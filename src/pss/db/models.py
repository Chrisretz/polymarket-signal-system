"""SQLAlchemy-modeller — matcher IMPLEMENTATION.md §3.1."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime


class Base(DeclarativeBase):
    """Base for alle ORM-modeller."""


class Market(Base):
    __tablename__ = "markets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    condition_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    slug: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    subcategory: Mapped[str | None] = mapped_column(Text)
    event_id: Mapped[str | None] = mapped_column(Text)
    yes_token_id: Mapped[str] = mapped_column(Text, nullable=False)
    no_token_id: Mapped[str] = mapped_column(Text, nullable=False)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_source: Mapped[str | None] = mapped_column(Text)
    minimum_tick_size: Mapped[float | None] = mapped_column(Numeric(6, 4))
    neg_risk: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    resolved_outcome: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    primary_vertical: Mapped[str | None] = mapped_column(Text)
    raw_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    snapshots: Mapped[list[MarketSnapshot]] = relationship(back_populates="market")
    signals: Mapped[list[Signal]] = relationship(back_populates="market")
    positions: Mapped[list[Position]] = relationship(back_populates="market")

    __table_args__ = (
        Index("idx_markets_active", "is_active", "is_closed"),
        Index(
            "idx_markets_vertical",
            "primary_vertical",
            postgresql_where=text("is_active = TRUE"),
        ),
        Index(
            "idx_markets_end_date",
            "end_date",
            postgresql_where=text("is_active = TRUE"),
        ),
    )


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    market_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("markets.id", ondelete="CASCADE"),
        primary_key=True,
    )
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
    )
    yes_price: Mapped[float | None] = mapped_column(Numeric(8, 5))
    no_price: Mapped[float | None] = mapped_column(Numeric(8, 5))
    yes_best_bid: Mapped[float | None] = mapped_column(Numeric(8, 5))
    yes_best_ask: Mapped[float | None] = mapped_column(Numeric(8, 5))
    spread: Mapped[float | None] = mapped_column(Numeric(8, 5))
    volume_24h: Mapped[float | None] = mapped_column(Numeric(18, 2))
    volume_total: Mapped[float | None] = mapped_column(Numeric(18, 2))
    liquidity_usd: Mapped[float | None] = mapped_column(Numeric(18, 2))

    market: Mapped[Market] = relationship(back_populates="snapshots")

    __table_args__ = (
        Index(
            "idx_snapshots_market_time",
            "market_id",
            snapshot_at.desc(),
        ),
    )


class OrderbookDepth(Base):
    __tablename__ = "orderbook_depth"

    market_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("markets.id", ondelete="CASCADE"),
        primary_key=True,
    )
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
    )
    token_id: Mapped[str] = mapped_column(Text, primary_key=True)
    bids: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    asks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    depth_5pct_bid: Mapped[float | None] = mapped_column(Numeric(18, 2))
    depth_5pct_ask: Mapped[float | None] = mapped_column(Numeric(18, 2))

    market: Mapped[Market] = relationship()


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    slug: Mapped[str | None] = mapped_column(Text)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    neg_risk: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    raw_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    snapshots: Mapped[list[EventSnapshot]] = relationship(back_populates="event")

    __table_args__ = (
        Index("idx_events_active", "is_active"),
        Index("idx_events_end_date", "end_date"),
    )


class EventSnapshot(Base):
    __tablename__ = "event_snapshots"

    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("events.id", ondelete="CASCADE"),
        primary_key=True,
    )
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
    )
    leg_count: Mapped[int] = mapped_column(Integer, nullable=False)
    sum_yes_prices: Mapped[float] = mapped_column(Numeric(8, 5), nullable=False)
    inconsistency_pp: Mapped[float] = mapped_column(Numeric(8, 5), nullable=False)
    min_leg_liquidity_usd: Mapped[float | None] = mapped_column(Numeric(18, 2))
    leg_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    event: Mapped[Event] = relationship(back_populates="snapshots")

    __table_args__ = (
        Index(
            "idx_event_snapshots_event",
            "event_id",
            snapshot_at.desc(),
        ),
    )


class BaseRate(Base):
    __tablename__ = "base_rates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    base_probability: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    confidence_lower: Mapped[float | None] = mapped_column(Numeric(5, 4))
    confidence_upper: Mapped[float | None] = mapped_column(Numeric(5, 4))
    source: Mapped[str | None] = mapped_column(Text)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("idx_base_rates_category", "category"),)


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    market_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("markets.id"),
        nullable=False,
    )
    strategy: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    side: Mapped[str] = mapped_column(Text, nullable=False)
    market_price: Mapped[float] = mapped_column(Numeric(8, 5), nullable=False)
    fair_value_estimate: Mapped[float] = mapped_column(Numeric(8, 5), nullable=False)
    edge_pct: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2))
    suggested_size_usd: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    kelly_fraction: Mapped[float | None] = mapped_column(Numeric(6, 4))
    exit_price_target: Mapped[float | None] = mapped_column(Numeric(8, 5))
    exit_date_target: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_conditions: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="NEW",
        server_default=text("'NEW'"),
    )
    rejected_reason: Mapped[str | None] = mapped_column(Text)
    signal_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Strategi C multi-leg (nullable for legacy Strategi A rows)
    event_id: Mapped[str | None] = mapped_column(Text)
    legs: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    sum_yes_prices: Mapped[float | None] = mapped_column(Numeric(8, 5))
    inconsistency_pp: Mapped[float | None] = mapped_column(Numeric(8, 5))
    net_edge_pp: Mapped[float | None] = mapped_column(Numeric(8, 5))
    min_leg_liquidity_usd: Mapped[float | None] = mapped_column(Numeric(18, 2))

    market: Mapped[Market] = relationship(back_populates="signals")
    positions: Mapped[list[Position]] = relationship(back_populates="signal")

    __table_args__ = (
        Index("idx_signals_status", "status", generated_at.desc()),
        Index("idx_signals_market", "market_id", generated_at.desc()),
    )


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    signal_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("signals.id"))
    market_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("markets.id"),
        nullable=False,
    )
    strategy: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    entry_price: Mapped[float] = mapped_column(Numeric(8, 5), nullable=False)
    entry_size_shares: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    entry_size_usd: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    entry_fees_usd: Mapped[float | None] = mapped_column(Numeric(18, 4))
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_price: Mapped[float | None] = mapped_column(Numeric(8, 5))
    exit_size_shares: Mapped[float | None] = mapped_column(Numeric(18, 4))
    exit_size_usd: Mapped[float | None] = mapped_column(Numeric(18, 2))
    exit_fees_usd: Mapped[float | None] = mapped_column(Numeric(18, 4))
    exited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_reason: Mapped[str | None] = mapped_column(Text)
    realized_pnl_usd: Mapped[float | None] = mapped_column(Numeric(18, 2))
    realized_pnl_pct: Mapped[float | None] = mapped_column(Numeric(8, 4))
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="OPEN",
        server_default=text("'OPEN'"),
    )
    is_paper: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    market: Mapped[Market] = relationship(back_populates="positions")
    signal: Mapped[Signal | None] = relationship(back_populates="positions")
    journal_entries: Mapped[list[DecisionJournal]] = relationship(back_populates="position")

    __table_args__ = (
        Index("idx_positions_status", "status", entered_at.desc()),
        Index("idx_positions_strategy", "strategy", "status"),
        Index("idx_positions_paper", "is_paper", "status"),
    )


class DecisionJournal(Base):
    __tablename__ = "decisions_journal"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    position_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("positions.id"))
    market_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("markets.id"),
        nullable=False,
    )
    entry_type: Mapped[str] = mapped_column(Text, nullable=False)
    strategy: Mapped[str | None] = mapped_column(Text)
    thesis: Mapped[str | None] = mapped_column(Text)
    base_rate_estimate: Mapped[float | None] = mapped_column(Numeric(5, 4))
    my_probability_estimate: Mapped[float | None] = mapped_column(Numeric(5, 4))
    expected_edge_pct: Mapped[float | None] = mapped_column(Numeric(6, 4))
    position_size_usd: Mapped[float | None] = mapped_column(Numeric(18, 2))
    exit_criteria: Mapped[str | None] = mapped_column(Text)
    invalidation_scenarios: Mapped[str | None] = mapped_column(Text)
    strongest_counter_argument: Mapped[str | None] = mapped_column(Text)
    potential_biases: Mapped[str | None] = mapped_column(Text)
    max_loss_impact: Mapped[str | None] = mapped_column(Text)
    outcome_matched_thesis: Mapped[bool | None] = mapped_column(Boolean)
    was_lucky_or_skilled: Mapped[str | None] = mapped_column(Text)
    lessons_learned: Mapped[str | None] = mapped_column(Text)
    calibration_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    position: Mapped[Position | None] = relationship(back_populates="journal_entries")
    market: Mapped[Market] = relationship()

    __table_args__ = (Index("idx_journal_position", "position_id"),)


class PerformanceDaily(Base):
    __tablename__ = "performance_daily"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    bankroll_start_usd: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    bankroll_end_usd: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    realized_pnl_usd: Mapped[float] = mapped_column(
        Numeric(18, 2),
        default=0,
        server_default=text("0"),
    )
    unrealized_pnl_usd: Mapped[float] = mapped_column(
        Numeric(18, 2),
        default=0,
        server_default=text("0"),
    )
    total_pnl_usd: Mapped[float] = mapped_column(
        Numeric(18, 2),
        default=0,
        server_default=text("0"),
    )
    open_positions_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
    )
    open_positions_usd: Mapped[float] = mapped_column(
        Numeric(18, 2),
        default=0,
        server_default=text("0"),
    )
    exposure_pct: Mapped[float | None] = mapped_column(Numeric(6, 4))
    trades_today: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    wins_today: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    losses_today: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    peak_bankroll_usd: Mapped[float | None] = mapped_column(Numeric(18, 2))
    drawdown_pct: Mapped[float | None] = mapped_column(Numeric(6, 4))
    strategy_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class NewsEvent(Base):
    __tablename__ = "news_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    relevance_tags: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    relevance_score: Mapped[float | None] = mapped_column(Numeric(3, 2))
    processed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
    )

    __table_args__ = (
        Index("idx_news_published", published_at.desc()),
        Index("idx_news_tags", "relevance_tags", postgresql_using="gin"),
    )


class TrackedGroup(Base):
    __tablename__ = "tracked_groups"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="active",
        server_default=text("'active'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    markets: Mapped[list[TrackedGroupMarket]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
    )
    relations: Mapped[list[TrackedGroupRelation]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
    )
    snapshots: Mapped[list[TrackedGroupSnapshot]] = relationship(back_populates="group")
    group_events: Mapped[list["TrackedGroupEvent"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
    )

    __table_args__ = (Index("idx_tracked_groups_status", "status"),)


class TrackedGroupEvent(Base):
    __tablename__ = "tracked_group_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tracked_groups.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_id: Mapped[str] = mapped_column(Text, nullable=False)
    event_title: Mapped[str] = mapped_column(Text, nullable=False)
    event_slug: Mapped[str] = mapped_column(Text, nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    group: Mapped[TrackedGroup] = relationship(back_populates="group_events")
    markets: Mapped[list["TrackedGroupMarket"]] = relationship(
        back_populates="group_event",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_tracked_group_events_group", "group_id"),
    )


class TrackedGroupMarket(Base):
    __tablename__ = "tracked_group_markets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tracked_groups.id", ondelete="CASCADE"),
        nullable=False,
    )
    group_event_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("tracked_group_events.id", ondelete="CASCADE"),
        nullable=True,
    )
    market_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("markets.id", ondelete="CASCADE"),
        nullable=False,
    )
    role_label: Mapped[str] = mapped_column(Text, nullable=False)
    outcome_side: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="yes",
        server_default=text("'yes'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    group: Mapped[TrackedGroup] = relationship(back_populates="markets")
    group_event: Mapped[TrackedGroupEvent | None] = relationship(back_populates="markets")
    market: Mapped[Market] = relationship()

    __table_args__ = (
        Index("idx_tracked_group_markets_group", "group_id"),
        Index("idx_tracked_group_markets_market", "market_id"),
        Index("idx_tracked_group_markets_group_event", "group_event_id"),
    )


class TrackedGroupRelation(Base):
    __tablename__ = "tracked_group_relations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tracked_groups.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(Text, nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    group: Mapped[TrackedGroup] = relationship(back_populates="relations")

    __table_args__ = (Index("idx_tracked_group_relations_group", "group_id"),)


class TrackedGroupSnapshot(Base):
    __tablename__ = "tracked_group_snapshots"

    group_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tracked_groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
    )
    calculated_metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    group: Mapped[TrackedGroup] = relationship(back_populates="snapshots")

    __table_args__ = (
        Index(
            "idx_tracked_group_snapshots_group",
            "group_id",
            snapshot_at.desc(),
        ),
    )
