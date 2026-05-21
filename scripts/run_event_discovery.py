"""Kør event discovery én gang (Strategi C Fase 1)."""

from __future__ import annotations

import asyncio
import sys

from pss.events.discovery import discover_events


async def main() -> None:
    count = await discover_events()
    print(f"Events processed: {count}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
