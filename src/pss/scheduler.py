"""APScheduler: discovery + price snapshots efter fast skema."""

from __future__ import annotations

import asyncio
import signal
from datetime import datetime, timedelta, timezone

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from pss.config import settings
from pss.health_server import resolve_health_port, run_health_server
from pss.ingestion.market_discovery import discover_markets
from pss.ingestion.price_snapshot import snapshot_all_active_markets
from pss.logging_config import configure_logging
from pss.signals.pipeline import run_signal_pipeline
from pss.tracking.alerts import process_snapshot_alerts
from pss.tracking.snapshot import snapshot_all_active_groups

logger = structlog.get_logger(__name__)


def _install_signal_logging() -> None:
    def _on_sigterm(*_args: object) -> None:
        print("PSS: modtog SIGTERM (typisk Railway deploy/omstart)", flush=True)
        logger.info("sigterm_received")

    signal.signal(signal.SIGTERM, _on_sigterm)


async def _run_market_discovery() -> None:
    logger.info("job_started", job="market_discovery")
    try:
        count = await discover_markets()
    except Exception:
        logger.exception("job_failed", job="market_discovery")
        raise
    logger.info("job_finished", job="market_discovery", processed=count)


async def _run_price_snapshot() -> None:
    logger.info("job_started", job="price_snapshot")
    try:
        count = await snapshot_all_active_markets()
    except Exception:
        logger.exception("job_failed", job="price_snapshot")
        raise
    logger.info("job_finished", job="price_snapshot", snapshots=count)


async def _run_signal_scan() -> None:
    logger.info("job_started", job="signal_scan")
    try:
        result = await run_signal_pipeline(notify_telegram=True)
    except Exception:
        logger.exception("job_failed", job="signal_scan")
        raise
    logger.info(
        "job_finished",
        job="signal_scan",
        inserted=result.inserted,
        skipped=result.skipped,
        telegram_sent=result.telegram_sent,
    )


async def _run_tracked_group_snapshot() -> None:
    logger.info("job_started", job="tracked_group_snapshot")
    try:
        run = await snapshot_all_active_groups()
        alerts = await process_snapshot_alerts(run, notify_telegram=True)
    except Exception:
        logger.exception("job_failed", job="tracked_group_snapshot")
        raise
    logger.info(
        "job_finished",
        job="tracked_group_snapshot",
        groups=run.groups_processed,
        snapshots=run.snapshots_written,
        alerts_sent=sum(1 for a in alerts if a.sent),
    )


def setup_scheduler(*, run_immediately: bool = True) -> AsyncIOScheduler:
    """Registrér ingestion-jobs."""
    scheduler = AsyncIOScheduler(timezone="UTC")
    now = datetime.now(timezone.utc) if run_immediately else None
    discovery_start = now
    snapshot_start = now
    signal_start = now
    tracked_start = now
    if now and settings.is_production:
        discovery_start = now + timedelta(seconds=45)
        snapshot_start = now + timedelta(minutes=5)
        signal_start = now + timedelta(minutes=15)
        tracked_start = now + timedelta(seconds=30)

    scheduler.add_job(
        _run_market_discovery,
        trigger=IntervalTrigger(hours=1),
        id="market_discovery",
        name="Discover new and updated markets",
        max_instances=1,
        coalesce=True,
        next_run_time=discovery_start,
    )

    scheduler.add_job(
        _run_price_snapshot,
        trigger=IntervalTrigger(minutes=10),
        id="price_snapshot",
        name="Snapshot prices of active markets",
        max_instances=1,
        coalesce=True,
        next_run_time=snapshot_start,
    )

    scheduler.add_job(
        _run_signal_scan,
        trigger=IntervalTrigger(hours=1),
        id="signal_scan",
        name="Scan for base rate fade signals",
        max_instances=1,
        coalesce=True,
        next_run_time=signal_start,
    )

    scheduler.add_job(
        _run_tracked_group_snapshot,
        trigger=IntervalTrigger(minutes=settings.tracked_group_snapshot_interval_minutes),
        id="tracked_group_snapshot",
        name="Snapshot tracked market groups",
        max_instances=1,
        coalesce=True,
        next_run_time=tracked_start,
    )

    return scheduler


async def _run_scheduler_loop() -> None:
    """Hold processen i live og kør APScheduler-jobs."""
    scheduler = setup_scheduler(run_immediately=True)
    scheduler.start()

    jobs = scheduler.get_jobs()
    logger.info(
        "scheduler_started",
        jobs=[{"id": j.id, "next_run": j.next_run_time.isoformat()} for j in jobs],
    )
    print(
        "PSS scheduler kører (UTC). "
        "Discovery: hver time. Snapshots: hver 10. min. "
        f"Tracked groups: hver {settings.tracked_group_snapshot_interval_minutes}. min. "
        "Signal-scan: hver time.",
        flush=True,
    )

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        logger.info("scheduler_stopping")
        scheduler.shutdown(wait=False)
        logger.info("scheduler_stopped")


async def main() -> None:
    configure_logging()
    _install_signal_logging()

    port = resolve_health_port()
    print(f"PSS: starter worker (health på port {port})…", flush=True)

    await asyncio.gather(
        run_health_server(port),
        _run_scheduler_loop(),
    )


if __name__ == "__main__":
    asyncio.run(main())
