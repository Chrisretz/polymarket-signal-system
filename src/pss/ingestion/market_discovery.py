"""Periodic job: opdager nye markeder og opdaterer metadata."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.dialects.postgresql import insert

from pss.clients.gamma import GammaClient
from pss.db.models import Market
from pss.db.session import AsyncSessionLocal

logger = structlog.get_logger(__name__)


def classify_vertical(market: dict[str, Any]) -> str:
    """Klassificér marked til vertikal for strategi-routing."""
    question = (market.get("question") or market.get("title") or "").lower()
    category = (market.get("category") or "").lower()

    macro_keywords = [
        "fed",
        "fomc",
        "ecb",
        "interest rate",
        "inflation",
        "cpi",
        "gdp",
        "unemployment",
    ]
    eu_keywords = [
        "eu ",
        "european",
        "germany",
        "france",
        "denmark",
        "uk election",
        "brexit",
    ]
    us_pol_keywords = ["trump", "biden", "harris", "congress", "senate", "house of rep"]
    sports_keywords = [
        "nfl",
        "nba",
        "soccer",
        "world cup",
        "champions league",
        "premier league",
    ]
    crypto_keywords = ["bitcoin", "btc", "ethereum", "eth", "solana", "crypto"]

    if any(k in question for k in macro_keywords):
        return "macro"
    if any(k in question for k in eu_keywords):
        return "eu_politics"
    if any(k in question for k in us_pol_keywords):
        return "us_politics"
    if any(k in question for k in sports_keywords) or "sports" in category:
        return "sports"
    if any(k in question for k in crypto_keywords) or "crypto" in category:
        return "crypto"
    return "other"


def _parse_clob_token_ids(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t) for t in raw]
    if isinstance(raw, str):
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(t) for t in parsed]
    return []


def _parse_end_date(raw: Any) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _market_values(m: dict[str, Any]) -> dict[str, Any] | None:
    """Map Gamma API-marked til DB-række; None hvis markedet skal springes over."""
    condition_id = m.get("conditionId")
    question = m.get("question") or m.get("title")
    clob_tokens = _parse_clob_token_ids(m.get("clobTokenIds"))

    if not condition_id or not question or len(clob_tokens) < 2:
        return None

    return {
        "condition_id": condition_id,
        "question": question,
        "description": m.get("description"),
        "slug": m.get("slug"),
        "category": m.get("category"),
        "event_id": m.get("eventId"),
        "yes_token_id": clob_tokens[0],
        "no_token_id": clob_tokens[1],
        "end_date": _parse_end_date(m.get("endDate")),
        "minimum_tick_size": m.get("minimumTickSize"),
        "neg_risk": bool(m.get("negRisk", False)),
        "is_active": bool(m.get("active", True)),
        "is_closed": bool(m.get("closed", False)),
        "primary_vertical": classify_vertical(m),
        "raw_metadata": m,
        "updated_at": datetime.now(timezone.utc),
    }


async def discover_markets() -> int:
    """Henter alle aktive markeder og upserter i database.

    Returns:
        Antal markeder behandlet (indsat/opdateret).
    """
    count = 0
    skipped = 0

    async with GammaClient() as gamma:
        markets = await gamma.list_all_active_markets()

        async with AsyncSessionLocal() as session:
            for m in markets:
                try:
                    values = _market_values(m)
                    if values is None:
                        skipped += 1
                        continue

                    stmt = insert(Market).values(**values)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["condition_id"],
                        set_={
                            "question": stmt.excluded.question,
                            "description": stmt.excluded.description,
                            "slug": stmt.excluded.slug,
                            "category": stmt.excluded.category,
                            "event_id": stmt.excluded.event_id,
                            "yes_token_id": stmt.excluded.yes_token_id,
                            "no_token_id": stmt.excluded.no_token_id,
                            "end_date": stmt.excluded.end_date,
                            "minimum_tick_size": stmt.excluded.minimum_tick_size,
                            "neg_risk": stmt.excluded.neg_risk,
                            "is_active": stmt.excluded.is_active,
                            "is_closed": stmt.excluded.is_closed,
                            "primary_vertical": stmt.excluded.primary_vertical,
                            "raw_metadata": stmt.excluded.raw_metadata,
                            "updated_at": stmt.excluded.updated_at,
                        },
                    )
                    await session.execute(stmt)
                    count += 1
                except Exception as exc:
                    logger.warning(
                        "market_discovery_skip",
                        market=m.get("conditionId"),
                        error=str(exc),
                    )
                    skipped += 1

            await session.commit()

    logger.info("market_discovery_complete", processed=count, skipped=skipped)
    return count
