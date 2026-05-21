"""Hit rate, Sharpe, drawdown fra trade-liste."""

from __future__ import annotations

import math
from typing import Sequence


def hit_rate(wins: Sequence[bool | None]) -> float | None:
    resolved = [w for w in wins if w is not None]
    if not resolved:
        return None
    return sum(1 for w in resolved if w) / len(resolved)


def equity_curve(
    starting_bankroll: float,
    pnls: Sequence[float],
) -> list[float]:
    curve = [starting_bankroll]
    for pnl in pnls:
        curve.append(curve[-1] + pnl)
    return curve


def max_drawdown_pct(curve: Sequence[float]) -> float | None:
    if len(curve) < 2:
        return None
    peak = curve[0]
    max_dd = 0.0
    for value in curve:
        if value > peak:
            peak = value
        if peak > 0:
            dd = (peak - value) / peak
            max_dd = max(max_dd, dd)
    return max_dd


def sharpe_ratio(
    returns_pct: Sequence[float],
    *,
    periods_per_year: float = 52.0,
) -> float | None:
    if len(returns_pct) < 2:
        return None
    mean = sum(returns_pct) / len(returns_pct)
    var = sum((r - mean) ** 2 for r in returns_pct) / (len(returns_pct) - 1)
    if var <= 0:
        return None
    std = math.sqrt(var)
    if std == 0:
        return None
    return (mean / std) * math.sqrt(periods_per_year)
