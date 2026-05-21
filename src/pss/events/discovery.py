"""Discover Polymarket events med multi-leg struktur (Strategi C Fase 1)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.dialects.postgresql import insert

from pss.clients.gamma import GammaClient
from pss.db.models import Event
from pss.db.session import AsyncSessionLocal

logger = structlog.get_logger(__name__)

MIN_LEG_COUNT = 3


def _parse_end_date(raw: Any) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _is_neg_risk_event(event: dict[str, Any]) -> bool:
    """Gamma bruger enableNegRisk på events; markeder har negRisk."""
    return bool(
        event.get("negRisk")
        or event.get("enableNegRisk")
        or event.get("negRiskAugmented"),
    )


def _event_values(event: dict[str, Any]) -> dict[str, Any] | None:
    """Map Gamma event til DB-række; None hvis eventet ikke opfylder kriterier."""
    event_markets = event.get("markets") or []
    if len(event_markets) < MIN_LEG_COUNT:
        return None
    if not _is_neg_risk_event(event):
        return None

    external_id = event.get("id")
    title = event.get("title")
    if external_id is None or not title:
        return None

    return {
        "event_id": str(external_id),
        "title": title,
        "description": event.get("description"),
        "slug": event.get("slug"),
        "end_date": _parse_end_date(event.get("endDate")),
        "is_active": bool(event.get("active", True)),
        "is_resolved": bool(event.get("closed", False)),
        "neg_risk": True,
        "raw_metadata": event,
        "updated_at": datetime.now(timezone.utc),
    }


async def discover_events() -> int:
    """Find aktive neg_risk events med 3+ ben og upsert til events-tabellen.

    Join-key til markets: ``markets.event_id = events.event_id`` (Polymarket
    ekstern identifier, TEXT).

    Returns:
        Antal events behandlet (indsat/opdateret).
    """
    count = 0
    skipped = 0

    async with GammaClient() as gamma:
        events = await gamma.list_all_active_events()

        async with AsyncSessionLocal() as session:
            for event in events:
                try:
                    values = _event_values(event)
                    if values is None:
                        skipped += 1
                        continue

                    stmt = insert(Event).values(**values)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["event_id"],
                        set_={
                            "title": stmt.excluded.title,
                            "description": stmt.excluded.description,
                            "slug": stmt.excluded.slug,
                            "end_date": stmt.excluded.end_date,
                            "is_active": stmt.excluded.is_active,
                            "is_resolved": stmt.excluded.is_resolved,
                            "neg_risk": stmt.excluded.neg_risk,
                            "raw_metadata": stmt.excluded.raw_metadata,
                            "updated_at": stmt.excluded.updated_at,
                        },
                    )
                    await session.execute(stmt)
                    count += 1
                except Exception as exc:
                    logger.warning(
                        "event_discovery_skip",
                        event_id=event.get("id"),
                        error=str(exc),
                    )
                    skipped += 1

            await session.commit()

    logger.info("event_discovery_complete", processed=count, skipped=skipped)
    return count
