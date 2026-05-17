"""APScheduler: discovery + price snapshots efter fast skema."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta, timezone

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from pss.config import settings
from pss.health_server import start_health_server_task
from pss.ingestion.market_discovery import discover_markets
from pss.ingestion.price_snapshot import snapshot_all_active_markets
from pss.logging_config import configure_logging
from pss.signals.pipeline import run_signal_pipeline

logger = structlog.get_logger(__name__)


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


def setup_scheduler(*, run_immediately: bool = True) -> AsyncIOScheduler:
    """Registrér ingestion-jobs.

    Args:
        run_immediately: Kør begge jobs én gang ved opstart (efter genstart).
    """
    scheduler = AsyncIOScheduler(timezone="UTC")
    now = datetime.now(timezone.utc) if run_immediately else None
    # I prod: undgå at discovery + snapshot kører parallelt ved opstart (mindre load + færre logs)
    discovery_start = now
    snapshot_start = now
    signal_start = now
    if now and settings.is_production:
        # Giv Railway healthcheck tid til at se HTTP 200 før tung Gamma-pagination
        discovery_start = now + timedelta(seconds=45)
        snapshot_start = now + timedelta(minutes=5)
        signal_start = now + timedelta(minutes=15)

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

    return scheduler


async def main() -> None:
    configure_logging()
    health_task = start_health_server_task()
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
        "Signal-scan: hver time. "
        "Stop med Ctrl+C.",
    )

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("scheduler_stopping")
        scheduler.shutdown(wait=False)
        logger.info("scheduler_stopped")
    finally:
        if health_task is not None:
            health_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await health_task


if __name__ == "__main__":
    asyncio.run(main())
