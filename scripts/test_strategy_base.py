"""Verificér Strategy base + Signal (Uge 5, Dag 1)."""

from __future__ import annotations

import asyncio

from pss.strategies.base import Signal, Strategy, compute_edge_pct


class _DemoStrategy(Strategy):
    name = "demo"

    async def scan_for_signals(self) -> list[Signal]:
        return [
            Signal.build(
                market_id=1,
                condition_id="0xabc",
                strategy=self.name,
                side="BUY_NO",
                market_price=0.70,
                fair_value_estimate=0.50,
                confidence=0.6,
            ),
        ]


async def main() -> None:
    strategy = _DemoStrategy()
    signals = await strategy.scan_for_signals()
    assert len(signals) == 1

    sig = strategy.enrich_signal(signals[0])
    assert abs(compute_edge_pct(0.70, 0.50, "BUY_NO") - 0.20) < 1e-9
    assert abs(sig.edge_pct - 0.20) < 1e-9
    assert strategy.validate_signal(sig, min_edge_pct=0.15)
    assert not strategy.validate_signal(sig, min_edge_pct=0.25)
    assert sig.exit_price_target is not None
    assert sig.exit_date_target is not None

    print(f"Signal: side={sig.side} edge={sig.edge_pct:.2f} target={sig.exit_price_target:.2f}")
    print("test_strategy_base: ok")


if __name__ == "__main__":
    asyncio.run(main())
