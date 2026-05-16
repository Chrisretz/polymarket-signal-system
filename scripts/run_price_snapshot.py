"""Kør price snapshot og vis statistik (Uge 2, Dag 2)."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import func, select

from pss.db.models import MarketSnapshot
from pss.db.session import AsyncSessionLocal
from pss.ingestion.price_snapshot import snapshot_all_active_markets


async def main() -> None:
    try:
        inserted = await snapshot_all_active_markets()
    except Exception as exc:
        print(f"price_snapshot fejl: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    async with AsyncSessionLocal() as session:
        total_rows = await session.scalar(select(func.count()).select_from(MarketSnapshot))
        latest_at = await session.scalar(select(func.max(MarketSnapshot.snapshot_at)))
        distinct_markets = await session.scalar(
            select(func.count(func.distinct(MarketSnapshot.market_id))),
        )
        sample = (
            await session.execute(
                select(
                    MarketSnapshot.market_id,
                    MarketSnapshot.yes_price,
                    MarketSnapshot.no_price,
                    MarketSnapshot.volume_24h,
                )
                .order_by(MarketSnapshot.snapshot_at.desc())
                .limit(3),
            )
        ).all()

    print(f"Snapshots indsat denne kørsel: {inserted}")
    print(f"Rækker i market_snapshots (total): {total_rows}")
    print(f"Unikke markeder med snapshots: {distinct_markets}")
    print(f"Seneste snapshot_at (UTC): {latest_at}")

    if sample:
        print("\nEksempel (seneste rækker):")
        for market_id, yes_p, no_p, vol in sample:
            print(
                f"  market_id={market_id}  yes={yes_p}  no={no_p}  vol24h={vol}",
            )

    if inserted < 1:
        print("Advarsel: ingen snapshots indsat.", file=sys.stderr)
        raise SystemExit(1)

    print("\nrun_price_snapshot: ok")


if __name__ == "__main__":
    asyncio.run(main())
