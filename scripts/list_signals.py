"""Vis seneste signaler fra database."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from pss.db.models import Market, Signal as SignalRow
from pss.db.session import AsyncSessionLocal
from pss.logging_config import configure_logging


async def main() -> None:
    configure_logging()
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(SignalRow, Market.question)
                .join(Market, Market.id == SignalRow.market_id)
                .where(SignalRow.status == "NEW")
                .order_by(SignalRow.generated_at.desc())
                .limit(20),
            )
        ).all()

    print(f"Seneste NEW-signaler: {len(rows)}\n")
    for sig, question in rows:
        print(
            f"id={sig.id}  ${float(sig.suggested_size_usd):.0f}  {sig.side:7}  "
            f"edge={float(sig.edge_pct):.2f}  {(question or '')[:55]}",
        )
    print("\nlist_signals: ok")


if __name__ == "__main__":
    asyncio.run(main())
