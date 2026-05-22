#!/usr/bin/env python3
"""Sanity check: matematisk korrekte relationer mod live Polymarket-data."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

if (ROOT / ".env").exists():
    load_dotenv(ROOT / ".env")
elif (ROOT / "env").exists():
    load_dotenv(ROOT / "env")

from pss.tracking.groups import (
    add_market_to_group,
    add_relation,
    create_group,
    remove_market_from_group,
    remove_relation,
    set_group_status,
)
from pss.tracking.snapshot import snapshot_group
from pss.db.models import TrackedGroup, TrackedGroupMarket
from pss.db.session import AsyncSessionLocal
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# --- Test 1: Nested Fed deadlines (implied_lte) ---
# P(cut by June) <= P(cut by September) — logisk nødvendighed
FED_MARKETS = [
    ("fed-rate-cut-by-june-2026-meeting", "cut_by_june"),
    ("fed-rate-cut-by-july-2026-meeting-577", "cut_by_july"),
    ("fed-rate-cut-by-september-2026-meeting-264-382", "cut_by_sept"),
]

FED_RELATIONS = [
    (
        "implied_lte",
        {
            "left_role": "cut_by_june",
            "right_role": "cut_by_sept",
            "label": "P(cut by June) <= P(cut by September)",
        },
    ),
    (
        "implied_lte",
        {
            "left_role": "cut_by_july",
            "right_role": "cut_by_sept",
            "label": "P(cut by July) <= P(cut by September)",
        },
    ),
]

# --- Test 2: Mutually exclusive VOX seat buckets (sum_to_target = 1.0) ---
VOX_BUCKETS = [
    (
        "will-vox-vox-win-fewer-than-13-seats-in-the-2026-andalusia-regional-election",
        "vox_lt_13",
    ),
    (
        "will-vox-vox-win-13-15-seats-in-the-2026-andalusia-regional-election",
        "vox_13_15",
    ),
    (
        "will-vox-vox-win-16-18-seats-in-the-2026-andalusia-regional-election",
        "vox_16_18",
    ),
    (
        "will-vox-vox-win-19-21-seats-in-the-2026-andalusia-regional-election",
        "vox_19_21",
    ),
    (
        "will-vox-vox-win-22-or-more-seats-in-the-2026-andalusia-regional-election",
        "vox_22_plus",
    ),
]

VOX_ROLES = [r for _, r in VOX_BUCKETS]

VOX_RELATIONS = [
    (
        "sum_to_target",
        {
            "component_roles": VOX_ROLES,
            "target_probability": 1.0,
            "label": "VOX seat buckets sum to 100%",
        },
    ),
]


def _interpret(pp: float) -> str:
    if pp <= 2.0:
        return "OK — Polymarket konsistent (0-2 pp)"
    if pp <= 10.0:
        return "MULIGT signal — spread/fees kan forklare (3-10 pp)"
    return "ADVARSEL — tjek relation eller stale data (>10 pp)"


def _print_result(group_name: str, metrics: dict) -> None:
    print(f"\n{'=' * 60}")
    print(f"GRUPPE: {group_name}")
    print(f"{'=' * 60}")
    print("Priser (pp):")
    for role, pp in sorted(metrics.get("prices_pp", {}).items()):
        print(f"  {role}: {pp:.2f}")

    print("\nRelationer:")
    for rel in metrics.get("relations", []):
        inc = rel["inconsistency_pp"]
        flag = " [ALERT]" if inc >= 3.0 else ""
        print(f"  {rel['label']}")
        print(
            f"    faktisk={rel.get('actual_pp')}  forventet={rel.get('expected_pp')}  "
            f"afvigelse={inc:.2f} pp{flag}",
        )
        print(f"    -> {_interpret(inc)}")

    max_pp = metrics["max_inconsistency_pp"]
    print(f"\nMax afvigelse: {max_pp:.2f} pp | Alerts (>=3pp): {metrics['alert_count']}")
    print(f"Samlet vurdering: {_interpret(max_pp)}")


async def _build_group(
    name: str,
    description: str,
    markets: list[tuple[str, str]],
    relations: list,
) -> tuple[int, list[int], list[int]]:
    """Opret gruppe; returner (group_id, market_row_ids, relation_ids)."""
    group_id = await create_group(name, description=description)
    market_ids: list[int] = []
    for slug, role in markets:
        mid = await add_market_to_group(group_id, slug, role, outcome_side="yes")
        market_ids.append(mid)
    relation_ids: list[int] = []
    for rtype, rdef in relations:
        rid = await add_relation(group_id, rtype, rdef)
        relation_ids.append(rid)
    return group_id, market_ids, relation_ids


async def _cleanup(group_id: int, market_ids: list[int], relation_ids: list[int]) -> None:
    for rid in relation_ids:
        await remove_relation(group_id, rid)
    for mid in market_ids:
        await remove_market_from_group(group_id, mid)
    await set_group_status(group_id, "closed")


async def _load_group(group_id: int) -> TrackedGroup:
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
            raise RuntimeError(f"Gruppe {group_id} ikke fundet")
        return group


async def main() -> int:
    created: list[tuple[int, list[int], list[int]]] = []

    print("Opretter test-grupper mod live Polymarket...\n")

    fed_id, fed_markets, fed_rels = await _build_group(
        "Sanity: Fed nested deadlines",
        "P(cut earlier) <= P(cut later) — matematisk nødvendighed",
        FED_MARKETS,
        FED_RELATIONS,
    )
    created.append((fed_id, fed_markets, fed_rels))
    print(f"  Fed gruppe id={fed_id} ({len(FED_MARKETS)} markeder, {len(FED_RELATIONS)} relationer)")

    vox_id, vox_markets, vox_rels = await _build_group(
        "Sanity: VOX seat buckets",
        "Mutually exclusive buckets — sum(YES) skal ≈ 1.0",
        VOX_BUCKETS,
        VOX_RELATIONS,
    )
    created.append((vox_id, vox_markets, vox_rels))
    print(f"  VOX gruppe id={vox_id} ({len(VOX_BUCKETS)} markeder, {len(VOX_RELATIONS)} relationer)")

    print("\nKorer snapshot mod live data...")
    for group_id, _, _ in created:
        group = await _load_group(group_id)
        result = await snapshot_group(group, persist=True)
        _print_result(result.group_name, result.metrics)

    print("\n" + "=" * 60)
    print("CLEANUP: lukker test-grupper")
    for group_id, mids, rids in created:
        await _cleanup(group_id, mids, rids)
        print(f"  Gruppe {group_id} lukket")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
