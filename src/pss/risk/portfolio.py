"""Portefølje-eksponering og caps."""

from __future__ import annotations

from sqlalchemy import func, select

from pss.db.models import Position
from pss.db.session import AsyncSessionLocal

MAX_TOTAL_EXPOSURE_PCT = 0.60
MAX_CORRELATED_EXPOSURE_PCT = 0.30


async def get_current_exposure(bankroll_usd: float) -> dict[str, float]:
    """Åben eksponering fra positions-tabellen."""
    async with AsyncSessionLocal() as session:
        open_exposure = await session.scalar(
            select(func.coalesce(func.sum(Position.entry_size_usd), 0)).where(
                Position.status == "OPEN",
            ),
        )

    exposure = float(open_exposure or 0.0)
    cap_usd = bankroll_usd * MAX_TOTAL_EXPOSURE_PCT
    return {
        "open_exposure_usd": exposure,
        "open_exposure_pct": exposure / bankroll_usd if bankroll_usd > 0 else 0.0,
        "available_usd": max(0.0, cap_usd - exposure),
        "max_total_usd": cap_usd,
    }


async def can_open_new_position(
    proposed_size_usd: float,
    correlation_group: str | None,
    bankroll_usd: float,
) -> tuple[bool, str]:
    """Tjek total eksponering (korrelations-tjek TODO)."""
    if proposed_size_usd <= 0.0:
        return False, "zero_size"

    exposure = await get_current_exposure(bankroll_usd)
    if exposure["open_exposure_usd"] + proposed_size_usd > exposure["max_total_usd"]:
        return False, "total_exposure_cap"

    _ = correlation_group
    return True, "ok"
