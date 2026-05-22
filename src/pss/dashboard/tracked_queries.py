"""Synkrone queries til Tracked Groups dashboard."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from pss.config import settings
from pss.dashboard.queries import _with_session
from pss.db.models import (
    Market,
    TrackedGroup,
    TrackedGroupMarket,
    TrackedGroupRelation,
    TrackedGroupSnapshot,
)
from pss.markets.urls import polymarket_market_url
from pss.tracking.relations import relation_row_signed_pp

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class GroupOverviewRow:
    id: int
    name: str
    description: str | None
    status: str
    market_count: int
    relation_count: int
    updated_at: datetime
    snapshot_at: datetime | None
    max_inconsistency_pp: float | None
    alert_count: int | None


@dataclass(frozen=True, slots=True)
class GroupMarketView:
    id: int
    role_label: str
    outcome_side: str
    question: str
    slug: str | None
    polymarket_url: str | None
    price_pp: float | None


@dataclass(frozen=True, slots=True)
class GroupRelationView:
    id: int
    relation_type: str
    definition: dict[str, Any]
    label: str
    actual_pp: float | None
    expected_pp: float | None
    inconsistency_pp: float | None
    signed_deviation_pp: float | None
    is_alert: bool


@dataclass(frozen=True, slots=True)
class RelationTimeseriesPoint:
    snapshot_at: datetime
    signed_deviation_pp: float
    inconsistency_pp: float
    actual_pp: float | None
    expected_pp: float | None
    price_lines_pp: dict[str, float]


@dataclass(frozen=True, slots=True)
class RelationStatsView:
    avg_signed_7d: float | None
    min_signed_7d: float | None
    max_signed_7d: float | None
    breach_count_30d: int
    time_since_last_breach: str | None


@dataclass(frozen=True, slots=True)
class GroupDetailView:
    id: int
    name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    snapshot_at: datetime | None
    metrics: dict[str, Any] | None
    markets: list[GroupMarketView]
    relations: list[GroupRelationView]


@dataclass(frozen=True, slots=True)
class SnapshotHistoryRow:
    snapshot_at: datetime
    max_inconsistency_pp: float
    alert_count: int
    relation_label: str
    actual_pp: float | None
    expected_pp: float | None
    inconsistency_pp: float
    signed_deviation_pp: float | None


@dataclass(frozen=True, slots=True)
class AlertHistoryRow:
    snapshot_at: datetime
    relation_label: str
    inconsistency_pp: float
    actual_pp: float | None
    expected_pp: float | None


def _latest_snapshot(session: Session, group_id: int) -> TrackedGroupSnapshot | None:
    return session.scalar(
        select(TrackedGroupSnapshot)
        .where(TrackedGroupSnapshot.group_id == group_id)
        .order_by(TrackedGroupSnapshot.snapshot_at.desc())
        .limit(1),
    )


def fetch_groups_overview(*, status: str | None = "active") -> list[GroupOverviewRow]:
    def _run(session: Session) -> list[GroupOverviewRow]:
        q = (
            select(TrackedGroup)
            .options(
                selectinload(TrackedGroup.markets),
                selectinload(TrackedGroup.relations),
            )
            .order_by(TrackedGroup.updated_at.desc())
        )
        if status:
            q = q.where(TrackedGroup.status == status)
        groups = session.scalars(q).all()
        out: list[GroupOverviewRow] = []
        for g in groups:
            snap = _latest_snapshot(session, int(g.id))
            metrics = snap.calculated_metrics if snap else None
            out.append(
                GroupOverviewRow(
                    id=int(g.id),
                    name=g.name,
                    description=g.description,
                    status=g.status,
                    market_count=len(g.markets) if g.markets else 0,
                    relation_count=len(g.relations) if g.relations else 0,
                    updated_at=g.updated_at,
                    snapshot_at=snap.snapshot_at if snap else None,
                    max_inconsistency_pp=(
                        float(metrics["max_inconsistency_pp"]) if metrics else None
                    ),
                    alert_count=int(metrics["alert_count"]) if metrics else None,
                ),
            )
        return out

    return _with_session(_run)


def fetch_group_detail(group_id: int) -> GroupDetailView | None:
    def _run(session: Session) -> GroupDetailView | None:
        group = session.scalar(
            select(TrackedGroup)
            .where(TrackedGroup.id == group_id)
            .options(
                selectinload(TrackedGroup.markets).selectinload(TrackedGroupMarket.market),
                selectinload(TrackedGroup.relations),
            ),
        )
        if group is None:
            return None

        snap = _latest_snapshot(session, group_id)
        metrics = snap.calculated_metrics if snap else None
        prices_pp = metrics.get("prices_pp", {}) if metrics else {}

        markets: list[GroupMarketView] = []
        for gm in group.markets:
            m: Market = gm.market
            url = polymarket_market_url(
                slug=m.slug,
                raw_metadata=m.raw_metadata,
                question=m.question,
            )
            markets.append(
                GroupMarketView(
                    id=int(gm.id),
                    role_label=gm.role_label,
                    outcome_side=gm.outcome_side,
                    question=m.question,
                    slug=m.slug,
                    polymarket_url=url,
                    price_pp=prices_pp.get(gm.role_label),
                ),
            )

        from pss.dashboard.tracked_format import format_relation_definition

        relations: list[GroupRelationView] = []
        for rel in group.relations:
            want = format_relation_definition(rel.relation_type, rel.definition)
            eval_row = None
            if metrics:
                for r in metrics.get("relations", []):
                    if r.get("label") == want:
                        eval_row = r
                        break
            inc = float(eval_row["inconsistency_pp"]) if eval_row else None
            signed = relation_row_signed_pp(eval_row) if eval_row else None
            relations.append(
                GroupRelationView(
                    id=int(rel.id),
                    relation_type=rel.relation_type,
                    definition=rel.definition,
                    label=want,
                    actual_pp=eval_row.get("actual_pp") if eval_row else None,
                    expected_pp=eval_row.get("expected_pp") if eval_row else None,
                    inconsistency_pp=inc,
                    signed_deviation_pp=signed,
                    is_alert=inc is not None and inc >= settings.tracked_group_alert_threshold_pp,
                ),
            )

        return GroupDetailView(
            id=int(group.id),
            name=group.name,
            description=group.description,
            status=group.status,
            created_at=group.created_at,
            updated_at=group.updated_at,
            snapshot_at=snap.snapshot_at if snap else None,
            metrics=metrics,
            markets=markets,
            relations=relations,
        )

    return _with_session(_run)


def fetch_snapshot_history(
    group_id: int,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 200,
) -> list[SnapshotHistoryRow]:
    def _run(session: Session) -> list[SnapshotHistoryRow]:
        q = (
            select(TrackedGroupSnapshot)
            .where(TrackedGroupSnapshot.group_id == group_id)
            .order_by(TrackedGroupSnapshot.snapshot_at.desc())
            .limit(limit)
        )
        if date_from:
            q = q.where(TrackedGroupSnapshot.snapshot_at >= datetime.combine(date_from, datetime.min.time()))
        if date_to:
            q = q.where(TrackedGroupSnapshot.snapshot_at <= datetime.combine(date_to, datetime.max.time()))

        rows = session.scalars(q).all()
        out: list[SnapshotHistoryRow] = []
        for snap in rows:
            metrics = snap.calculated_metrics or {}
            rels = metrics.get("relations") or []
            if not rels:
                out.append(
                    SnapshotHistoryRow(
                        snapshot_at=snap.snapshot_at,
                        max_inconsistency_pp=float(metrics.get("max_inconsistency_pp", 0)),
                        alert_count=int(metrics.get("alert_count", 0)),
                        relation_label="—",
                        actual_pp=None,
                        expected_pp=None,
                        inconsistency_pp=0.0,
                        signed_deviation_pp=None,
                    ),
                )
                continue
            for rel in rels:
                out.append(
                    SnapshotHistoryRow(
                        snapshot_at=snap.snapshot_at,
                        max_inconsistency_pp=float(metrics.get("max_inconsistency_pp", 0)),
                        alert_count=int(metrics.get("alert_count", 0)),
                        relation_label=str(rel.get("label", "")),
                        actual_pp=rel.get("actual_pp"),
                        expected_pp=rel.get("expected_pp"),
                        inconsistency_pp=float(rel.get("inconsistency_pp", 0)),
                        signed_deviation_pp=relation_row_signed_pp(rel),
                    ),
                )
        return out

    return _with_session(_run)


def _price_lines_for_relation(
    relation_type: str,
    definition: dict[str, Any],
    prices_pp: dict[str, Any],
    rel_row: dict[str, Any],
) -> dict[str, float]:
    """Pris-linjer til dual-axis chart (sekundær akse, %)."""
    lines: dict[str, float] = {}

    def _price(role: str) -> float | None:
        if role not in prices_pp or prices_pp[role] is None:
            return None
        return float(prices_pp[role])

    if relation_type == "implied_lte":
        left = definition["left_role"]
        right = definition["right_role"]
        if (p := _price(left)) is not None:
            lines[f"P({left})"] = p
        if (p := _price(right)) is not None:
            lines[f"P({right})"] = p

    elif relation_type == "target_equals":
        role = definition["role"]
        if (p := _price(role)) is not None:
            lines[f"P({role})"] = p
        lines["target"] = float(definition["target_probability"]) * 100

    elif relation_type == "sum_to_target":
        for role in definition["component_roles"]:
            if (p := _price(role)) is not None:
                lines[f"P({role})"] = p
        lines["target Σ"] = float(definition.get("target_probability", 1.0)) * 100
        if rel_row.get("actual_pp") is not None:
            lines["faktisk Σ"] = float(rel_row["actual_pp"])

    elif relation_type == "sum_equals":
        target = definition["target_role"]
        if (p := _price(target)) is not None:
            lines[f"P({target})"] = p
        for role in definition["component_roles"]:
            if (p := _price(role)) is not None:
                lines[f"P({role})"] = p
        if rel_row.get("expected_pp") is not None:
            lines["Σ komponenter"] = float(rel_row["expected_pp"])

    elif relation_type == "weighted_sum_equals":
        target = definition["target_role"]
        if (p := _price(target)) is not None:
            lines[f"P({target})"] = p
        for comp in definition["components"]:
            role = comp["role"]
            weight = comp.get("weight", 1.0)
            if (p := _price(role)) is not None:
                lines[f"P({role})×{weight}"] = p
        if rel_row.get("expected_pp") is not None:
            lines["weighted Σ"] = float(rel_row["expected_pp"])

    return lines


def _format_duration(delta: timedelta) -> str:
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds} sek"
    minutes = total_seconds // 60
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} timer"
    days = hours // 24
    return f"{days} dage"


def _compute_relation_stats(
    points: list[RelationTimeseriesPoint],
    *,
    threshold_pp: float,
    now: datetime | None = None,
) -> RelationStatsView:
    now = now or datetime.now(timezone.utc)
    cutoff_7d = now - timedelta(days=7)
    cutoff_30d = now - timedelta(days=30)

    recent_7d = [p for p in points if p.snapshot_at >= cutoff_7d]
    signed_7d = [p.signed_deviation_pp for p in recent_7d]

    avg_signed: float | None = None
    min_signed: float | None = None
    max_signed: float | None = None
    if signed_7d:
        avg_signed = sum(signed_7d) / len(signed_7d)
        min_signed = min(signed_7d)
        max_signed = max(signed_7d)

    breach_count_30d = sum(
        1
        for p in points
        if p.snapshot_at >= cutoff_30d and p.inconsistency_pp >= threshold_pp
    )

    last_breach: datetime | None = None
    for p in reversed(points):
        if p.inconsistency_pp >= threshold_pp:
            last_breach = p.snapshot_at
            break

    time_since: str | None
    if last_breach is None:
        time_since = "Aldrig"
    else:
        time_since = _format_duration(now - last_breach)

    return RelationStatsView(
        avg_signed_7d=avg_signed,
        min_signed_7d=min_signed,
        max_signed_7d=max_signed,
        breach_count_30d=breach_count_30d,
        time_since_last_breach=time_since,
    )


def fetch_relation_timeseries(
    group_id: int,
    relation_label: str,
    *,
    relation_type: str,
    definition: dict[str, Any],
    days: int | None = 7,
    limit: int = 5000,
) -> tuple[list[RelationTimeseriesPoint], RelationStatsView]:
    """Hent signed afvigelse + rolle-priser over tid for én relation."""

    def _run(session: Session) -> tuple[list[RelationTimeseriesPoint], RelationStatsView]:
        now = datetime.now(timezone.utc)
        stats_window_days = 30
        if days is None:
            fetch_since = None
        else:
            fetch_days = max(days, stats_window_days)
            fetch_since = now - timedelta(days=fetch_days)

        q = (
            select(TrackedGroupSnapshot)
            .where(TrackedGroupSnapshot.group_id == group_id)
            .order_by(TrackedGroupSnapshot.snapshot_at.asc())
            .limit(limit)
        )
        if fetch_since is not None:
            q = q.where(TrackedGroupSnapshot.snapshot_at >= fetch_since)

        snaps = session.scalars(q).all()
        all_points: list[RelationTimeseriesPoint] = []
        for snap in snaps:
            metrics = snap.calculated_metrics or {}
            prices_pp = metrics.get("prices_pp") or {}
            for rel in metrics.get("relations") or []:
                if str(rel.get("label", "")) != relation_label:
                    continue
                signed = relation_row_signed_pp(rel)
                if signed is None:
                    continue
                all_points.append(
                    RelationTimeseriesPoint(
                        snapshot_at=snap.snapshot_at,
                        signed_deviation_pp=signed,
                        inconsistency_pp=float(rel.get("inconsistency_pp", 0)),
                        actual_pp=rel.get("actual_pp"),
                        expected_pp=rel.get("expected_pp"),
                        price_lines_pp=_price_lines_for_relation(
                            relation_type,
                            definition,
                            prices_pp,
                            rel,
                        ),
                    ),
                )
                break

        if days is None:
            chart_points = all_points
        else:
            chart_since = now - timedelta(days=days)
            chart_points = [p for p in all_points if p.snapshot_at >= chart_since]

        stats = _compute_relation_stats(
            all_points,
            threshold_pp=settings.tracked_group_alert_threshold_pp,
            now=now,
        )
        return chart_points, stats

    return _with_session(_run)


def fetch_alert_history(group_id: int, *, limit: int = 100) -> list[AlertHistoryRow]:
    def _run(session: Session) -> list[AlertHistoryRow]:
        snaps = session.scalars(
            select(TrackedGroupSnapshot)
            .where(TrackedGroupSnapshot.group_id == group_id)
            .order_by(TrackedGroupSnapshot.snapshot_at.desc())
            .limit(limit * 3),
        ).all()
        threshold = settings.tracked_group_alert_threshold_pp
        out: list[AlertHistoryRow] = []
        for snap in snaps:
            metrics = snap.calculated_metrics or {}
            for alert in metrics.get("alerts") or []:
                out.append(
                    AlertHistoryRow(
                        snapshot_at=snap.snapshot_at,
                        relation_label=str(alert.get("label", "")),
                        inconsistency_pp=float(alert.get("inconsistency_pp", 0)),
                        actual_pp=alert.get("actual_pp"),
                        expected_pp=alert.get("expected_pp"),
                    ),
                )
            if len(out) >= limit:
                break
        return out[:limit]

    return _with_session(_run)
