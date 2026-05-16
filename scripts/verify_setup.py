"""Verificér config og database (Uge 1, Dag 2)."""

from __future__ import annotations

import asyncio
import sys

import asyncpg

from pss.config import settings

MAX_ATTEMPTS = 10
RETRY_SECONDS = 2


async def check_db() -> None:
    """Forbind til Postgres; retry mens containeren starter op."""
    last_error: BaseException | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            conn = await asyncpg.connect(
                settings.asyncpg_dsn,
                ssl=False,  # lokal Docker-Postgres bruger ikke TLS
            )
            try:
                pg_version = await conn.fetchval("SELECT version()")
                ts_version = await conn.fetchval(
                    "SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'",
                )
            finally:
                await conn.close()
            break
        except (OSError, ConnectionError, asyncpg.PostgresConnectionError) as exc:
            last_error = exc
            if attempt < MAX_ATTEMPTS:
                print(
                    f"Database ikke klar (forsøg {attempt}/{MAX_ATTEMPTS}), "
                    f"prøver igen om {RETRY_SECONDS}s...",
                )
                await asyncio.sleep(RETRY_SECONDS)
            else:
                raise
    else:
        raise last_error  # type: ignore[misc]

    print(f"PostgreSQL: {str(pg_version)[:80]}...")
    if not ts_version:
        print("TimescaleDB: NOT INSTALLED", file=sys.stderr)
        raise SystemExit(1)
    print(f"TimescaleDB: {ts_version}")


def main() -> None:
    host = settings.asyncpg_dsn.split("@", 1)[-1]
    print(f"Environment: {settings.environment}")
    print(f"Database: {host}")
    print(f"Bankroll (USD): {settings.bankroll_usd}")
    asyncio.run(check_db())
    print("verify_setup: ok")


if __name__ == "__main__":
    main()
