"""Telegram alerts via python-telegram-bot."""

from __future__ import annotations

import structlog
from telegram import Bot
from telegram.error import TelegramError

from pss.config import settings

logger = structlog.get_logger(__name__)


class TelegramNotConfiguredError(RuntimeError):
    """TELEGRAM_BOT_TOKEN eller TELEGRAM_CHAT_ID mangler i .env."""


def _require_telegram_config() -> tuple[str, str]:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        raise TelegramNotConfiguredError(
            "Sæt TELEGRAM_BOT_TOKEN og TELEGRAM_CHAT_ID i .env.\n"
            "1. Opret bot: @BotFather → /newbot → kopier token\n"
            "2. Start en chat med din bot (Send /start)\n"
            "3. Find chat_id: @userinfobot eller GET getUpdates på bot API"
        )
    return (
        settings.telegram_bot_token.get_secret_value(),
        settings.telegram_chat_id,
    )


async def send_telegram_message(
    text: str,
    *,
    parse_mode: str | None = None,
    disable_notification: bool = False,
) -> int:
    """Send besked til konfigureret chat. Returnerer Telegram message_id."""
    token, chat_id = _require_telegram_config()
    try:
        async with Bot(token) as bot:
            message = await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                disable_notification=disable_notification,
            )
    except TelegramError as exc:
        logger.error("telegram_send_failed", error=str(exc))
        raise

    message_id = message.message_id
    logger.info("telegram_sent", chat_id=chat_id, message_id=message_id)
    return message_id


async def send_alert(title: str, body: str) -> int:
    """Send formateret alert (plain text, ingen Markdown)."""
    text = f"[PSS] {title}\n\n{body}" if title else body
    return await send_telegram_message(text)
