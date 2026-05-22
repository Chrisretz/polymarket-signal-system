"""Snapshot live priser for aktive tracked groups."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from pss.clients.gamma import GammaClient
from pss.config import settings
from pss.db.models import Market, TrackedGroup, TrackedGroupMarket, TrackedGroupSnapshot
from pss.db.session import AsyncSessionLocal
from pss.tracking.prices import build_role_prices, parse_gamma_yes_price
from pss.tracking.relations import evaluate_group_relations

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class GroupSnapshotResult:
    group_id: int
    group_name: str
    snapshot_at: datetime
    metrics: dict[str, Any]
    market_count: int
    missing_prices: list[str]


@dataclass(frozen=True, slots=True)
class SnapshotRunResult:
    groups_processed: int
    snapshots_written: int
    results: list[GroupSnapshotResult]


async def _load_active_groups() -> list[TrackedGroup]:
    async with AsyncSessionLocal() as session:
        q = (
            select(TrackedGroup)
            .where(TrackedGroup.status == "active")
            .options(
                selectinload(TrackedGroup.markets).selectinload(TrackedGroupMarket.market),
                selectinload(TrackedGroup.relations),
            )
            .order_by(TrackedGroup.id)
        )
        return list((await session.execute(q)).scalars().all())


async def _fetch_gamma_yes_prices(
    market_rows: list[Market],
    *,
    gamma: GammaClient,
) -> dict[str, float | None]:
    """Returnerer condition_id → YES-pris (deduplikeret)."""
    prices: dict[str, float | None] = {}
    seen: set[str] = set()
    for market in market_rows:
        cid = market.condition_id
        if cid in seen:
            continue
        seen.add(cid)

        payload: dict | None = None
        if market.slug:
            try:
                payload = await gamma.get_market_by_slug(market.slug)
            except Exception:
                payload = None
        if not payload:
            batch = await gamma.get_markets_by_condition_ids([cid])
            payload = batch.get(cid)

        prices[cid] = parse_gamma_yes_price(payload) if payload else None
    return prices


def _build_group_prices(
    markets: list[TrackedGroupMarket],
    yes_prices: dict[str, float | None],
) -> tuple[dict[str, float], list[str]]:
    rows: list[tuple[str, str, float | None]] = []
    missing: list[str] = []
    for gm in markets:
        cid = gm.market.condition_id
        yes_price = yes_prices.get(cid)
        if yes_price is None:
            missing.append(gm.role_label)
        rows.append((gm.role_label, gm.outcome_side, yes_price))
    return build_role_prices(rows), missing


async def snapshot_group(
    group: TrackedGroup,
    *,
    gamma: GammaClient | None = None,
    threshold_pp: float | None = None,
    persist: bool = True,
) -> GroupSnapshotResult:
    """Hent priser, evaluér relationer, gem snapshot."""
    threshold = (
        threshold_pp
        if threshold_pp is not None
        else settings.tracked_group_alert_threshold_pp
    )
    condition_ids = [gm.market.condition_id for gm in group.markets]
    market_orms = [gm.market for gm in group.markets]
    if gamma is not None:
        yes_prices = await _fetch_gamma_yes_prices(market_orms, gamma=gamma)
    else:
        async with GammaClient() as client:
            yes_prices = await _fetch_gamma_yes_prices(market_orms, gamma=client)
    prices, missing = _build_group_prices(group.markets, yes_prices)

    relations = [(r.relation_type, r.definition) for r in group.relations]
    metrics = evaluate_group_relations(relations, prices, threshold_pp=threshold)
    metrics["missing_roles"] = missing

    snapshot_at = datetime.now(timezone.utc)
    if persist:
        async with AsyncSessionLocal() as session:
            session.add(
                TrackedGroupSnapshot(
                    group_id=group.id,
                    snapshot_at=snapshot_at,
                    calculated_metrics=metrics,
                ),
            )
            await session.commit()

    logger.info(
        "tracked_group_snapshot",
        group_id=group.id,
        group_name=group.name,
        market_count=len(group.markets),
        max_inconsistency_pp=metrics["max_inconsistency_pp"],
        alert_count=metrics["alert_count"],
        missing=len(missing),
    )

    return GroupSnapshotResult(
        group_id=group.id,
        group_name=group.name,
        snapshot_at=snapshot_at,
        metrics=metrics,
        market_count=len(group.markets),
        missing_prices=missing,
    )


async def snapshot_all_active_groups(
    *,
    threshold_pp: float | None = None,
    persist: bool = True,
) -> SnapshotRunResult:
    """Snapshot alle aktive grupper (scheduler + CLI)."""
    groups = await _load_active_groups()
    if not groups:
        logger.info("tracked_group_snapshot_skip", reason="no_active_groups")
        return SnapshotRunResult(groups_processed=0, snapshots_written=0, results=[])

    all_markets: list[Market] = []
    for group in groups:
        all_markets.extend(gm.market for gm in group.markets)

    async with GammaClient() as gamma:
        yes_prices = await _fetch_gamma_yes_prices(all_markets, gamma=gamma)
        results: list[GroupSnapshotResult] = []
        threshold = (
            threshold_pp
            if threshold_pp is not None
            else settings.tracked_group_alert_threshold_pp
        )

        for group in groups:
            prices, missing = _build_group_prices(group.markets, yes_prices)
            relations = [(r.relation_type, r.definition) for r in group.relations]
            metrics = evaluate_group_relations(relations, prices, threshold_pp=threshold)
            metrics["missing_roles"] = missing

            snapshot_at = datetime.now(timezone.utc)
            if persist:
                async with AsyncSessionLocal() as session:
                    session.add(
                        TrackedGroupSnapshot(
                            group_id=group.id,
                            snapshot_at=snapshot_at,
                            calculated_metrics=metrics,
                        ),
                    )
                    await session.commit()

            logger.info(
                "tracked_group_snapshot",
                group_id=group.id,
                group_name=group.name,
                market_count=len(group.markets),
                max_inconsistency_pp=metrics["max_inconsistency_pp"],
                alert_count=metrics["alert_count"],
                missing=len(missing),
            )
            results.append(
                GroupSnapshotResult(
                    group_id=group.id,
                    group_name=group.name,
                    snapshot_at=snapshot_at,
                    metrics=metrics,
                    market_count=len(group.markets),
                    missing_prices=missing,
                ),
            )

    return SnapshotRunResult(
        groups_processed=len(results),
        snapshots_written=len(results) if persist else 0,
        results=results,
    )
