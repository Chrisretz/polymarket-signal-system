"""Tekstuel signal-gennemgang til manuelt review."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from pss.config import settings
from pss.db.models import Market, Signal as SignalRow
from pss.db.session import AsyncSessionLocal


@dataclass(frozen=True, slots=True)
class SignalReviewCard:
    signal_id: int
    market_id: int
    question: str
    strategy: str
    side: str
    market_price: float
    fair_value: float
    edge_pct: float
    suggested_size_usd: float
    status: str
    metadata: dict
    exit_price_target: float | None
    exit_date_target: str | None
    body: str


async def build_review_card(signal_id: int) -> SignalReviewCard | None:
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                select(SignalRow, Market)
                .join(Market, Market.id == SignalRow.market_id)
                .where(SignalRow.id == signal_id),
            )
        ).one_or_none()
        if row is None:
            return None
        sig, market = row

    meta = sig.signal_metadata or {}
    lines = [
        f"Signal #{sig.id}  status={sig.status}",
        f"Marked: {market.question or '(ingen question)'}",
        f"market_id={sig.market_id}  strategy={sig.strategy}  side={sig.side}",
        "",
        "Priser / edge:",
        f"  market_price={float(sig.market_price):.4f}  fair_value={float(sig.fair_value_estimate):.4f}",
        f"  edge={float(sig.edge_pct):.2%}  confidence={sig.confidence}",
        f"  suggested_size=${float(sig.suggested_size_usd):,.0f}  (bankroll ${settings.bankroll_usd:,.0f})",
        "",
        "Base rate (fra signal_metadata):",
        f"  category={meta.get('base_rate_category')}",
        f"  base_rate_probability={meta.get('base_rate_probability')}",
        f"  deviation_pp={meta.get('deviation_pp')}",
        f"  liquidity_usd={meta.get('liquidity_usd')}",
        "",
        "Exit:",
        f"  exit_price_target={sig.exit_price_target}",
        f"  exit_date_target={sig.exit_date_target}",
        f"  exit_conditions={sig.exit_conditions}",
        "",
        "Review-spørgsmål:",
        "  • Er kategorien rigtig (ECB/BOJ kan være fejlklassificeret)?",
        "  • Er mean-reversion tesen plausibel her?",
        "  • Er likviditet og horizon OK?",
        "  • Ville du handle dette manuelt på Polymarket?",
    ]
    exit_str = sig.exit_date_target.isoformat() if sig.exit_date_target else None
    exit_price = float(sig.exit_price_target) if sig.exit_price_target is not None else None

    return SignalReviewCard(
        signal_id=sig.id,
        market_id=sig.market_id,
        question=market.question or "",
        strategy=sig.strategy,
        side=sig.side,
        market_price=float(sig.market_price),
        fair_value=float(sig.fair_value_estimate),
        edge_pct=float(sig.edge_pct),
        suggested_size_usd=float(sig.suggested_size_usd),
        status=sig.status,
        metadata=meta,
        exit_price_target=exit_price,
        exit_date_target=exit_str,
        body="\n".join(lines),
    )
