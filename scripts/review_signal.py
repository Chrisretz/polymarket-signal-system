"""Vis ét signal til manuelt review (fx sammen i chat)."""

from __future__ import annotations

import argparse
import asyncio

from pss.journal.review import build_review_card


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("signal_id", type=int, help="Signal-id fra list_signals")
    args = parser.parse_args()

    card = await build_review_card(args.signal_id)
    if card is None:
        print(f"Signal {args.signal_id} findes ikke.")
        return

    print(card.body)
    print("\nreview_signal: ok")


if __name__ == "__main__":
    asyncio.run(main())
