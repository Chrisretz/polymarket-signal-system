"""Test Gamma API: list_markets() (Uge 1, Dag 5)."""

from __future__ import annotations

import asyncio
import sys

from pss.clients.gamma import GammaClient


def _market_label(market: dict) -> str:
    question = (market.get("question") or market.get("title") or "?")[:80]
    condition_id = market.get("conditionId") or market.get("condition_id") or "?"
    return f"{question}  [{condition_id[:16]}...]"


async def main() -> None:
    try:
        async with GammaClient() as gamma:
            markets = await gamma.list_markets(limit=10)
    except Exception as exc:
        print(f"Gamma API fejl: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if len(markets) < 10:
        print(
            f"Advarsel: fik kun {len(markets)} markeder (forventede mindst 10).",
            file=sys.stderr,
        )
        if not markets:
            raise SystemExit(1)

    print(f"Gamma API OK — {len(markets)} markeder (første side, limit=10):\n")
    for i, market in enumerate(markets, start=1):
        print(f"{i:2}. {_market_label(market)}")

    print("\ntest_gamma: ok")


if __name__ == "__main__":
    asyncio.run(main())
