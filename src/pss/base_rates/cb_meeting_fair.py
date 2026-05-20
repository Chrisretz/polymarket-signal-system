"""Forward-proxy fair value for central bank meeting markets (FRED).

Uses policy rate vs short money-market proxy (3M) to estimate implied
P(hold|cut|hike) at the next meeting — not static expert priors.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Literal

import structlog

from pss.base_rates.fred import FredClient

logger = structlog.get_logger(__name__)

EXPERT_PRIOR_SOURCE = "expert_prior_v0"
FORWARD_IMPLIED_SOURCE = "forward_implied_v0"

CbAction = Literal["hold", "cut", "hike"]

CB_MEETING_CATEGORIES: frozenset[str] = frozenset(
    {
        "fed_hold",
        "fed_cut_25bps",
        "fed_hike_25bps",
        "ecb_hold",
        "ecb_cut",
        "ecb_hike",
        "boj_hold",
        "boj_cut",
        "boj_hike",
    },
)

_CATEGORY_ACTION: dict[str, CbAction] = {
    "fed_hold": "hold",
    "fed_cut_25bps": "cut",
    "fed_hike_25bps": "hike",
    "ecb_hold": "hold",
    "ecb_cut": "cut",
    "ecb_hike": "hike",
    "boj_hold": "hold",
    "boj_cut": "cut",
    "boj_hike": "hike",
}

_INSTITUTION_SERIES: dict[str, tuple[str, str]] = {
    # institution → (policy_rate_series, forward_proxy_series); both in % on FRED
    "ecb": ("ECBDFR", "IR3TIB01EZM156N"),
    "fed": ("FEDFUNDS", "DGS3MO"),
    "boj": ("IRSTCI01JPM156N", "IR3TIB01JPM156N"),
}


def category_institution(category: str) -> str | None:
    if category.startswith("ecb_"):
        return "ecb"
    if category.startswith("fed_"):
        return "fed"
    if category.startswith("boj_"):
        return "boj"
    return None


def expected_delta_bps(policy_rate_pct: float, forward_proxy_pct: float) -> float:
    """Proxy for expected policy change (bps) from curve vs current policy."""
    return (forward_proxy_pct - policy_rate_pct) * 100.0


def implied_action_probability(action: CbAction, expected_delta_bps: float) -> float:
    """Map curve-implied delta to P(hold|cut|hike), bounded away from 0/1."""
    if action == "hold":
        sigma = 25.0
        z = expected_delta_bps / sigma
        raw = math.exp(-0.5 * z * z)
    elif action == "cut":
        x = (-expected_delta_bps - 25.0) / 15.0
        raw = 1.0 / (1.0 + math.exp(-x))
    else:
        x = (expected_delta_bps - 25.0) / 15.0
        raw = 1.0 / (1.0 + math.exp(-x))
    return max(0.05, min(0.95, raw))


@dataclass(frozen=True, slots=True)
class CbFairSnapshot:
    institution: str
    policy_rate_pct: float
    forward_proxy_pct: float
    expected_delta_bps: float
    policy_series: str
    forward_series: str
    as_of: date


class CbMeetingFairValueProvider:
    """Caches one snapshot per institution per scan."""

    def __init__(self, fred: FredClient | None) -> None:
        self._fred = fred
        self._cache: dict[str, CbFairSnapshot | None] = {}

    async def fair_for_category(
        self,
        category: str,
    ) -> tuple[float, str, dict[str, float | str]] | None:
        if category not in CB_MEETING_CATEGORIES:
            return None
        action = _CATEGORY_ACTION.get(category)
        institution = category_institution(category)
        if action is None or institution is None:
            return None

        snapshot = await self._snapshot_for(institution)
        if snapshot is None:
            return None

        prob = implied_action_probability(action, snapshot.expected_delta_bps)
        meta: dict[str, float | str] = {
            "cb_institution": institution,
            "cb_action": action,
            "cb_policy_rate_pct": snapshot.policy_rate_pct,
            "cb_forward_proxy_pct": snapshot.forward_proxy_pct,
            "cb_expected_delta_bps": snapshot.expected_delta_bps,
            "cb_policy_series": snapshot.policy_series,
            "cb_forward_series": snapshot.forward_series,
            "cb_rates_as_of": snapshot.as_of.isoformat(),
        }
        return round(prob, 4), FORWARD_IMPLIED_SOURCE, meta

    async def _snapshot_for(self, institution: str) -> CbFairSnapshot | None:
        if institution in self._cache:
            return self._cache[institution]
        snapshot = await self._fetch_snapshot(institution)
        self._cache[institution] = snapshot
        return snapshot

    async def _fetch_snapshot(self, institution: str) -> CbFairSnapshot | None:
        if self._fred is None:
            return None
        series = _INSTITUTION_SERIES.get(institution)
        if series is None:
            return None
        policy_id, forward_id = series
        try:
            policy = await self._fred.fetch_latest_observation(policy_id)
            forward = await self._fred.fetch_latest_observation(forward_id)
        except Exception:
            logger.warning(
                "cb_fair_fred_fetch_failed",
                institution=institution,
                exc_info=True,
            )
            return None
        if policy is None or forward is None:
            logger.info("cb_fair_missing_observations", institution=institution)
            return None

        policy_date, policy_pct = policy
        forward_date, forward_pct = forward
        delta = expected_delta_bps(policy_pct, forward_pct)
        snap = CbFairSnapshot(
            institution=institution,
            policy_rate_pct=policy_pct,
            forward_proxy_pct=forward_pct,
            expected_delta_bps=delta,
            policy_series=policy_id,
            forward_series=forward_id,
            as_of=max(policy_date, forward_date),
        )
        logger.info(
            "cb_fair_snapshot",
            institution=institution,
            policy_pct=policy_pct,
            forward_pct=forward_pct,
            expected_delta_bps=round(delta, 2),
        )
        return snap
