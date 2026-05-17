"""Telegram ved nye handelssignaler."""

from __future__ import annotations

import structlog

from pss.config import settings
from pss.notifications.telegram import TelegramNotConfiguredError, send_alert
from pss.strategies.base import Signal as TradeSignal

logger = structlog.get_logger(__name__)


def format_signal_message(sig: TradeSignal, signal_id: int) -> str:
    """Plain-text besked til Telegram."""
    question = str(sig.metadata.get("question", ""))[:300]
    category = sig.metadata.get("base_rate_category", "—")
    yes_price = sig.metadata.get("yes_price")
    yes_line = f"Ja-pris (marked): {float(yes_price):.3f}\n" if yes_price is not None else ""

    return (
        f"Signal #{signal_id}\n"
        f"Strategi: {sig.strategy}\n"
        f"{sig.side}  |  edge {sig.edge_pct:.1%}  |  ${sig.suggested_size_usd:,.0f}\n"
        f"Kategori: {category}\n"
        f"{yes_line}"
        f"Købspris (side): {sig.market_price:.3f}  fair: {sig.fair_value_estimate:.3f}\n"
        f"\n{question}"
    )


async def notify_new_signals(
    items: list[tuple[TradeSignal, int]],
    *,
    skip_if_unconfigured: bool = True,
) -> int:
    """Send Telegram for hvert nyt signal. Returnerer antal beskeder sendt."""
    if not items:
        return 0

    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        if skip_if_unconfigured:
            logger.warning("telegram_skipped", reason="not_configured", count=len(items))
            return 0
        raise TelegramNotConfiguredError()

    sent = 0
    for sig, signal_id in items:
        body = format_signal_message(sig, signal_id)
        await send_alert("Nyt signal", body)
        sent += 1

    logger.info("telegram_signals_sent", count=sent)
    return sent
