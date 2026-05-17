"""Tager periodiske snapshots af priser og volume."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select

from pss.clients.gamma import GammaClient
from pss.db.models import Market, MarketSnapshot
from pss.db.session import AsyncSessionLocal

logger = structlog.get_logger(__name__)


def _parse_outcome_prices(raw: Any) -> tuple[float, float] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, list) or len(raw) < 2:
        return None
    try:
        return float(raw[0]), float(raw[1])
    except (TypeError, ValueError):
        return None


async def _fetch_gamma_price_index(
    gamma: GammaClient,
    *,
    needed_condition_ids: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Hent aktive markeder fra Gamma; stop tidligt når alle DB-markeder er fundet."""
    index: dict[str, dict[str, Any]] = {}
    needed = set(needed_condition_ids) if needed_condition_ids else None

    async for batch in gamma.iter_active_market_pages():
        for item in batch:
            condition_id = item.get("conditionId")
            if condition_id:
                index[condition_id] = item

        if needed is not None and needed.issubset(index.keys()):
            logger.info(
                "gamma_price_index_early_complete",
                indexed=len(index),
                needed=len(needed),
            )
            break

    logger.info("gamma_price_index_built", markets=len(index))
    return index


async def snapshot_all_active_markets() -> int:
    """Snapshot af alle aktive markeder i DB med friske Gamma-priser."""
    snapshot_time = datetime.now(timezone.utc)
    count = 0
    skipped = 0
    missing_in_gamma = 0

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Market).where(Market.is_active, ~Market.is_closed),
        )
        active_markets = result.scalars().all()

        if not active_markets:
            logger.info("snapshot_complete", count=0, reason="no_active_markets")
            return 0

        needed = {m.condition_id for m in active_markets if m.condition_id}

        async with GammaClient() as gamma:
            price_index = await _fetch_gamma_price_index(
                gamma,
                needed_condition_ids=needed,
            )

            for market in active_markets:
                try:
                    data = price_index.get(market.condition_id)
                    if data is None:
                        missing_in_gamma += 1
                        continue

                    prices = _parse_outcome_prices(data.get("outcomePrices"))
                    if prices is None:
                        skipped += 1
                        continue

                    yes_price, no_price = prices
                    snapshot = MarketSnapshot(
                        market_id=market.id,
                        snapshot_at=snapshot_time,
                        yes_price=yes_price,
                        no_price=no_price,
                        volume_24h=float(data.get("volume24hr") or 0),
                        volume_total=float(data.get("volume") or data.get("volumeNum") or 0),
                        liquidity_usd=float(
                            data.get("liquidity") or data.get("liquidityNum") or 0,
                        ),
                    )
                    session.add(snapshot)
                    count += 1
                except Exception as exc:
                    logger.warning(
                        "snapshot_skip",
                        market=market.condition_id,
                        error=str(exc),
                    )
                    skipped += 1

            await session.commit()

    logger.info(
        "snapshot_complete",
        count=count,
        skipped=skipped,
        missing_in_gamma=missing_in_gamma,
        snapshot_at=snapshot_time.isoformat(),
    )
    return count
