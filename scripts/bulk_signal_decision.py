"""Sæt mange NEW-signaler til REJECTED eller EXPIRED (uge 6 review)."""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from pss.db.models import Signal as SignalRow
from pss.db.session import AsyncSessionLocal


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "signal_ids",
        type=int,
        nargs="+",
        help="Signal-ids (fx 10 11 12 13)",
    )
    parser.add_argument(
        "--status",
        choices=("REJECTED", "EXPIRED"),
        default="REJECTED",
    )
    parser.add_argument("--reason", default="manual_review_week6")
    args = parser.parse_args()

    updated = 0
    async with AsyncSessionLocal() as session:
        for sid in args.signal_ids:
            sig = await session.get(SignalRow, sid)
            if sig is None:
                print(f"  #{sid}: findes ikke")
                continue
            if sig.status != "NEW":
                print(f"  #{sid}: status={sig.status!r} (sprunget over)")
                continue
            sig.status = args.status
            sig.rejected_reason = args.reason
            updated += 1
            print(f"  #{sid} → {args.status}")

        if updated:
            await session.commit()

    print(f"\nOpdateret: {updated}")
    print("bulk_signal_decision: ok")


if __name__ == "__main__":
    asyncio.run(main())
