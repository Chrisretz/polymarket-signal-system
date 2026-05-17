"""Gem strategi-signaler i signals-tabellen."""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from sqlalchemy import select

from pss.db.models import Signal as SignalRow
from pss.db.session import AsyncSessionLocal
from pss.strategies.base import Signal as TradeSignal

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PersistedSignal:
    trade: TradeSignal
    signal_id: int


def _to_row(sig: TradeSignal) -> SignalRow:
    sizing = sig.metadata.get("sizing", {})
    kelly = sizing.get("applied_fraction") if isinstance(sizing, dict) else None
    return SignalRow(
        market_id=sig.market_id,
        strategy=sig.strategy,
        side=sig.side,
        market_price=sig.market_price,
        fair_value_estimate=sig.fair_value_estimate,
        edge_pct=sig.edge_pct,
        confidence=sig.confidence,
        suggested_size_usd=sig.suggested_size_usd,
        kelly_fraction=kelly,
        exit_price_target=sig.exit_price_target,
        exit_date_target=sig.exit_date_target,
        exit_conditions=sig.exit_conditions or None,
        status="NEW",
        signal_metadata=sig.metadata,
    )


async def persist_signals(
    signals: list[TradeSignal],
    *,
    skip_existing_new: bool = True,
) -> tuple[int, int, list[PersistedSignal]]:
    """Indsæt signaler. Returnerer (indsat, sprunget_over, nyindsatte med id)."""
    inserted = 0
    skipped = 0
    created: list[PersistedSignal] = []

    async with AsyncSessionLocal() as session:
        for sig in signals:
            if skip_existing_new:
                exists = await session.scalar(
                    select(SignalRow.id)
                    .where(
                        SignalRow.market_id == sig.market_id,
                        SignalRow.strategy == sig.strategy,
                        SignalRow.status == "NEW",
                    )
                    .limit(1),
                )
                if exists is not None:
                    skipped += 1
                    continue

            row = _to_row(sig)
            session.add(row)
            await session.flush()
            created.append(PersistedSignal(trade=sig, signal_id=row.id))
            inserted += 1

        if inserted:
            await session.commit()

    logger.info("signals_persisted", inserted=inserted, skipped=skipped)
    return inserted, skipped, created
