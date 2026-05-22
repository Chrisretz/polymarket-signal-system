"""CRUD for Tracked Market Groups."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload

from pss.clients.gamma import GammaClient
from pss.db.models import (
    Market,
    TrackedGroup,
    TrackedGroupEvent,
    TrackedGroupMarket,
    TrackedGroupRelation,
)
from pss.db.session import AsyncSessionLocal
from pss.ingestion.market_discovery import _market_values
from pss.tracking.market_refs import (
    EventUrlError,
    parse_market_reference,
    resolve_event_from_reference,
)
from pss.tracking.prices import VALID_OUTCOME_SIDES
from pss.tracking.relations import validate_relation_definition

logger = structlog.get_logger(__name__)

LEGACY_EVENT_TITLE = "Imported markets (legacy)"

# Re-export for tests og API-konsistens
__all__ = [
    "EventUrlError",
    "GroupDetail",
    "GroupEventDetail",
    "GroupEventSummary",
    "GroupMarketRow",
    "GroupSummary",
    "add_event_to_group",
    "add_market_to_event",
    "add_market_to_group",
    "add_markets_to_event",
    "add_relation",
    "create_group",
    "ensure_market_in_db",
    "get_group",
    "list_events_in_group",
    "list_groups",
    "parse_market_reference",
    "remove_event_from_group",
    "remove_market_from_group",
    "remove_relation",
    "set_group_status",
    "update_group",
]


def _legacy_event_id(group_id: int) -> str:
    return f"legacy-{group_id}"


def _legacy_event_slug(group_id: int) -> str:
    return f"legacy-import-{group_id}"


@dataclass(frozen=True, slots=True)
class GroupSummary:
    id: int
    name: str
    description: str | None
    status: str
    event_count: int
    market_count: int
    relation_count: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class GroupMarketRow:
    id: int
    group_event_id: int | None
    market_id: int
    role_label: str
    outcome_side: str
    condition_id: str
    question: str


@dataclass(frozen=True, slots=True)
class GroupEventSummary:
    id: int
    event_id: str
    event_title: str
    event_slug: str
    market_count: int
    added_at: datetime


@dataclass(frozen=True, slots=True)
class GroupEventDetail:
    id: int
    event_id: str
    event_title: str
    event_slug: str
    added_at: datetime
    markets: list[GroupMarketRow]


@dataclass(frozen=True, slots=True)
class GroupDetail:
    id: int
    name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    events: list[GroupEventDetail]
    markets: list[GroupMarketRow]
    relations: list[tuple[int, str, dict[str, Any]]]


def _market_row(gm: TrackedGroupMarket) -> GroupMarketRow:
    return GroupMarketRow(
        id=gm.id,
        group_event_id=gm.group_event_id,
        market_id=gm.market_id,
        role_label=gm.role_label,
        outcome_side=gm.outcome_side,
        condition_id=gm.market.condition_id,
        question=gm.market.question,
    )


async def _get_or_create_legacy_event(session, group_id: int) -> TrackedGroupEvent:
    row = await session.scalar(
        select(TrackedGroupEvent).where(
            TrackedGroupEvent.group_id == group_id,
            TrackedGroupEvent.event_id == _legacy_event_id(group_id),
        ),
    )
    if row is not None:
        return row

    row = TrackedGroupEvent(
        group_id=group_id,
        event_id=_legacy_event_id(group_id),
        event_title=LEGACY_EVENT_TITLE,
        event_slug=_legacy_event_slug(group_id),
    )
    session.add(row)
    await session.flush()
    return row


async def ensure_market_in_db(
    reference: str,
    *,
    gamma: GammaClient | None = None,
) -> Market:
    """Hent marked fra Gamma og upsert i markets; returner ORM-række."""
    kind, value = parse_market_reference(reference)
    if kind == "event_slug":
        raise EventUrlError(value)

    async def _fetch(client: GammaClient) -> dict[str, Any]:
        if kind == "condition_id":
            data = await client.get_market(value)
            if not data:
                raise ValueError(f"Marked ikke fundet for condition_id: {value}")
            return data
        try:
            data = await client.get_market_by_slug(value)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise ValueError(
                    f"Marked ikke fundet for slug '{value}'. "
                    "Tjek at linket peger på et specifikt outcome/marked — "
                    "ikke kun et event (se /market/ eller vælg outcome på Polymarket).",
                ) from exc
            raise
        if not data:
            raise ValueError(
                f"Marked ikke fundet for slug '{value}'. "
                "Tjek at linket peger på et specifikt outcome/marked.",
            )
        return data

    if gamma is not None:
        gamma_data = await _fetch(gamma)
    else:
        async with GammaClient() as client:
            gamma_data = await _fetch(client)

    values = _market_values(gamma_data)
    if values is None:
        raise ValueError("Gamma-marked mangler condition_id, question eller token IDs")

    async with AsyncSessionLocal() as session:
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
        await session.commit()

        row = await session.scalar(
            select(Market).where(Market.condition_id == values["condition_id"]),
        )
        if row is None:
            raise RuntimeError("Market upsert failed")
        return row


async def create_group(
    name: str,
    *,
    description: str | None = None,
) -> int:
    async with AsyncSessionLocal() as session:
        group = TrackedGroup(name=name.strip(), description=description)
        session.add(group)
        await session.commit()
        await session.refresh(group)
        logger.info("tracked_group_created", group_id=group.id, name=name)
        return group.id


async def list_groups(*, status: str | None = "active") -> list[GroupSummary]:
    async with AsyncSessionLocal() as session:
        q = select(TrackedGroup).options(
            selectinload(TrackedGroup.markets),
            selectinload(TrackedGroup.group_events),
            selectinload(TrackedGroup.relations),
        )
        if status:
            q = q.where(TrackedGroup.status == status)
        q = q.order_by(TrackedGroup.created_at.desc())
        groups = (await session.execute(q)).scalars().all()

        return [
            GroupSummary(
                id=g.id,
                name=g.name,
                description=g.description,
                status=g.status,
                event_count=len(g.group_events),
                market_count=len(g.markets),
                relation_count=len(g.relations),
                created_at=g.created_at,
            )
            for g in groups
        ]


async def get_group(group_id: int) -> GroupDetail | None:
    async with AsyncSessionLocal() as session:
        group = await session.scalar(
            select(TrackedGroup)
            .where(TrackedGroup.id == group_id)
            .options(
                selectinload(TrackedGroup.group_events)
                .selectinload(TrackedGroupEvent.markets)
                .selectinload(TrackedGroupMarket.market),
                selectinload(TrackedGroup.markets).selectinload(TrackedGroupMarket.market),
                selectinload(TrackedGroup.relations),
            ),
        )
        if group is None:
            return None

        events = [
            GroupEventDetail(
                id=ev.id,
                event_id=ev.event_id,
                event_title=ev.event_title,
                event_slug=ev.event_slug,
                added_at=ev.added_at,
                markets=[_market_row(gm) for gm in ev.markets],
            )
            for ev in sorted(group.group_events, key=lambda e: e.added_at)
        ]
        markets = [_market_row(gm) for gm in group.markets]
        relations = [(r.id, r.relation_type, r.definition) for r in group.relations]

        return GroupDetail(
            id=group.id,
            name=group.name,
            description=group.description,
            status=group.status,
            created_at=group.created_at,
            updated_at=group.updated_at,
            events=events,
            markets=markets,
            relations=relations,
        )


async def list_events_in_group(group_id: int) -> list[GroupEventSummary]:
    async with AsyncSessionLocal() as session:
        group = await session.get(TrackedGroup, group_id)
        if group is None:
            raise ValueError(f"Gruppe {group_id} findes ikke")

        rows = (
            await session.execute(
                select(
                    TrackedGroupEvent,
                    func.count(TrackedGroupMarket.id).label("market_count"),
                )
                .outerjoin(
                    TrackedGroupMarket,
                    TrackedGroupMarket.group_event_id == TrackedGroupEvent.id,
                )
                .where(TrackedGroupEvent.group_id == group_id)
                .group_by(TrackedGroupEvent.id)
                .order_by(TrackedGroupEvent.added_at),
            )
        ).all()

        return [
            GroupEventSummary(
                id=ev.id,
                event_id=ev.event_id,
                event_title=ev.event_title,
                event_slug=ev.event_slug,
                market_count=int(market_count or 0),
                added_at=ev.added_at,
            )
            for ev, market_count in rows
        ]


async def add_event_to_group(group_id: int, event_url_or_id: str) -> int:
    """Hent event metadata fra Gamma og opret tracked_group_events."""
    event_data = await resolve_event_from_reference(event_url_or_id)
    event_id = str(event_data.event_id or event_data.event_slug)
    title = (event_data.title or event_data.event_slug or event_id).strip()
    slug = event_data.event_slug or event_id

    async with AsyncSessionLocal() as session:
        group = await session.get(TrackedGroup, group_id)
        if group is None:
            raise ValueError(f"Gruppe {group_id} findes ikke")

        existing = await session.scalar(
            select(TrackedGroupEvent.id).where(
                TrackedGroupEvent.group_id == group_id,
                TrackedGroupEvent.event_id == event_id,
            ),
        )
        if existing is not None:
            raise ValueError(f"Event '{title}' er allerede i gruppen")

        existing_slug = await session.scalar(
            select(TrackedGroupEvent.id).where(
                TrackedGroupEvent.group_id == group_id,
                TrackedGroupEvent.event_slug == slug,
            ),
        )
        if existing_slug is not None:
            raise ValueError(f"Event med slug '{slug}' er allerede i gruppen")

        row = TrackedGroupEvent(
            group_id=group_id,
            event_id=event_id,
            event_title=title,
            event_slug=slug,
        )
        session.add(row)
        group.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(row)
        logger.info(
            "tracked_group_event_added",
            group_id=group_id,
            group_event_id=row.id,
            event_slug=slug,
        )
        return row.id


async def remove_event_from_group(group_id: int, group_event_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        row = await session.scalar(
            select(TrackedGroupEvent).where(
                TrackedGroupEvent.id == group_event_id,
                TrackedGroupEvent.group_id == group_id,
            ),
        )
        if row is None:
            return False
        await session.delete(row)
        group = await session.get(TrackedGroup, group_id)
        if group:
            group.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return True


async def update_group(
    group_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
) -> bool:
    async with AsyncSessionLocal() as session:
        group = await session.get(TrackedGroup, group_id)
        if group is None:
            return False
        if name is not None:
            group.name = name.strip()
        if description is not None:
            group.description = description
        group.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return True


async def set_group_status(group_id: int, status: str) -> bool:
    if status not in ("active", "closed"):
        raise ValueError("status skal være 'active' eller 'closed'")
    async with AsyncSessionLocal() as session:
        group = await session.get(TrackedGroup, group_id)
        if group is None:
            return False
        group.status = status
        group.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return True


async def add_market_to_event(
    group_event_id: int,
    reference: str,
    role_label: str,
    *,
    outcome_side: str = "yes",
) -> int:
    """Tilføj marked under et specifikt event i gruppen."""
    role = role_label.strip()
    if not role:
        raise ValueError("role_label må ikke være tom")
    side = outcome_side.strip().lower()
    if side not in VALID_OUTCOME_SIDES:
        raise ValueError("outcome_side skal være 'yes' eller 'no'")

    market = await ensure_market_in_db(reference)

    async with AsyncSessionLocal() as session:
        group_event = await session.scalar(
            select(TrackedGroupEvent).where(TrackedGroupEvent.id == group_event_id),
        )
        if group_event is None:
            raise ValueError(f"Group event {group_event_id} findes ikke")

        group_id = group_event.group_id
        group = await session.get(TrackedGroup, group_id)
        if group is None:
            raise ValueError(f"Gruppe {group_id} findes ikke")

        existing_role = await session.scalar(
            select(TrackedGroupMarket.id).where(
                TrackedGroupMarket.group_id == group_id,
                TrackedGroupMarket.role_label == role,
            ),
        )
        if existing_role is not None:
            raise ValueError(f"role_label '{role}' findes allerede i gruppen")

        existing_row = await session.scalar(
            select(TrackedGroupMarket.id).where(
                TrackedGroupMarket.group_id == group_id,
                TrackedGroupMarket.market_id == market.id,
                TrackedGroupMarket.outcome_side == side,
            ),
        )
        if existing_row is not None:
            raise ValueError(
                f"Marked {market.condition_id} med outcome_side={side} er allerede i gruppen",
            )

        row = TrackedGroupMarket(
            group_id=group_id,
            group_event_id=group_event_id,
            market_id=market.id,
            role_label=role,
            outcome_side=side,
        )
        session.add(row)
        group.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(row)
        logger.info(
            "tracked_group_market_added",
            group_id=group_id,
            group_event_id=group_event_id,
            market_id=market.id,
            role=role,
        )
        return row.id


async def add_markets_to_event(
    group_event_id: int,
    entries: list[tuple[str, str, str]],
) -> list[int]:
    """Bulk-tilføj markeder: [(reference, role_label, outcome_side), ...]."""
    ids: list[int] = []
    for reference, role_label, outcome_side in entries:
        row_id = await add_market_to_event(
            group_event_id,
            reference,
            role_label,
            outcome_side=outcome_side,
        )
        ids.append(row_id)
    return ids


async def add_market_to_group(
    group_id: int,
    reference: str,
    role_label: str,
    *,
    outcome_side: str = "yes",
) -> int:
    """Bagudkompatibel: tilføj marked via legacy event for gruppen."""
    async with AsyncSessionLocal() as session:
        group = await session.get(TrackedGroup, group_id)
        if group is None:
            raise ValueError(f"Gruppe {group_id} findes ikke")
        legacy = await _get_or_create_legacy_event(session, group_id)
        group_event_id = legacy.id
        await session.commit()

    return await add_market_to_event(
        group_event_id,
        reference,
        role_label,
        outcome_side=outcome_side,
    )


async def remove_market_from_group(group_id: int, tracked_market_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        row = await session.scalar(
            select(TrackedGroupMarket).where(
                TrackedGroupMarket.id == tracked_market_id,
                TrackedGroupMarket.group_id == group_id,
            ),
        )
        if row is None:
            return False
        await session.delete(row)
        group = await session.get(TrackedGroup, group_id)
        if group:
            group.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return True


async def add_relation(
    group_id: int,
    relation_type: str,
    definition: dict[str, Any],
) -> int:
    validate_relation_definition(relation_type, definition)

    async with AsyncSessionLocal() as session:
        group = await session.get(TrackedGroup, group_id)
        if group is None:
            raise ValueError(f"Gruppe {group_id} findes ikke")

        row = TrackedGroupRelation(
            group_id=group_id,
            relation_type=relation_type,
            definition=definition,
        )
        session.add(row)
        group.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(row)
        return row.id


async def remove_relation(group_id: int, relation_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        row = await session.scalar(
            select(TrackedGroupRelation).where(
                TrackedGroupRelation.id == relation_id,
                TrackedGroupRelation.group_id == group_id,
            ),
        )
        if row is None:
            return False
        await session.delete(row)
        group = await session.get(TrackedGroup, group_id)
        if group:
            group.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return True
