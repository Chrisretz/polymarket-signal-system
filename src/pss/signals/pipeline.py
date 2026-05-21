"""Fuld signal-pipeline: scan → risk → persist → Telegram."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import structlog

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
    """Strategi A fjernet — pipeline deaktiveret indtil Strategi C (Fase 2+)."""
    _ = notify_telegram
    msg = "signal_pipeline_disabled: Strategi A (base_rate_fade) fjernet; Strategi C ikke implementeret endnu"
    logger.warning("signal_pipeline_disabled")
    raise NotImplementedError(msg)
