"""Unit-smoke tests for risk sizing (Uge 5, Dag 3)."""

from __future__ import annotations

from pss.risk.sizing import (
    MAX_POSITION_PCT,
    apply_liquidity_constraint,
    calculate_kelly_size,
)
from pss.strategies.base import Signal


def main() -> None:
    zero_edge = Signal.build(
        market_id=1,
        condition_id="0x1",
        strategy="test",
        side="BUY_YES",
        market_price=0.5,
        fair_value_estimate=0.5,
        confidence=0.5,
    )
    size, dbg = calculate_kelly_size(zero_edge, 10_000)
    assert size == 0.0, dbg

    big_edge = Signal.build(
        market_id=2,
        condition_id="0x2",
        strategy="test",
        side="BUY_YES",
        market_price=0.1,
        fair_value_estimate=0.9,
        confidence=0.5,
    )
    size, _ = calculate_kelly_size(big_edge, 10_000)
    assert size <= 10_000 * MAX_POSITION_PCT + 0.01

    constrained = apply_liquidity_constraint(1000.0, 1000.0)
    assert constrained == 400.0

    print("test_risk_sizing: ok")


if __name__ == "__main__":
    main()
