"""Send testbesked via Telegram (Uge 1, Dag 4).

Kræver TELEGRAM_BOT_TOKEN og TELEGRAM_CHAT_ID i .env.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone

from pss.config import settings
from pss.notifications.telegram import TelegramNotConfiguredError, send_telegram_message


async def main() -> None:
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        text = (
            "PSS testbesked\n"
            f"Miljø: {settings.environment}\n"
            f"Tid: {now}\n"
            "Uge 1, Dag 4 — Telegram setup OK."
        )
        message_id = await send_telegram_message(text)
    except TelegramNotConfiguredError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"Fejl ved afsendelse: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"Telegram besked sendt (message_id={message_id})")


if __name__ == "__main__":
    asyncio.run(main())
