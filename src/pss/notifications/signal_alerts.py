"""Telegram ved nye handelssignaler."""

from __future__ import annotations

import html

import structlog

from pss.config import settings
from pss.markets.urls import polymarket_market_url
from pss.notifications.telegram import TelegramNotConfiguredError, send_telegram_message
from pss.strategies.base import Signal as TradeSignal

logger = structlog.get_logger(__name__)


def format_signal_message(sig: TradeSignal, signal_id: int) -> tuple[str, str | None]:
    """Telegram-tekst og valgfri parse_mode (HTML hvis link)."""
    question = str(sig.metadata.get("question", ""))[:300]
    category = sig.metadata.get("base_rate_category", "—")
    yes_price = sig.metadata.get("yes_price")
    yes_line = f"Ja-pris (marked): {float(yes_price):.3f}\n" if yes_price is not None else ""

    url = sig.metadata.get("polymarket_url")
    if not url or not isinstance(url, str):
        url = polymarket_market_url(
            slug=sig.metadata.get("market_slug") if isinstance(sig.metadata.get("market_slug"), str) else None,
            question=question,
        )

    lines = [
        f"Signal #{signal_id}",
        f"Strategi: {sig.strategy}",
        f"{sig.side}  |  edge {sig.edge_pct:.1%}  |  ${sig.suggested_size_usd:,.0f}",
        f"Kategori: {category}",
        yes_line.rstrip(),
        f"Købspris (side): {sig.market_price:.3f}  fair: {sig.fair_value_estimate:.3f}",
        "",
        question,
    ]
    plain = "\n".join(line for line in lines if line is not None)

    if not url:
        return plain, None

    safe_q = html.escape(question)
    safe_url = html.escape(url, quote=True)
    html_body = (
        f"<b>Signal #{signal_id}</b>\n"
        f"Strategi: {html.escape(str(sig.strategy))}\n"
        f"{html.escape(str(sig.side))}  |  edge {sig.edge_pct:.1%}  |  "
        f"${sig.suggested_size_usd:,.0f}\n"
        f"Kategori: {html.escape(str(category))}\n"
    )
    if yes_price is not None:
        html_body += f"Ja-pris (marked): {float(yes_price):.3f}\n"
    html_body += (
        f"Købspris: {sig.market_price:.3f}  fair: {sig.fair_value_estimate:.3f}\n\n"
        f"{safe_q}\n\n"
        f'<a href="{safe_url}">Åbn marked på Polymarket</a>'
    )
    return html_body, "HTML"


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
        body, parse_mode = format_signal_message(sig, signal_id)
        title = "Nyt signal"
        text = f"[PSS] {title}\n\n{body}" if title else body
        await send_telegram_message(text, parse_mode=parse_mode)
        sent += 1

    logger.info("telegram_signals_sent", count=sent)
    return sent
