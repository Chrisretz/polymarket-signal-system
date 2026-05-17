"""Kør base-rate classifier på aktive markeder (Uge 4, Dag 4)."""

from __future__ import annotations

import asyncio
from collections import Counter

from sqlalchemy import select

from pss.base_rates.classifier import classify_market_fields
from pss.db.models import Market
from pss.db.session import AsyncSessionLocal


async def main() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Market).where(
                Market.is_active,
                ~Market.is_closed,
                Market.primary_vertical.in_(("macro", "eu_politics")),
            ),
        )
        markets = result.scalars().all()

    matched: Counter[str] = Counter()
    unmatched = 0
    samples: dict[str, list[str]] = {}

    for m in markets:
        cat = classify_market_fields(
            question=m.question,
            description=m.description,
            category=m.category,
            primary_vertical=m.primary_vertical,
        )
        if cat is None:
            unmatched += 1
            continue
        matched[cat] += 1
        if cat not in samples or len(samples[cat]) < 2:
            samples.setdefault(cat, []).append((m.question or "")[:72])

    total = len(markets)
    print(f"Markeder (macro + eu_politics): {total}")
    print(f"Matched base rate: {sum(matched.values())}")
    print(f"Ingen match: {unmatched}\n")

    print("Fordeling:")
    for cat, n in matched.most_common():
        print(f"  {cat:28} {n:5d}")
        for q in samples.get(cat, []):
            print(f"    → {q}")

    if total and sum(matched.values()) == 0:
        raise SystemExit(1)

    print("\nclassify_markets: ok")


if __name__ == "__main__":
    asyncio.run(main())
