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
    """Slug fra DB eller Gamma raw_metadata."""
    if slug and str(slug).strip():
        return str(slug).strip()
    if not raw_metadata:
        return None
    for key in ("slug", "eventSlug", "market_slug"):
        value = raw_metadata.get(key)
        if value and str(value).strip():
            return str(value).strip()
    events = raw_metadata.get("events")
    if isinstance(events, list) and events:
        first = events[0]
        if isinstance(first, dict):
            ev_slug = first.get("slug") or first.get("eventSlug")
            if ev_slug:
                return str(ev_slug).strip()
    return None


def polymarket_market_url(
    *,
    slug: str | None = None,
    raw_metadata: dict[str, Any] | None = None,
    question: str | None = None,
) -> str | None:
    """Direkte link til marked på polymarket.com."""
    resolved = resolve_market_slug(slug=slug, raw_metadata=raw_metadata)
    if resolved:
        if resolved.startswith("http://") or resolved.startswith("https://"):
            return resolved
        path = resolved.removeprefix("/").removeprefix("event/")
        return f"{POLYMARKET_EVENT_BASE}/{path}"
    if question and question.strip():
        return f"https://polymarket.com/search?_q={quote(question.strip()[:120])}"
    return None
