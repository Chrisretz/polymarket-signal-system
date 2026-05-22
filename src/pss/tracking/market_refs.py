"""Parse og valider Polymarket-markedreferencer (URL, slug, condition_id)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from pss.clients.gamma import GammaClient
from pss.tracking.prices import parse_gamma_outcome_prices

_CONDITION_ID_RE = re.compile(r"^0x[a-fA-F0-9]{64}$")

EVENT_URL_HELP = (
    "Polymarket viser ofte alle outcomes på én event-side (/event/…). "
    "Indsæt event-linket her — vi henter alle underliggende markeder, "
    "så du kan vælge hvilke outcomes der skal trackes."
)


class EventUrlError(ValueError):
    """Legacy: event-link sendt til ensure_market_in_db uden market-valg."""

    def __init__(self, event_slug: str, *, title: str | None = None) -> None:
        self.event_slug = event_slug
        self.title = title
        super().__init__(EVENT_URL_HELP)


@dataclass(frozen=True, slots=True)
class EventMarketOption:
    slug: str
    question: str
    outcome_name: str
    condition_id: str | None
    yes_price_pp: float | None
    no_price_pp: float | None
    liquidity_usd: float | None


@dataclass(frozen=True, slots=True)
class EventMarketsResult:
    event_slug: str
    event_id: str | None
    title: str | None
    markets: list[EventMarketOption]


def suggest_role_label(outcome_name: str) -> str:
    """Auto-foreslå role_label fra outcome-navn (snake_case, ASCII)."""
    text = unicodedata.normalize("NFKD", outcome_name.strip().lower())
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    if not text:
        return "outcome"
    if text[0].isdigit():
        text = f"o_{text}"
    return text[:48]


def parse_market_reference(raw: str) -> tuple[str, str]:
    """Parse reference. Returnerer (kind, value).

    Kinds:
    - condition_id
    - market_slug — specifikt marked (slug, /market/ URL, eller event/…/market-slug)
    - event_slug — event-niveau (/event/{slug} uden undermarked)
    """
    text = raw.strip()
    if _CONDITION_ID_RE.match(text):
        return "condition_id", text

    if text.startswith("0x") and len(text) == 66:
        return "condition_id", text

    if "polymarket.com" in text:
        path = urlparse(text).path.strip("/")
        parts = [p for p in path.split("/") if p]
        if not parts:
            raise ValueError(f"Kunne ikke parse URL: {raw}")

        head = parts[0].lower()
        if head == "market":
            if len(parts) < 2:
                raise ValueError("Ugyldig market-URL — mangler marked-slug efter /market/")
            return "market_slug", parts[-1]

        if head == "event":
            rest = parts[1:]
            if len(rest) == 1:
                return "event_slug", rest[0]
            if len(rest) >= 2:
                return "market_slug", rest[-1]
            raise ValueError(f"Ugyldig event-URL: {raw}")

        return "market_slug", parts[-1]

    if re.match(r"^[a-z0-9-]+$", text, re.I):
        return "market_slug", text

    raise ValueError(
        "Ugyldig reference — brug event-URL (/event/…), condition_id (0x…), "
        "market-slug eller market-URL",
    )


def _outcome_name_from_market(row: dict[str, Any]) -> str:
    title = row.get("groupItemTitle")
    if title and str(title).strip():
        return str(title).strip()
    question = str(row.get("question") or "")
    if question.lower().startswith("will "):
        # "Will X be the next ..." → extract X heuristisk
        body = question[5:]
        for sep in (" be ", " win ", " become "):
            if sep in body.lower():
                idx = body.lower().index(sep)
                return body[:idx].strip()
    return question[:80] if question else str(row.get("slug") or "Outcome")


def _liquidity_usd(row: dict[str, Any]) -> float | None:
    for key in ("liquidityNum", "liquidity", "liquidityClob"):
        val = row.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return None


def _markets_from_event_payload(event: dict[str, Any], event_slug: str) -> EventMarketsResult:
    title = event.get("title") or event.get("slug") or event_slug
    event_id = event.get("id")
    if event_id is not None:
        event_id = str(event_id)

    options: list[EventMarketOption] = []
    for row in event.get("markets") or []:
        if row.get("closed") or not row.get("active", True):
            continue
        slug = row.get("slug")
        if not slug:
            continue
        yes, no = parse_gamma_outcome_prices(row)
        options.append(
            EventMarketOption(
                slug=str(slug),
                question=str(row.get("question") or slug),
                outcome_name=_outcome_name_from_market(row),
                condition_id=row.get("conditionId"),
                yes_price_pp=yes * 100 if yes is not None else None,
                no_price_pp=no * 100 if no is not None else None,
                liquidity_usd=_liquidity_usd(row),
            ),
        )
    options.sort(key=lambda m: (-(m.yes_price_pp or 0), m.outcome_name))
    return EventMarketsResult(
        event_slug=event_slug,
        event_id=event_id,
        title=title,
        markets=options,
    )


async def fetch_event_markets(event_slug_or_id: str) -> EventMarketsResult:
    """Hent alle aktive markeder under et Polymarket-event."""
    key = event_slug_or_id.strip()
    async with GammaClient() as client:
        event = await client.get_event_by_slug(key)
        if not event:
            event = await client.get_event_by_id(key)
        if not event:
            rows = await client.list_events_by_slug(key)
            event = rows[0] if rows else {}

    if not event:
        return EventMarketsResult(
            event_slug=key,
            event_id=None,
            title=None,
            markets=[],
        )

    slug = str(event.get("slug") or key)
    return _markets_from_event_payload(event, slug)


def parse_event_reference(raw: str) -> tuple[str, str]:
    """Parse event URL, slug eller numerisk Gamma event-id. Returnerer ('slug'|'id', value)."""
    text = raw.strip()
    if not text:
        raise ValueError("Event-reference må ikke være tom")

    if "polymarket.com" in text:
        kind, value = parse_market_reference(text)
        if kind != "event_slug":
            raise ValueError(
                "Forventede en event-URL (polymarket.com/event/{slug}) — "
                "ikke et enkelt marked.",
            )
        return "slug", value

    if text.isdigit():
        return "id", text

    if re.match(r"^[a-z0-9-]+$", text, re.I):
        return "slug", text

    raise ValueError(
        "Ugyldig event-reference — brug event-URL, event-slug eller numerisk event-id",
    )


async def list_event_markets(event_slug: str) -> tuple[str | None, list[EventMarketOption]]:
    """Bagudkompatibel wrapper — returnerer (title, markets)."""
    result = await fetch_event_markets(event_slug)
    return result.title, result.markets


async def resolve_event_from_reference(reference: str) -> EventMarketsResult:
    """Hent event metadata fra Gamma ud fra URL, slug eller id."""
    kind, value = parse_event_reference(reference)
    if kind == "slug":
        return await fetch_event_markets(value)
    result = await fetch_event_markets(value)
    if result.markets:
        return result
    async with GammaClient() as client:
        payload = await client.get_event_by_id(value)
    if not payload:
        raise ValueError(f"Event ikke fundet for id/slug: {value}")
    slug = str(payload.get("slug") or value)
    return _markets_from_event_payload(payload, slug)
