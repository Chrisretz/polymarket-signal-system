"""Kør event snapshot én gang (Strategi C Fase 1)."""

from __future__ import annotations

import asyncio
import sys

from pss.events.snapshot import snapshot_events


async def main() -> None:
    result = await snapshot_events()
    print(f"Events snapshotted: {result.processed}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
