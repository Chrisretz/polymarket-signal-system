#!/usr/bin/env python3
"""End-to-end CLI test for tracked market groups (Fase 2A).

Opretter en test-gruppe med reelle Polymarket-markeder, definerer relation,
kører snapshot og viser evaluering.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

# Bruger `env` hvis `.env` mangler (lokal convention)
if (ROOT / ".env").exists():
    load_dotenv(ROOT / ".env")
elif (ROOT / "env").exists():
    load_dotenv(ROOT / "env")

from pss.tracking.alerts import maybe_alert_for_snapshot
from pss.tracking.groups import (
    add_market_to_group,
    add_relation,
    create_group,
    get_group,
    remove_market_from_group,
    remove_relation,
    set_group_status,
)
from pss.tracking.relations import evaluate_group_relations
from pss.tracking.snapshot import snapshot_all_active_groups

# Dansk politik — "Which parties will be part of the next Government of Denmark?"
# Demonstrerer outcome-niveau roles + weighted_sum_equals (SF-lignende mønster)
DEFAULT_MARKETS: list[tuple[str, str, str]] = [
    (
        "will-green-left-be-part-of-the-next-government-of-denmark",
        "green_left_gov",
        "yes",
    ),
    (
        "will-the-social-democrats-be-part-of-the-next-government-of-denmark",
        "social_democrats_gov",
        "yes",
    ),
    (
        "will-moderates-be-part-of-the-next-government-of-denmark",
        "moderates_gov",
        "yes",
    ),
]


def _print_metrics(group_name: str, metrics: dict) -> None:
    print(f"\n=== {group_name} ===")
    print("Priser (pp):")
    for role, pp in sorted(metrics.get("prices_pp", {}).items()):
        print(f"  {role}: {pp:.1f}")

    print("\nRelationer:")
    for rel in metrics.get("relations", []):
        flag = " [!]" if rel["inconsistency_pp"] >= 3.0 else ""
        print(
            f"  {rel['label']}: "
            f"faktisk={rel.get('actual_pp')} forventet={rel.get('expected_pp')} "
            f"d={rel['inconsistency_pp']:.1f} pp{flag}",
        )

    print(
        f"\nMax inkonsistens: {metrics['max_inconsistency_pp']:.1f} pp | "
        f"Alerts: {metrics['alert_count']}",
    )
    if metrics.get("missing_roles"):
        print(f"Manglende priser: {', '.join(metrics['missing_roles'])}")


async def _cleanup_test_group(group_id: int, detail) -> None:
    for rel_id, _, _ in detail.relations:
        await remove_relation(group_id, rel_id)
    for m in detail.markets:
        await remove_market_from_group(group_id, m.id)
    await set_group_status(group_id, "closed")


async def run_demo(*, cleanup: bool, notify: bool) -> int:
    group_id = await create_group(
        "CLI test — DK regering 2026",
        description="Fase 2A: Green Left vs rød+lilla implikation (auto-oprettet)",
    )
    print(f"Oprettet gruppe id={group_id}")

    for url, role, side in DEFAULT_MARKETS:
        row_id = await add_market_to_group(group_id, url, role, outcome_side=side)
        print(f"  + {role} ({side}) -> tracked_market_id={row_id}")

    # P(green_left_gov) ≈ P(S gov) + 0.7 * P(Moderaterne gov) — SF sikker i rød, sandsynlig i lilla
    await add_relation(
        group_id,
        "weighted_sum_equals",
        {
            "target_role": "green_left_gov",
            "components": [
                {"role": "social_democrats_gov", "weight": 1.0},
                {"role": "moderates_gov", "weight": 0.7},
            ],
            "label": "Green Left ≈ S + 0.7×Moderaterne (blok-implikation)",
        },
    )
    print("Relation tilføjet: weighted_sum_equals (green_left vs S + 0.7×Moderaterne)")

    detail = await get_group(group_id)
    if detail is None:
        print("Fejl: gruppe ikke fundet efter oprettelse", file=sys.stderr)
        return 1

    run = await snapshot_all_active_groups()
    our = next((r for r in run.results if r.group_id == group_id), None)
    if our is None:
        print("Fejl: snapshot for test-gruppe mangler", file=sys.stderr)
        return 1

    _print_metrics(our.group_name, our.metrics)

    if notify:
        alert = await maybe_alert_for_snapshot(our, notify_telegram=True)
        print(f"\nTelegram alert: sent={alert.sent} reason={alert.reason}")

    print("\n--- Raw metrics JSON ---")
    print(json.dumps(our.metrics, indent=2, default=str))

    if cleanup and detail:
        await _cleanup_test_group(group_id, detail)
        print(f"\nTest-gruppe {group_id} lukket og ryddet op.")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Test tracked market groups end-to-end")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Behold test-gruppen i DB (default: cleanup)",
    )
    parser.add_argument(
        "--telegram",
        action="store_true",
        help="Forsøg Telegram alert ved threshold-brud",
    )
    args = parser.parse_args()
    code = asyncio.run(run_demo(cleanup=not args.keep, notify=args.telegram))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
