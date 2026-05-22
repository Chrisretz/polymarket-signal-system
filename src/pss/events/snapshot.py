"""Snapshot af inkonsistens-data per event (Strategi C Fase 1)."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from pss.db.models import Event, EventSnapshot, Market, MarketSnapshot
from pss.db.session import AsyncSessionLocal

logger = structlog.get_logger(__name__)

MIN_LEG_COUNT = 3
SLOW_EVENT_SECONDS = 2.0
INSERT_BATCH_SIZE = 500
MAX_NUMERIC_8_5 = 999.99999


@dataclass(frozen=True)
class SnapshotRunResult:
    processed: int
    skipped_few_legs: int
    skipped_incomplete: int
    skipped_overflow: int
    errors: int
    elapsed_seconds: float
    snapshot_at: datetime


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _liquidity_usd(snapshot: MarketSnapshot) -> float:
    return float(snapshot.liquidity_usd or 0)


def _inconsistency_pp(sum_yes_prices: float) -> float:
    return abs(sum_yes_prices - 1.0) * 100


def _fits_numeric_8_5(value: float) -> bool:
    return abs(value) <= MAX_NUMERIC_8_5


def build_leg_details(
    markets: list[Market],
    latest_by_market: dict[int, MarketSnapshot],
) -> tuple[list[dict[str, Any]], float, float] | None:
    """Byg leg_details og aggregater; None hvis et ben mangler snapshot."""
    leg_details: list[dict[str, Any]] = []
    sum_yes = 0.0
    min_liquidity = float("inf")

    for market in markets:
        latest = latest_by_market.get(market.id)
        yes_price = _float_or_none(latest.yes_price) if latest else None
        if latest is None or yes_price is None:
            return None

        liq = _liquidity_usd(latest)
        sum_yes += yes_price
        min_liquidity = min(min_liquidity, liq)
        leg_details.append(
            {
                "market_id": market.id,
                "condition_id": market.condition_id,
                "yes_price": yes_price,
                "liquidity_usd": liq,
                "yes_best_bid": _float_or_none(latest.yes_best_bid),
                "yes_best_ask": _float_or_none(latest.yes_best_ask),
                "category": market.category,
                "primary_vertical": market.primary_vertical,
            },
        )

    if min_liquidity == float("inf"):
        min_liquidity = 0.0

    return leg_details, sum_yes, min_liquidity


def build_event_snapshot_row(
    event: Event,
    markets: list[Market],
    latest_by_market: dict[int, MarketSnapshot],
    snapshot_at: datetime,
) -> dict[str, Any] | None:
    """Map event + markets til en event_snapshots-række; None hvis incomplete."""
    built = build_leg_details(markets, latest_by_market)
    if built is None:
        return None

    leg_details, sum_yes, min_liquidity = built
    inconsistency = _inconsistency_pp(sum_yes)
    if not _fits_numeric_8_5(sum_yes) or not _fits_numeric_8_5(inconsistency):
        return None

    return {
        "event_id": event.id,
        "snapshot_at": snapshot_at,
        "leg_count": len(markets),
        "sum_yes_prices": sum_yes,
        "inconsistency_pp": inconsistency,
        "min_leg_liquidity_usd": min_liquidity,
        "leg_details": leg_details,
    }


async def _fetch_latest_snapshots(
    session: Any,
    market_ids: list[int],
) -> dict[int, MarketSnapshot]:
    """Seneste market_snapshot per market_id (én batch-query)."""
    if not market_ids:
        return {}

    stmt = (
        select(MarketSnapshot)
        .where(MarketSnapshot.market_id.in_(market_ids))
        .order_by(MarketSnapshot.market_id, MarketSnapshot.snapshot_at.desc())
        .distinct(MarketSnapshot.market_id)
    )
    result = await session.execute(stmt)
    return {snap.market_id: snap for snap in result.scalars().all()}


async def _insert_snapshots(session: Any, rows: list[dict[str, Any]]) -> None:
    for offset in range(0, len(rows), INSERT_BATCH_SIZE):
        batch = rows[offset : offset + INSERT_BATCH_SIZE]
        stmt = insert(EventSnapshot).values(batch)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["event_id", "snapshot_at"],
        )
        await session.execute(stmt)


async def snapshot_events() -> SnapshotRunResult:
    """For hver aktiv event, beregn sum af YES-priser og likviditet.

    Køres efter price_snapshot, så vi har friske market snapshots at trække fra.

    Returns:
        Kørselsstatistik inkl. antal events der fik et event_snapshot indsat.
    """
    snapshot_at = datetime.now(timezone.utc)
    run_start = time.monotonic()
    processed = 0
    skipped_few_legs = 0
    skipped_incomplete = 0
    skipped_overflow = 0
    errors = 0
    slow_events = 0
    rows_to_insert: list[dict[str, Any]] = []

    async with AsyncSessionLocal() as session:
        events = (
            await session.execute(
                select(Event).where(
                    Event.is_active.is_(True),
                    Event.is_resolved.is_(False),
                ),
            )
        ).scalars().all()

        if not events:
            elapsed = time.monotonic() - run_start
            logger.info(
                "event_snapshot_complete",
                processed=0,
                skipped_few_legs=0,
                skipped_incomplete=0,
                errors=0,
                slow_events=0,
                elapsed_seconds=round(elapsed, 2),
            )
            return SnapshotRunResult(
                processed=0,
                skipped_few_legs=0,
                skipped_incomplete=0,
                skipped_overflow=0,
                errors=0,
                elapsed_seconds=elapsed,
                snapshot_at=snapshot_at,
            )

        external_ids = [event.event_id for event in events]
        markets_result = await session.execute(
            select(Market).where(Market.event_id.in_(external_ids)),
        )
        all_markets = markets_result.scalars().all()

        markets_by_event: dict[str, list[Market]] = defaultdict(list)
        for market in all_markets:
            if market.event_id:
                markets_by_event[market.event_id].append(market)

        latest_by_market = await _fetch_latest_snapshots(
            session,
            [market.id for market in all_markets],
        )

        for event in events:
            event_start = time.monotonic()
            try:
                markets = markets_by_event.get(event.event_id, [])
                if len(markets) < MIN_LEG_COUNT:
                    skipped_few_legs += 1
                    continue

                row = build_event_snapshot_row(
                    event,
                    markets,
                    latest_by_market,
                    snapshot_at,
                )
                if row is None:
                    built = build_leg_details(markets, latest_by_market)
                    if built is None:
                        skipped_incomplete += 1
                    else:
                        skipped_overflow += 1
                    continue

                rows_to_insert.append(row)
                processed += 1

                if time.monotonic() - event_start > SLOW_EVENT_SECONDS:
                    slow_events += 1
                    logger.warning(
                        "event_snapshot_slow",
                        event_id=event.event_id,
                        leg_count=len(markets),
                        elapsed_seconds=round(time.monotonic() - event_start, 3),
                    )
            except Exception as exc:
                errors += 1
                logger.warning(
                    "event_snapshot_error",
                    event_id=event.event_id,
                    error=str(exc),
                )

        if rows_to_insert:
            await _insert_snapshots(session, rows_to_insert)

        await session.commit()

    elapsed = time.monotonic() - run_start
    logger.info(
        "event_snapshot_complete",
        processed=processed,
        skipped_few_legs=skipped_few_legs,
        skipped_incomplete=skipped_incomplete,
        skipped_overflow=skipped_overflow,
        errors=errors,
        slow_events=slow_events,
        active_events=len(events),
        linked_markets=len(all_markets),
        snapshot_at=snapshot_at.isoformat(),
        elapsed_seconds=round(elapsed, 2),
    )
    return SnapshotRunResult(
        processed=processed,
        skipped_few_legs=skipped_few_legs,
        skipped_incomplete=skipped_incomplete,
        skipped_overflow=skipped_overflow,
        errors=errors,
        elapsed_seconds=elapsed,
        snapshot_at=snapshot_at,
    )
