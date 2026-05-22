#!/usr/bin/env python3
"""Verificer fetch_event_markets mod dansk PM-event."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pss.tracking.market_refs import fetch_event_markets, parse_market_reference

URL = (
    "https://polymarket.com/event/"
    "next-prime-minister-of-denmark-after-parliamentary-election"
)


async def main() -> int:
    kind, slug = parse_market_reference(URL)
    assert kind == "event_slug", f"Forventede event_slug, fik {kind}"

    result = await fetch_event_markets(slug)
    print(f"Event: {result.title}")
    print(f"Markeder: {len(result.markets)}")

    if len(result.markets) < 4:
        print("FEJL: for få markeder (forventede 4+ kandidater)")
        return 1

    print("\nTop outcomes (YES-pris):")
    for m in result.markets[:8]:
        yes = f"{m.yes_price_pp:.2f}%" if m.yes_price_pp is not None else "—"
        no = f"{m.no_price_pp:.2f}%" if m.no_price_pp is not None else "—"
        liq = f"${m.liquidity_usd:,.0f}" if m.liquidity_usd else "—"
        print(f"  {m.outcome_name:28} YES {yes:>7}  NO {no:>7}  liq {liq}")

    names = {m.outcome_name for m in result.markets}
    for expect in ("Lars Løkke Rasmussen", "Martin Lidegaard"):
        if not any(expect.split()[0] in n for n in names):
            print(f"ADVARSEL: fandt ikke forventet kandidat lignende '{expect}'")

    print("\nOK — event-handling klar til dashboard.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
