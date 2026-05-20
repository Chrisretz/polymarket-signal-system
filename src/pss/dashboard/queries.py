"""Synkrone database queries til Streamlit (undgår asyncio event-loop konflikter)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any, TypeVar

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from pss.config import settings
from pss.db.models import DecisionJournal, Market, MarketSnapshot, PerformanceDaily, Position, Signal
from pss.markets.urls import polymarket_market_url

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class SignalRow:
    id: int
    generated_at: datetime
    strategy: str
    side: str
    status: str
    market_price: float
    fair_value_estimate: float
    edge_pct: float
    suggested_size_usd: float
    question: str
    polymarket_url: str | None
    metadata: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class PositionRow:
    id: int
    strategy: str
    side: str
    status: str
    is_paper: bool
    entry_price: float
    entry_size_usd: float
    entered_at: datetime
    exit_price: float | None
    exited_at: datetime | None
    realized_pnl_usd: float | None
    realized_pnl_pct: float | None
    question: str


@dataclass(frozen=True, slots=True)
class JournalRow:
    id: int
    entry_type: str
    strategy: str | None
    thesis: str | None
    created_at: datetime
    question: str
    expected_edge_pct: float | None


@dataclass(frozen=True, slots=True)
class PipelineStats:
    active_markets: int
    base_rate_markets: int
    snapshot_count: int
    last_snapshot_at: datetime | None
    signal_counts: dict[str, int]


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        settings.database_url_sync,
        pool_pre_ping=True,
        echo=False,
    )
    return sessionmaker(bind=engine, expire_on_commit=False)


def _with_session(fn: Callable[[Session], T]) -> T:
    session = _session_factory()()
    try:
        return fn(session)
    finally:
        session.close()


def fetch_signals(
    *,
    status: str | None = None,
    limit: int = 100,
) -> list[SignalRow]:
    def _run(session: Session) -> list[SignalRow]:
        q = (
            select(Signal, Market.question, Market.slug, Market.raw_metadata)
            .join(Market, Market.id == Signal.market_id)
            .order_by(Signal.generated_at.desc())
            .limit(limit)
        )
        if status:
            q = q.where(Signal.status == status)
        rows = session.execute(q).all()
        out: list[SignalRow] = []
        for s, question, slug, raw_meta in rows:
            url = polymarket_market_url(
                slug=slug,
                raw_metadata=raw_meta,
                question=str(question or ""),
            )
            out.append(
                SignalRow(
                    id=int(s.id),
                    generated_at=s.generated_at,
                    strategy=s.strategy,
                    side=s.side,
                    status=s.status,
                    market_price=float(s.market_price),
                    fair_value_estimate=float(s.fair_value_estimate),
                    edge_pct=float(s.edge_pct),
                    suggested_size_usd=float(s.suggested_size_usd),
                    question=str(question or ""),
                    polymarket_url=url,
                    metadata=s.signal_metadata,
                ),
            )
        return out

    return _with_session(_run)


def fetch_positions(
    *,
    status: str | None = None,
    limit: int = 100,
) -> list[PositionRow]:
    def _run(session: Session) -> list[PositionRow]:
        q = (
            select(Position, Market.question)
            .join(Market, Market.id == Position.market_id)
            .order_by(Position.entered_at.desc())
            .limit(limit)
        )
        if status:
            q = q.where(Position.status == status)
        rows = session.execute(q).all()
        return [
            PositionRow(
                id=int(p.id),
                strategy=p.strategy,
                side=p.side,
                status=p.status,
                is_paper=bool(p.is_paper),
                entry_price=float(p.entry_price),
                entry_size_usd=float(p.entry_size_usd),
                entered_at=p.entered_at,
                exit_price=float(p.exit_price) if p.exit_price is not None else None,
                exited_at=p.exited_at,
                realized_pnl_usd=float(p.realized_pnl_usd)
                if p.realized_pnl_usd is not None
                else None,
                realized_pnl_pct=float(p.realized_pnl_pct)
                if p.realized_pnl_pct is not None
                else None,
                question=str(question or ""),
            )
            for p, question in rows
        ]

    return _with_session(_run)


def fetch_journal(*, limit: int = 50) -> list[JournalRow]:
    def _run(session: Session) -> list[JournalRow]:
        rows = session.execute(
            select(DecisionJournal, Market.question)
            .join(Market, Market.id == DecisionJournal.market_id)
            .order_by(DecisionJournal.created_at.desc())
            .limit(limit),
        ).all()
        return [
            JournalRow(
                id=int(j.id),
                entry_type=j.entry_type,
                strategy=j.strategy,
                thesis=j.thesis,
                created_at=j.created_at,
                question=str(question or ""),
                expected_edge_pct=float(j.expected_edge_pct)
                if j.expected_edge_pct is not None
                else None,
            )
            for j, question in rows
        ]

    return _with_session(_run)


def fetch_pipeline_stats() -> PipelineStats:
    def _run(session: Session) -> PipelineStats:
        active = session.scalar(
            select(func.count()).select_from(Market).where(
                Market.is_active,
                ~Market.is_closed,
            ),
        )
        br = session.scalar(
            select(func.count()).select_from(Market).where(Market.has_base_rate.is_(True)),
        )
        snaps = session.scalar(select(func.count()).select_from(MarketSnapshot))
        last_snap = session.scalar(select(func.max(MarketSnapshot.snapshot_at)))

        status_rows = session.execute(
            select(Signal.status, func.count())
            .group_by(Signal.status)
            .order_by(func.count().desc()),
        ).all()
        signal_counts = {str(s): int(c) for s, c in status_rows}

        return PipelineStats(
            active_markets=int(active or 0),
            base_rate_markets=int(br or 0),
            snapshot_count=int(snaps or 0),
            last_snapshot_at=last_snap,
            signal_counts=signal_counts,
        )

    return _with_session(_run)


def fetch_performance_daily(*, limit: int = 90) -> list[PerformanceDaily]:
    def _run(session: Session) -> list[PerformanceDaily]:
        return list(
            session.execute(
                select(PerformanceDaily)
                .order_by(PerformanceDaily.date.desc())
                .limit(limit),
            )
            .scalars()
            .all(),
        )

    return _with_session(_run)


def fetch_realized_pnl_total() -> float:
    def _run(session: Session) -> float:
        total = session.scalar(
            select(func.coalesce(func.sum(Position.realized_pnl_usd), 0)).where(
                Position.status == "CLOSED",
            ),
        )
        return float(total or 0)

    return _with_session(_run)
