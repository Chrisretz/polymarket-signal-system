"""Verificér at alle kerne-tabeller findes efter migration."""

from __future__ import annotations

import asyncio

import asyncpg

from pss.config import settings

EXPECTED_TABLES = (
    "markets",
    "market_snapshots",
    "orderbook_depth",
    "events",
    "event_snapshots",
    "base_rates",
    "signals",
    "positions",
    "decisions_journal",
    "performance_daily",
    "news_events",
)

EXPECTED_HYPERTABLES = (
    "market_snapshots",
    "orderbook_depth",
    "event_snapshots",
)


async def main() -> None:
    conn = await asyncpg.connect(settings.asyncpg_dsn, ssl=settings.asyncpg_ssl)
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
            list(EXPECTED_HYPERTABLES),
        )
        ht_names = {r["hypertable_name"] for r in hypertables}
        missing_ht = set(EXPECTED_HYPERTABLES) - ht_names
        if missing_ht:
            print(f"Mangler hypertables: {sorted(missing_ht)}")
            raise SystemExit(1)

        # markets: has_base_rate skal være væk efter 0002
        has_br = await conn.fetchval(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'markets'
              AND column_name = 'has_base_rate'
            """,
        )
        if has_br:
            print("markets.has_base_rate findes stadig (forventet droppet i 0002)")
            raise SystemExit(1)

        signal_cols = await conn.fetch(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'signals'
              AND column_name = ANY($1::text[])
            ORDER BY column_name
            """,
            [
                "event_id",
                "legs",
                "sum_yes_prices",
                "inconsistency_pp",
                "net_edge_pp",
                "min_leg_liquidity_usd",
            ],
        )
        signal_col_names = {r["column_name"] for r in signal_cols}
        expected_signal_cols = {
            "event_id",
            "inconsistency_pp",
            "legs",
            "min_leg_liquidity_usd",
            "net_edge_pp",
            "sum_yes_prices",
        }
        missing_signal = expected_signal_cols - signal_col_names
        if missing_signal:
            print(f"Mangler signals-kolonner: {sorted(missing_signal)}")
            raise SystemExit(1)

        print(f"Tabeller OK ({len(found)}):")
        for t in sorted(found):
            print(f"  - {t}")
        print(f"Hypertables OK: {', '.join(sorted(ht_names))}")
        print("markets.has_base_rate: absent (OK)")
        print(f"signals multi-leg cols: {', '.join(sorted(signal_col_names))}")
        print("verify_schema: ok")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
