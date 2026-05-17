"""Sæt NEW-signaler til EXPIRED hvis markeds-klassifikation er ændret."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from pss.base_rates.classifier import classify_market_fields
from pss.db.models import Market, Signal as SignalRow
from pss.db.session import AsyncSessionLocal


async def main() -> None:
    expired = 0
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(SignalRow, Market)
                .join(Market, Market.id == SignalRow.market_id)
                .where(SignalRow.status == "NEW"),
            )
        ).all()

        for sig, market in rows:
            meta = sig.signal_metadata or {}
            old_cat = meta.get("base_rate_category")
            new_cat = classify_market_fields(
                question=market.question,
                description=market.description,
                category=market.category,
                primary_vertical=market.primary_vertical,
            )
            if old_cat == new_cat:
                continue
            sig.status = "EXPIRED"
            sig.rejected_reason = "classifier_updated"
            expired += 1
            print(
                f"  id={sig.id}  {old_cat!r} → {new_cat!r}  "
                f"{(market.question or '')[:55]}",
            )

        if expired:
            await session.commit()

    print(f"\nExpired: {expired} / {len(rows)} NEW")
    print("expire_stale_new_signals: ok")


if __name__ == "__main__":
    asyncio.run(main())
