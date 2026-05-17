"""Uge 6 onsdag: gennemgå alle NEW-signaler (kompakt + anbefaling)."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from pss.base_rates.classifier import classify_market_fields
from pss.db.models import Market, Signal as SignalRow
from pss.db.session import AsyncSessionLocal
from pss.journal.review import build_review_card
from pss.logging_config import configure_logging


def _suggest_verdict(
    *,
    question: str,
    signal_category: str | None,
    fresh_category: str | None,
    edge_pct: float,
) -> str:
    if fresh_category != signal_category:
        return "AFVIS — klassifikation i signal matcher ikke spørgsmål (kør expire_stale + pipeline)"
    if fresh_category is None:
        return "AFVIS — ingen base-rate-kategori"
    if edge_pct > 0.35:
        return "AFVIS — edge urealistisk høj (tjek kategori / markedets pris)"
    q = question.lower()
    if "decrease" in q or "increase" in q or "cut" in q or "hike" in q:
        if fresh_category.endswith("_hold"):
            return "AFVIS — spørgsmål om cut/hike men kategori er hold"
    return "MANUEL — læs review; godkend kun hvis du ville handle på Polymarket"


async def main() -> None:
    configure_logging()
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(SignalRow, Market)
                .join(Market, Market.id == SignalRow.market_id)
                .where(SignalRow.status == "NEW")
                .order_by(SignalRow.generated_at.desc()),
            )
        ).all()

    if not rows:
        print("Ingen NEW-signaler.")
        return

    print(f"NEW-signaler: {len(rows)}\n")
    for sig, market in rows:
        meta = sig.signal_metadata or {}
        old_cat = meta.get("base_rate_category")
        fresh = classify_market_fields(
            question=market.question,
            description=market.description,
            category=market.category,
            primary_vertical=market.primary_vertical,
        )
        verdict = _suggest_verdict(
            question=market.question or "",
            signal_category=old_cat,
            fresh_category=fresh,
            edge_pct=float(sig.edge_pct),
        )
        print("=" * 72)
        print(f"Signal #{sig.id}  edge={float(sig.edge_pct):.1%}  side={sig.side}")
        print(f"  Spørgsmål: {(market.question or '')[:68]}")
        print(f"  Signal-kategori: {old_cat!r}  →  Nu classifier: {fresh!r}")
        print(f"  Anbefaling: {verdict}")
        card = await build_review_card(sig.id)
        if card:
            print()
            print(card.body)
        print()

    print("review_all_new_signals: ok")


if __name__ == "__main__":
    asyncio.run(main())
