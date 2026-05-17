"""Sæt has_base_rate på markeder med classifier-match (Uge 4, Dag 5)."""

from __future__ import annotations

import argparse
import asyncio
import sys

from pss.base_rates.apply_flags import apply_has_base_rate_flags, count_flagged


async def main() -> None:
    parser = argparse.ArgumentParser(description="Opdater markets.has_base_rate fra classifier.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Vis kun hvad der ville ændres — skriv ikke til DB.",
    )
    args = parser.parse_args()

    before_flagged, before_total = await count_flagged()
    print(f"Før: has_base_rate=true → {before_flagged} / {before_total} (macro + eu_politics)")

    stats = await apply_has_base_rate_flags(dry_run=args.dry_run)

    after_flagged, after_total = await count_flagged()
    if not args.dry_run:
        print(f"Efter: has_base_rate=true → {after_flagged} / {after_total}")

    print(
        f"\nScannet: {stats['scanned']}\n"
        f"  Sat til true:  {stats['set_true']}\n"
        f"  Sat til false: {stats['set_false']}\n"
        f"  Uændret true:  {stats['unchanged_true']}\n"
        f"  Uændret false: {stats['unchanged_false']}",
    )

    if args.dry_run:
        print("\n(dry-run — ingen DB-ændringer)")
    else:
        if stats["set_true"] + stats["unchanged_true"] == 0 and stats["scanned"] > 0:
            print("\nAdvarsel: ingen markeder flagged.", file=sys.stderr)
            raise SystemExit(1)

    print("\napply_base_rate_flags: ok")


if __name__ == "__main__":
    asyncio.run(main())
