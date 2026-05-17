"""Kør BaseRateFadeStrategy mod database (Uge 5, Dag 2)."""

from __future__ import annotations

import asyncio
from collections import Counter

from pss.strategies.base_rate_fade import BaseRateFadeStrategy


async def main() -> None:
    strategy = BaseRateFadeStrategy()
    signals = await strategy.scan_for_signals()

    print(f"Signaler fundet: {len(signals)}\n")
    sides = Counter(s.side for s in signals)
    print(f"Sider: {dict(sides)}")

    top = sorted(signals, key=lambda s: s.edge_pct, reverse=True)[:10]
    if top:
        print("\nTop 10 efter edge:")
        for sig in top:
            cat = sig.metadata.get("base_rate_category", "?")
            dev = sig.metadata.get("deviation_pp", 0)
            q = sig.metadata.get("question", "")[:60]
            print(
                f"  edge={sig.edge_pct:.2f} {sig.side:7} cat={cat:24} "
                f"dev={dev:+.2f}  {q}",
            )

    print("\nscan_base_rate_signals: ok")


if __name__ == "__main__":
    asyncio.run(main())
