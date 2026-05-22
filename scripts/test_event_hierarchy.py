#!/usr/bin/env python3
"""CLI test for event-hierarki under tracked groups (Fase 1+2).

Opretter gruppe "Dansk regering 2026" med to events, tilføjer markeder
under hvert event, definerer cross-event relation og kører snapshot.
"""

from __future__ import annotations

import argparse
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
    add_event_to_group,
    add_markets_to_event,
    add_relation,
    create_group,
    get_group,
    list_events_in_group,
    set_group_status,
)
from pss.tracking.relations import evaluate_group_relations
from pss.tracking.snapshot import snapshot_all_active_groups

EVENT_PM = "next-prime-minister-of-denmark-after-parliamentary-election"
EVENT_PARTIES = "which-parties-will-be-part-of-the-next-government-of-denmark"

PM_MARKETS: list[tuple[str, str, str]] = [
    (
        "will-mette-frederiksen-be-the-next-prime-minister-of-denmark-after-the-2026-parliamentary-elections",
        "mette_pm",
        "yes",
    ),
    (
        "will-troels-lund-poulsen-be-the-next-prime-minister-of-denmark-after-the-2026-parliamentary-elections",
        "troels_pm",
        "yes",
    ),
]

PARTY_MARKETS: list[tuple[str, str, str]] = [
    (
        "will-the-social-democrats-be-part-of-the-next-government-of-denmark",
        "social_democrats_gov",
        "yes",
    ),
    (
        "will-venstre-be-part-of-the-next-government-of-denmark",
        "venstre_gov",
        "yes",
    ),
]


def _print_group_tree(group_id: int, detail) -> None:
    print(f"\n=== Gruppe #{group_id}: {detail.name} ===")
    print(f"Events: {len(detail.events)} | Markets: {len(detail.markets)} | Relations: {len(detail.relations)}")
    for ev in detail.events:
        legacy = ev.event_id.startswith("legacy-")
        tag = " [legacy]" if legacy else ""
        print(f"\n  Event: {ev.event_title}{tag}")
        print(f"    slug={ev.event_slug} | markets={len(ev.markets)}")
        for m in ev.markets:
            print(f"      - {m.role_label} ({m.outcome_side}): {m.question[:70]}...")


async def run(*, cleanup: bool) -> None:
    group_id = await create_group(
        "Dansk regering 2026 (event-hierarki test)",
        description="CLI test — PM + regeringspartier med cross-event relationer",
    )
    print(f"Oprettet gruppe #{group_id}")

    try:
        pm_event_id = await add_event_to_group(group_id, EVENT_PM)
        print(f"  + Event A (PM): group_event_id={pm_event_id}")

        parties_event_id = await add_event_to_group(group_id, EVENT_PARTIES)
        print(f"  + Event B (partier): group_event_id={parties_event_id}")

        pm_ids = await add_markets_to_event(pm_event_id, PM_MARKETS)
        print(f"  + {len(pm_ids)} PM-markeder tilføjet")

        party_ids = await add_markets_to_event(parties_event_id, PARTY_MARKETS)
        print(f"  + {len(party_ids)} partimarkeder tilføjet")

        rel_id = await add_relation(
            group_id,
            "implied_lte",
            {
                "left_role": "mette_pm",
                "right_role": "social_democrats_gov",
                "label": "Mette PM => Socialdemokratiet i regering",
            },
        )
        print(f"  + Relation implied_lte (mette_pm => social_democrats_gov): id={rel_id}")

        rel_id2 = await add_relation(
            group_id,
            "implied_lte",
            {
                "left_role": "troels_pm",
                "right_role": "venstre_gov",
                "label": "Troels PM => Venstre i regering",
            },
        )
        print(f"  + Relation implied_lte (troels_pm => venstre_gov): id={rel_id2}")

        events = await list_events_in_group(group_id)
        print("\n--- list_events_in_group ---")
        for ev in events:
            print(f"  [{ev.id}] {ev.event_title} ({ev.market_count} markets) slug={ev.event_slug}")

        detail = await get_group(group_id)
        if detail:
            _print_group_tree(group_id, detail)

        print("\n--- Snapshot ---")
        run = await snapshot_all_active_groups()
        snap = next((r for r in run.results if r.group_id == group_id), None)
        if snap is None:
            print("Snapshot fejlede (gruppe ikke i active snapshot-run)")
        else:
            metrics = snap.metrics
            print(f"Priser hentet for {snap.market_count} markeder")
            if snap.missing_prices:
                print(f"Mangler priser: {snap.missing_prices}")
            for role, pp in sorted(metrics.get("prices_pp", {}).items()):
                print(f"  {role}: {pp:.1f} pp")
            eval_metrics = evaluate_group_relations(
                [(r[1], r[2]) for r in detail.relations] if detail else [],
                {k: v / 100 for k, v in metrics.get("prices_pp", {}).items()},
                threshold_pp=3.0,
            )
            print(f"\nMax inkonsistens: {eval_metrics['max_inconsistency_pp']:.1f} pp")
            for rel in eval_metrics.get("relations", []):
                print(
                    f"  {rel['label']}: d={rel['inconsistency_pp']:.1f} pp "
                    f"(actual={rel.get('actual_pp')} expected={rel.get('expected_pp')})",
                )

        print("\n=== test_event_hierarchy: OK ===")
    finally:
        if cleanup:
            await set_group_status(group_id, "closed")
            print(f"\nGruppe #{group_id} sat til closed (cleanup)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test event-hierarki for tracked groups")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Behold gruppen som active efter test",
    )
    args = parser.parse_args()
    asyncio.run(run(cleanup=not args.keep))


if __name__ == "__main__":
    main()
