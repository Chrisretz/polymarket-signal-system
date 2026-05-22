"""Backfill markets.event_id from raw_metadata.events[0].id (one-off)."""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from pss.db.session import AsyncSessionLocal


async def main() -> None:
    sql = text(
        """
        UPDATE markets
        SET event_id = raw_metadata->'events'->0->>'id'
        WHERE event_id IS NULL
          AND raw_metadata->'events'->0->>'id' IS NOT NULL
        """,
    )
    async with AsyncSessionLocal() as session:
        result = await session.execute(sql)
        await session.commit()
        print(f"Backfilled event_id rows: {result.rowcount}")


if __name__ == "__main__":
    asyncio.run(main())
