"""Fuld signal-pipeline: scan → risk → persist → Telegram."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import structlog

from pss.notifications.signal_alerts import notify_new_signals
from pss.notifications.telegram import TelegramNotConfiguredError
from pss.risk.pipeline import apply_risk_pipeline
from pss.signals.persist import persist_signals
from pss.strategies.base_rate_fade import BaseRateFadeStrategy

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PipelineResult:
    raw_count: int
    approved_count: int
    inserted: int
    skipped: int
    telegram_sent: int
    signal_ids: tuple[int, ...]


async def run_signal_pipeline(
    *,
    notify_telegram: bool = True,
) -> PipelineResult:
    """Kør base_rate_fade end-to-end."""
    raw = await BaseRateFadeStrategy().scan_for_signals()
    approved = await apply_risk_pipeline(raw)
    inserted, skipped, created = await persist_signals(approved)

    telegram_sent = 0
    if notify_telegram and created:
        try:
            telegram_sent = await notify_new_signals(
                [(p.trade, p.signal_id) for p in created],
            )
        except TelegramNotConfiguredError:
            logger.warning("telegram_skipped", reason="not_configured")

    result = PipelineResult(
        raw_count=len(raw),
        approved_count=len(approved),
        inserted=inserted,
        skipped=skipped,
        telegram_sent=telegram_sent,
        signal_ids=tuple(p.signal_id for p in created),
    )
    logger.info("signal_pipeline_complete", **asdict(result))
    return result
