"""Verificér at alle kerne-tabeller findes efter migration."""

from __future__ import annotations

import asyncio

import asyncpg

from pss.config import settings

EXPECTED_TABLES = (
    "markets",
    "market_snapshots",
    "orderbook_depth",
    "base_rates",
    "signals",
    "positions",
    "decisions_journal",
    "performance_daily",
    "news_events",
)


async def main() -> None:
    conn = await asyncpg.connect(settings.asyncpg_dsn, ssl=False)
    try:
        rows = await conn.fetch(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public' AND tablename = ANY($1::text[])
            ORDER BY tablename
            """,
            list(EXPECTED_TABLES),
        )
        found = {r["tablename"] for r in rows}
        missing = set(EXPECTED_TABLES) - found
        if missing:
            print(f"Mangler tabeller: {sorted(missing)}")
            raise SystemExit(1)

        hypertables = await conn.fetch(
            """
            SELECT hypertable_name FROM timescaledb_information.hypertables
            WHERE hypertable_name = ANY($1::text[])
            """,
            ["market_snapshots", "orderbook_depth"],
        )
        ht_names = {r["hypertable_name"] for r in hypertables}
        for name in ("market_snapshots", "orderbook_depth"):
            if name not in ht_names:
                print(f"Mangler hypertable: {name}")
                raise SystemExit(1)

        print(f"Tabeller OK ({len(found)}):")
        for t in sorted(found):
            print(f"  - {t}")
        print(f"Hypertables OK: {', '.join(sorted(ht_names))}")
        print("verify_schema: ok")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
