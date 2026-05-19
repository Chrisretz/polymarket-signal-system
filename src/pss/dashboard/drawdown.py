"""Drawdown-beregning og alert-niveauer (STRATEGY.md §7.2)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DrawdownState:
    bankroll_start: float
    bankroll_current: float
    peak: float
    drawdown_pct: float
    level: str | None  # None | "review" | "reduce" | "stop"


THRESHOLDS: tuple[tuple[float, str], ...] = (
    (0.20, "stop"),
    (0.15, "reduce"),
    (0.10, "review"),
)


def compute_drawdown(
    *,
    bankroll_start: float,
    bankroll_current: float,
    peak_override: float | None = None,
) -> DrawdownState:
    peak = peak_override if peak_override is not None else max(bankroll_start, bankroll_current)
    if peak <= 0:
        return DrawdownState(
            bankroll_start=bankroll_start,
            bankroll_current=bankroll_current,
            peak=peak,
            drawdown_pct=0.0,
            level=None,
        )
    dd = max(0.0, (peak - bankroll_current) / peak)
    level: str | None = None
    for threshold, name in THRESHOLDS:
        if dd >= threshold:
            level = name
            break
    return DrawdownState(
        bankroll_start=bankroll_start,
        bankroll_current=bankroll_current,
        peak=peak,
        drawdown_pct=dd,
        level=level,
    )


def alert_message(state: DrawdownState) -> str | None:
    if state.level is None:
        return None
    pct = state.drawdown_pct * 100
    messages = {
        "review": f"Drawdown {pct:.1f}% — gennemgå journal og fejl (≥10%).",
        "reduce": f"Drawdown {pct:.1f}% — halvér position sizes (≥15%).",
        "stop": f"Drawdown {pct:.1f}% — stop nye positioner (≥20%).",
    }
    return messages.get(state.level)
