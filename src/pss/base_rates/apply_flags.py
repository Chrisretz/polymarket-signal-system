"""Sæt markets.has_base_rate ud fra classifier."""

from __future__ import annotations

import structlog
from sqlalchemy import func, select

from pss.base_rates.classifier import classify_market_fields
from pss.db.models import Market
from pss.db.session import AsyncSessionLocal

logger = structlog.get_logger(__name__)

TARGET_VERTICALS = ("macro", "eu_politics")


async def apply_has_base_rate_flags(*, dry_run: bool = False) -> dict[str, int]:
    """Opdater has_base_rate for macro/eu_politics-markeder.

    Returns:
        Stats: scanned, set_true, set_false, unchanged_true, unchanged_false.
    """
    stats = {
        "scanned": 0,
        "set_true": 0,
        "set_false": 0,
        "unchanged_true": 0,
        "unchanged_false": 0,
    }

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Market).where(
                Market.is_active,
                ~Market.is_closed,
                Market.primary_vertical.in_(TARGET_VERTICALS),
            ),
        )
        markets = result.scalars().all()
        stats["scanned"] = len(markets)

        for m in markets:
            category = classify_market_fields(
                question=m.question,
                description=m.description,
                category=m.category,
                primary_vertical=m.primary_vertical,
            )
            should_have = category is not None

            if should_have and m.has_base_rate:
                stats["unchanged_true"] += 1
                continue
            if not should_have and not m.has_base_rate:
                stats["unchanged_false"] += 1
                continue

            if dry_run:
                if should_have:
                    stats["set_true"] += 1
                else:
                    stats["set_false"] += 1
                continue

            m.has_base_rate = should_have
            if should_have:
                stats["set_true"] += 1
            else:
                stats["set_false"] += 1

        if not dry_run:
            await session.commit()

    logger.info("has_base_rate_flags_applied", dry_run=dry_run, **stats)
    return stats


async def count_flagged() -> tuple[int, int]:
    """Returnér (med flag, macro/eu_politics aktive total)."""
    async with AsyncSessionLocal() as session:
        total = await session.scalar(
            select(func.count())
            .select_from(Market)
            .where(
                Market.is_active,
                ~Market.is_closed,
                Market.primary_vertical.in_(TARGET_VERTICALS),
            ),
        )
        flagged = await session.scalar(
            select(func.count())
            .select_from(Market)
            .where(
                Market.is_active,
                ~Market.is_closed,
                Market.primary_vertical.in_(TARGET_VERTICALS),
                Market.has_base_rate,
            ),
        )
    return int(flagged or 0), int(total or 0)
