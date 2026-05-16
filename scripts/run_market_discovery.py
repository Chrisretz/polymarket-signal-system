"""Kør market discovery og vis DB-statistik (Uge 2, Dag 1)."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import func, select

from pss.db.models import Market
from pss.db.session import AsyncSessionLocal
from pss.ingestion.market_discovery import discover_markets


async def main() -> None:
    try:
        processed = await discover_markets()
    except Exception as exc:
        print(f"market_discovery fejl: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    async with AsyncSessionLocal() as session:
        total = await session.scalar(select(func.count()).select_from(Market))
        active = await session.scalar(
            select(func.count())
            .select_from(Market)
            .where(Market.is_active, ~Market.is_closed),
        )
        by_vertical = (
            await session.execute(
                select(Market.primary_vertical, func.count())
                .where(Market.is_active, ~Market.is_closed)
                .group_by(Market.primary_vertical)
                .order_by(func.count().desc()),
            )
        ).all()
        sample = []
        if total and total >= 1:
            sample = (
                await session.execute(
                    select(Market.question, Market.primary_vertical)
                    .where(Market.is_active)
                    .limit(3),
                )
            ).all()

    print(f"Behandlet denne kørsel: {processed}")
    print(f"Markeder i database (total): {total}")
    print(f"Aktive (ikke lukket): {active}")
    print("\nFordeling primary_vertical (aktive):")
    for vertical, n in by_vertical:
        label = vertical or "(null)"
        print(f"  {label}: {n}")

    if sample:
        print("\nEksempel-markeder:")
        for question, vertical in sample:
            print(f"  [{vertical}] {(question or '')[:70]}")

    print("\nrun_market_discovery: ok")


if __name__ == "__main__":
    asyncio.run(main())
