"""Kør risk på liste af signaler."""

from __future__ import annotations

from pss.config import settings
from pss.risk.portfolio import can_open_new_position
from pss.risk.sizing import apply_risk_to_signal
from pss.strategies.base import Signal


async def apply_risk_pipeline(
    signals: list[Signal],
    *,
    bankroll_usd: float | None = None,
) -> list[Signal]:
    """Size + portfolio-filter; returnerer kun godkendte signaler med size > 0."""
    bankroll = bankroll_usd if bankroll_usd is not None else settings.bankroll_usd
    approved: list[Signal] = []

    for signal in signals:
        liquidity = float(signal.metadata.get("liquidity_usd") or 0.0)
        sized = apply_risk_to_signal(
            signal,
            bankroll_usd=bankroll,
            available_liquidity_usd=liquidity,
        )
        if sized.suggested_size_usd <= 0.0:
            continue

        group = signal.metadata.get("base_rate_category")
        allowed, reason = await can_open_new_position(
            sized.suggested_size_usd,
            str(group) if group else None,
            bankroll,
        )
        if not allowed:
            sized.metadata["risk_rejected"] = reason
            continue

        sized.metadata["risk_approved"] = True
        approved.append(sized)

    return approved
