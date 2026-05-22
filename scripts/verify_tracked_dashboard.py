#!/usr/bin/env python3
"""Verificer dashboard queries mod Fed nested deadlines (samme som CLI sanity check)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

if (ROOT / ".env").exists():
    load_dotenv(ROOT / ".env")
elif (ROOT / "env").exists():
    load_dotenv(ROOT / "env")

from pss.dashboard.tracked_actions import (
    action_add_market,
    action_add_relation,
    action_create_group,
    action_refresh_snapshot,
    action_remove_market,
    action_remove_relation,
    action_set_status,
)
from pss.dashboard.tracked_queries import fetch_group_detail

FED = [
    ("fed-rate-cut-by-june-2026-meeting", "cut_by_june"),
    ("fed-rate-cut-by-july-2026-meeting-577", "cut_by_july"),
    ("fed-rate-cut-by-september-2026-meeting-264-382", "cut_by_sept"),
]


def main() -> int:
    gid = action_create_group("UI verify: Fed nested", description="Dashboard query test")
    mids: list[int] = []
    rids: list[int] = []
    try:
        for slug, role in FED:
            mids.append(action_add_market(gid, slug, role, "yes"))
        rids.append(
            action_add_relation(
                gid,
                "implied_lte",
                {
                    "left_role": "cut_by_june",
                    "right_role": "cut_by_sept",
                    "label": "P(cut by June) <= P(cut by September)",
                },
            ),
        )
        action_refresh_snapshot(gid)
        detail = fetch_group_detail(gid)
        assert detail is not None
        assert len(detail.markets) == 3
        assert detail.metrics is not None
        max_pp = float(detail.metrics["max_inconsistency_pp"])
        print(f"OK group_id={gid} max_inconsistency_pp={max_pp:.2f}")
        for rel in detail.relations:
            print(
                f"  {rel.inconsistency_pp:.2f} pp alert={rel.is_alert} "
                f"actual={rel.actual_pp} expected={rel.expected_pp}",
            )
        for m in detail.markets:
            print(f"  {m.role_label}: {m.price_pp}%")
        if max_pp > 2.0:
            print("WARN: forventede <=2 pp for Fed nested test")
            return 1
        print("Dashboard data layer matcher CLI-forventning.")
        return 0
    finally:
        for rid in rids:
            action_remove_relation(gid, rid)
        for mid in mids:
            action_remove_market(gid, mid)
        action_set_status(gid, "closed")


if __name__ == "__main__":
    raise SystemExit(main())
