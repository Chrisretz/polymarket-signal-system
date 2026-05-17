"""Position sizing: modificeret Kelly + likviditetsloft."""

from __future__ import annotations

from typing import Any

from pss.strategies.base import Signal

KELLY_FRACTION = 0.25
MAX_POSITION_PCT = 0.05
MIN_POSITION_USD = 10.0
LIQUIDITY_CAP_PCT = 0.40


def calculate_kelly_size(
    signal: Signal,
    bankroll_usd: float,
) -> tuple[float, dict[str, Any]]:
    """Beregner anbefalet position size i USD."""
    price = signal.market_price
    if price <= 0.0 or price >= 1.0 or bankroll_usd <= 0.0:
        return 0.0, {"reason": "invalid_price_or_bankroll"}

    p = signal.fair_value_estimate
    q = 1.0 - p
    b = (1.0 - price) / price

    full_kelly = (b * p - q) / b
    if full_kelly <= 0.0:
        return 0.0, {"reason": "negative_kelly", "full_kelly": round(full_kelly, 4)}

    fraction = min(KELLY_FRACTION * full_kelly, MAX_POSITION_PCT)
    size_usd = round(bankroll_usd * fraction, 2)

    if size_usd < MIN_POSITION_USD:
        return 0.0, {
            "reason": "below_min_size",
            "would_size": size_usd,
            "full_kelly": round(full_kelly, 4),
        }

    return size_usd, {
        "full_kelly": round(full_kelly, 4),
        "applied_fraction": round(fraction, 4),
        "size_usd": size_usd,
        "kelly_fraction": KELLY_FRACTION,
    }


def apply_liquidity_constraint(
    size_usd: float,
    available_liquidity_usd: float,
    *,
    cap_pct: float = LIQUIDITY_CAP_PCT,
) -> float:
    """Begræns size til andel af book-likviditet."""
    if available_liquidity_usd <= 0.0:
        return 0.0
    return min(size_usd, round(available_liquidity_usd * cap_pct, 2))


def apply_risk_to_signal(
    signal: Signal,
    *,
    bankroll_usd: float,
    available_liquidity_usd: float,
) -> Signal:
    """Sæt suggested_size_usd og sizing-metadata på signalet."""
    size, debug = calculate_kelly_size(signal, bankroll_usd)
    if size > 0.0:
        size = apply_liquidity_constraint(size, available_liquidity_usd)
        if size < MIN_POSITION_USD:
            size = 0.0
            debug = {**debug, "reason": "below_min_after_liquidity", "liquidity_cap": True}

    signal.suggested_size_usd = size
    signal.metadata = {
        **signal.metadata,
        "sizing": debug,
        "liquidity_usd": available_liquidity_usd,
    }
    return signal
