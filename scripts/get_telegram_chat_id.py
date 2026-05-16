"""Hent dit TELEGRAM_CHAT_ID via getUpdates (efter /start til din bot)."""

from __future__ import annotations

import asyncio
import sys

import httpx

from pss.config import settings


async def main() -> None:
    if not settings.telegram_bot_token:
        print(
            "Sæt først TELEGRAM_BOT_TOKEN i .env (fra BotFather).\n"
            "Du har allerede sendt /start til PSS Alerts — godt.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    token = settings.telegram_bot_token.get_secret_value()
    url = f"https://api.telegram.org/bot{token}/getUpdates"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()

    if not data.get("ok"):
        print(f"Telegram API fejl: {data}", file=sys.stderr)
        raise SystemExit(1)

    results = data.get("result") or []
    if not results:
        print(
            "Ingen beskeder fundet.\n"
            "1. Åbn PSS Alerts i Telegram\n"
            "2. Send /start igen\n"
            "3. Kør dette script igen",
            file=sys.stderr,
        )
        raise SystemExit(1)

    seen: set[int] = set()
    print("Fundne chat_id (brug dit eget tal i .env):\n")
    for item in results:
        message = item.get("message") or item.get("edited_message")
        if not message:
            continue
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None or chat_id in seen:
            continue
        seen.add(chat_id)
        name = chat.get("first_name") or chat.get("title") or "?"
        username = chat.get("username") or ""
        user bit = f" @{username}" if username else ""
        print(f"  TELEGRAM_CHAT_ID={chat_id}   ({name}{user_bit})")

    if len(seen) == 1:
        only = next(iter(seen))
        print(f"\nKopier til .env:\n  TELEGRAM_CHAT_ID={only}")


if __name__ == "__main__":
    asyncio.run(main())
