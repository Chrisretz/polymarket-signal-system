"""Offentlige Polymarket-links til markeder."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

POLYMARKET_EVENT_BASE = "https://polymarket.com/event"


def resolve_market_slug(
    *,
    slug: str | None,
    raw_metadata: dict[str, Any] | None = None,
) -> str | None:
    """Markeds-slug fra DB eller Gamma raw_metadata (ikke event-slug)."""
    if slug and str(slug).strip():
        return str(slug).strip()
    if not raw_metadata:
        return None
    for key in ("slug", "market_slug"):
        value = raw_metadata.get(key)
        if value and str(value).strip():
            return str(value).strip()
    return None


def resolve_event_slug(raw_metadata: dict[str, Any] | None) -> str | None:
    """Event-slug for multi-outcome (neg-risk) markeder."""
    if not raw_metadata:
        return None
    for key in ("eventSlug",):
        value = raw_metadata.get(key)
        if value and str(value).strip():
            return str(value).strip()
    events = raw_metadata.get("events")
    if isinstance(events, list) and events:
        first = events[0]
        if isinstance(first, dict):
            ev_slug = first.get("slug") or first.get("eventSlug")
            if ev_slug and str(ev_slug).strip():
                return str(ev_slug).strip()
    return None


def _event_path(event_slug: str, market_slug: str | None) -> str:
    event_slug = event_slug.removeprefix("/").removeprefix("event/")
    if market_slug and market_slug != event_slug:
        market_slug = market_slug.removeprefix("/").removeprefix("event/")
        return f"{event_slug}/{market_slug}"
    return event_slug


def polymarket_market_url(
    *,
    slug: str | None = None,
    raw_metadata: dict[str, Any] | None = None,
    question: str | None = None,
) -> str | None:
    """Direkte link til marked på polymarket.com."""
    market_slug = resolve_market_slug(slug=slug, raw_metadata=raw_metadata)
    event_slug = resolve_event_slug(raw_metadata)

    if event_slug:
        if event_slug.startswith("http://") or event_slug.startswith("https://"):
            return event_slug
        path = _event_path(event_slug, market_slug)
        return f"{POLYMARKET_EVENT_BASE}/{path}"

    if market_slug:
        if market_slug.startswith("http://") or market_slug.startswith("https://"):
            return market_slug
        path = market_slug.removeprefix("/").removeprefix("event/")
        return f"{POLYMARKET_EVENT_BASE}/{path}"

    if question and question.strip():
        return f"https://polymarket.com/search?_q={quote(question.strip()[:120])}"
    return None
