"""Async handlinger til Tracked Groups UI (CRUD + snapshot)."""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from pss.db.models import TrackedGroup, TrackedGroupMarket
from pss.db.session import AsyncSessionLocal
from pss.tracking.groups import (
    add_market_to_group,
    add_relation,
    create_group,
    remove_market_from_group,
    remove_relation,
    set_group_status,
    update_group,
)
from pss.tracking.market_refs import fetch_event_markets, parse_market_reference
from pss.tracking.snapshot import snapshot_group

_async_loop: asyncio.AbstractEventLoop | None = None


def run_async(coro):
    """Kør async coroutine fra synkron Streamlit-kontekst (genbruger event loop)."""
    global _async_loop
    if _async_loop is None or _async_loop.is_closed():
        _async_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_async_loop)
    return _async_loop.run_until_complete(coro)


async def _load_group_orm(group_id: int) -> TrackedGroup:
    async with AsyncSessionLocal() as session:
        group = await session.scalar(
            select(TrackedGroup)
            .where(TrackedGroup.id == group_id)
            .options(
                selectinload(TrackedGroup.markets).selectinload(TrackedGroupMarket.market),
                selectinload(TrackedGroup.relations),
            ),
        )
        if group is None:
            raise ValueError(f"Gruppe {group_id} findes ikke")
        return group


def action_fetch_event_markets(event_slug_or_id: str):
    return run_async(fetch_event_markets(event_slug_or_id))


def action_list_event_markets(event_slug: str):
    result = action_fetch_event_markets(event_slug)
    return result.title, result.markets


def action_classify_reference(reference: str) -> tuple[str, str]:
    return parse_market_reference(reference.strip())


def action_create_group(name: str, description: str | None) -> int:
    return run_async(create_group(name, description=description or None))


def action_add_market(
    group_id: int,
    reference: str,
    role_label: str,
    outcome_side: str,
) -> int:
    return run_async(
        add_market_to_group(
            group_id,
            reference,
            role_label,
            outcome_side=outcome_side,
        ),
    )


def action_add_markets_bulk(
    group_id: int,
    items: list[tuple[str, str, str]],
) -> tuple[list[int], list[str]]:
    """Tilføj flere markeder; returnerer (ids, fejlbeskeder)."""
    ids: list[int] = []
    errors: list[str] = []

    async def _run():
        for reference, role_label, outcome_side in items:
            try:
                row_id = await add_market_to_group(
                    group_id,
                    reference,
                    role_label,
                    outcome_side=outcome_side,
                )
                ids.append(row_id)
            except Exception as exc:
                errors.append(f"{role_label}: {exc}")

    run_async(_run())
    return ids, errors


def action_add_relation(group_id: int, relation_type: str, definition: dict[str, Any]) -> int:
    return run_async(add_relation(group_id, relation_type, definition))


def action_remove_market(group_id: int, tracked_market_id: int) -> bool:
    return run_async(remove_market_from_group(group_id, tracked_market_id))


def action_remove_relation(group_id: int, relation_id: int) -> bool:
    return run_async(remove_relation(group_id, relation_id))


def action_set_status(group_id: int, status: str) -> bool:
    return run_async(set_group_status(group_id, status))


def action_update_group(group_id: int, name: str | None, description: str | None) -> bool:
    return run_async(update_group(group_id, name=name, description=description))


def action_refresh_snapshot(group_id: int):
    async def _run():
        group = await _load_group_orm(group_id)
        return await snapshot_group(group, persist=True)

    return run_async(_run())
