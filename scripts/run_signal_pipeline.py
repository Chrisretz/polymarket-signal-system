"""Scan → risk → persist → Telegram (CLI)."""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import func, select

from pss.config import settings
from pss.logging_config import configure_logging
from pss.db.models import Signal as SignalRow
from pss.db.session import AsyncSessionLocal
from pss.signals.pipeline import run_signal_pipeline


async def _count_new_signals() -> int:
    async with AsyncSessionLocal() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(SignalRow)
                .where(SignalRow.status == "NEW"),
            )
            or 0,
        )


async def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-telegram", action="store_true")
    args = parser.parse_args()

    result = await run_signal_pipeline(notify_telegram=not args.no_telegram)
    new_total = await _count_new_signals()

    print(f"Rå signaler: {result.raw_count}")
    print(f"Efter risk: {result.approved_count}")
    print(f"Indsat i DB: {result.inserted}  (sprunget over: {result.skipped})")
    print(f"Telegram sendt: {result.telegram_sent}")
    print(f"NEW i signals (total): {new_total}")
    print(f"Bankroll: ${settings.bankroll_usd:,.0f}")

    if result.signal_ids:
        print(f"Nye signal-ids: {list(result.signal_ids)}")

    print("\nrun_signal_pipeline: ok")


if __name__ == "__main__":
    asyncio.run(main())
