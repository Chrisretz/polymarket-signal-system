"""Telegram alerts ved relation-inkonsistens i tracked groups."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import select

from pss.config import settings
from pss.db.models import TrackedGroupSnapshot
from pss.db.session import AsyncSessionLocal
from pss.notifications.telegram import TelegramNotConfiguredError, send_alert
from pss.tracking.snapshot import GroupSnapshotResult, SnapshotRunResult

logger = structlog.get_logger(__name__)

_last_alert_at: dict[int, datetime] = {}


@dataclass(frozen=True, slots=True)
class AlertDispatchResult:
    group_id: int
    group_name: str
    sent: bool
    reason: str
    max_inconsistency_pp: float
    alert_count: int


def _format_alert_body(group_name: str, metrics: dict[str, Any]) -> str:
    lines = [
        f"Gruppe: {group_name}",
        f"Max inkonsistens: {metrics['max_inconsistency_pp']:.1f} pp",
        f"Threshold: {settings.tracked_group_alert_threshold_pp:.1f} pp",
        "",
    ]
    for alert in metrics.get("alerts", []):
        lines.append(f"• {alert['label']}")
        if alert.get("actual_pp") is not None and alert.get("expected_pp") is not None:
            lines.append(
                f"  Faktisk: {alert['actual_pp']:.1f}% | Forventet: {alert['expected_pp']:.1f}% "
                f"({alert['inconsistency_pp']:.1f} pp)",
            )
        else:
            lines.append(f"  Inkonsistens: {alert['inconsistency_pp']:.1f} pp")
    prices = metrics.get("prices_pp", {})
    if prices:
        lines.append("")
        lines.append("Priser (pp):")
        for role, pp in sorted(prices.items()):
            lines.append(f"  {role}: {pp:.1f}")
    return "\n".join(lines)


async def _previous_snapshot_metrics(group_id: int) -> dict[str, Any] | None:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(TrackedGroupSnapshot)
                .where(TrackedGroupSnapshot.group_id == group_id)
                .order_by(TrackedGroupSnapshot.snapshot_at.desc())
                .limit(2),
            )
        ).scalars().all()
    if len(rows) < 2:
        return None
    return rows[1].calculated_metrics


def _should_send_alert(
    group_id: int,
    metrics: dict[str, Any],
    previous: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> tuple[bool, str]:
    if metrics.get("alert_count", 0) == 0:
        return False, "under_threshold"

    current_max = float(metrics.get("max_inconsistency_pp", 0.0))
    threshold = settings.tracked_group_alert_threshold_pp
    if current_max < threshold:
        return False, "under_threshold"

    ts = now or datetime.now(timezone.utc)
    last = _last_alert_at.get(group_id)
    cooldown = timedelta(minutes=settings.tracked_group_alert_cooldown_minutes)
    if last and ts - last < cooldown:
        return False, "cooldown"

    if previous is not None:
        prev_max = float(previous.get("max_inconsistency_pp", 0.0))
        if prev_max >= threshold and current_max <= prev_max + 0.5:
            return False, "not_worsened"

    return True, "triggered"


async def maybe_alert_for_snapshot(
    result: GroupSnapshotResult,
    *,
    notify_telegram: bool = True,
) -> AlertDispatchResult:
    """Send alert hvis snapshot overstiger threshold og situation er forværret."""
    metrics = result.metrics
    previous = await _previous_snapshot_metrics(result.group_id)
    should_send, reason = _should_send_alert(result.group_id, metrics, previous)

    if not should_send or not notify_telegram:
        return AlertDispatchResult(
            group_id=result.group_id,
            group_name=result.group_name,
            sent=False,
            reason=reason if not notify_telegram else reason,
            max_inconsistency_pp=float(metrics.get("max_inconsistency_pp", 0.0)),
            alert_count=int(metrics.get("alert_count", 0)),
        )

    body = _format_alert_body(result.group_name, metrics)
    try:
        await send_alert("Tracked group inkonsistens", body)
    except TelegramNotConfiguredError:
        logger.warning("tracked_group_alert_skipped", reason="telegram_not_configured")
        return AlertDispatchResult(
            group_id=result.group_id,
            group_name=result.group_name,
            sent=False,
            reason="telegram_not_configured",
            max_inconsistency_pp=float(metrics.get("max_inconsistency_pp", 0.0)),
            alert_count=int(metrics.get("alert_count", 0)),
        )

    _last_alert_at[result.group_id] = datetime.now(timezone.utc)
    logger.info(
        "tracked_group_alert_sent",
        group_id=result.group_id,
        max_inconsistency_pp=metrics.get("max_inconsistency_pp"),
    )
    return AlertDispatchResult(
        group_id=result.group_id,
        group_name=result.group_name,
        sent=True,
        reason="sent",
        max_inconsistency_pp=float(metrics.get("max_inconsistency_pp", 0.0)),
        alert_count=int(metrics.get("alert_count", 0)),
    )


async def process_snapshot_alerts(
    run: SnapshotRunResult,
    *,
    notify_telegram: bool = True,
) -> list[AlertDispatchResult]:
    """Evaluér alerts for alle snapshots i et run."""
    out: list[AlertDispatchResult] = []
    for result in run.results:
        out.append(await maybe_alert_for_snapshot(result, notify_telegram=notify_telegram))
    return out
