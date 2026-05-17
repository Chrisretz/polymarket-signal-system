"""Scan base-rate fade + risk sizing (Uge 5, Dag 3)."""

from __future__ import annotations

import asyncio

from pss.config import settings
from pss.risk.pipeline import apply_risk_pipeline
from pss.strategies.base_rate_fade import BaseRateFadeStrategy


async def main() -> None:
    raw = await BaseRateFadeStrategy().scan_for_signals()
    sized = await apply_risk_pipeline(raw)

    print(f"Rå signaler: {len(raw)}")
    print(f"Efter risk (size > 0, portfolio OK): {len(sized)}")
    print(f"Bankroll (config): ${settings.bankroll_usd:,.0f}\n")

    for sig in sorted(sized, key=lambda s: s.suggested_size_usd, reverse=True)[:10]:
        sizing = sig.metadata.get("sizing", {})
        print(
            f"  ${sig.suggested_size_usd:>7.2f}  edge={sig.edge_pct:.2f}  {sig.side:7}  "
            f"{sig.metadata.get('question', '')[:50]}",
        )
        print(f"           kelly={sizing.get('applied_fraction', '—')}")

    print("\nscan_and_size_signals: ok")


if __name__ == "__main__":
    asyncio.run(main())
