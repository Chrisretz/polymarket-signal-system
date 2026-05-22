"""Tests for event snapshot aggregation (Strategi C Fase 1)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pss.db.models import Event, Market, MarketSnapshot
from pss.events.snapshot import (
    _inconsistency_pp,
    build_event_snapshot_row,
    build_leg_details,
    snapshot_events,
)


def _market(
    market_id: int,
    *,
    condition_id: str | None = None,
    event_id: str = "evt-1",
) -> Market:
    market = Market(
        condition_id=condition_id or f"cond-{market_id}",
        question=f"Q{market_id}",
        yes_token_id=f"yes-{market_id}",
        no_token_id=f"no-{market_id}",
        event_id=event_id,
    )
    market.id = market_id
    return market


def _snapshot(
    market_id: int,
    *,
    yes_price: float | None = 0.3,
    liquidity_usd: float = 100.0,
    yes_best_bid: float | None = 0.29,
    yes_best_ask: float | None = 0.31,
) -> MarketSnapshot:
    return MarketSnapshot(
        market_id=market_id,
        snapshot_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
        yes_price=yes_price,
        no_price=1.0 - yes_price if yes_price is not None else None,
        yes_best_bid=yes_best_bid,
        yes_best_ask=yes_best_ask,
        liquidity_usd=liquidity_usd,
    )


def _event(*, event_id: str = "evt-1", internal_id: int = 1) -> Event:
    event = Event(event_id=event_id, title="Test Event", neg_risk=True)
    event.id = internal_id
    return event


class TestBuildLegDetails:
    def test_three_markets_all_have_snapshots_success(self) -> None:
        markets = [_market(i) for i in (1, 2, 3)]
        latest = {
            1: _snapshot(1, yes_price=0.3, liquidity_usd=200),
            2: _snapshot(2, yes_price=0.35, liquidity_usd=150),
            3: _snapshot(3, yes_price=0.35, liquidity_usd=500),
        }

        result = build_leg_details(markets, latest)

        assert result is not None
        legs, sum_yes, min_liq = result
        assert len(legs) == 3
        assert sum_yes == pytest.approx(1.0)
        assert min_liq == 150.0

    def test_three_markets_one_missing_snapshot_skips(self) -> None:
        markets = [_market(i) for i in (1, 2, 3)]
        latest = {
            1: _snapshot(1),
            2: _snapshot(2),
        }

        assert build_leg_details(markets, latest) is None

    def test_five_markets_three_snapshots_skips(self) -> None:
        markets = [_market(i) for i in (1, 2, 3, 4, 5)]
        latest = {
            1: _snapshot(1),
            2: _snapshot(2),
            3: _snapshot(3),
        }

        assert build_leg_details(markets, latest) is None

    def test_sum_and_inconsistency_calculated_correctly(self) -> None:
        markets = [_market(i) for i in (1, 2, 3)]
        latest = {
            1: _snapshot(1, yes_price=0.4),
            2: _snapshot(2, yes_price=0.35),
            3: _snapshot(3, yes_price=0.20),
        }

        result = build_leg_details(markets, latest)
        assert result is not None
        _, sum_yes, _ = result
        assert sum_yes == pytest.approx(0.95)
        assert _inconsistency_pp(sum_yes) == pytest.approx(5.0)

    def test_min_leg_liquidity_is_minimum(self) -> None:
        markets = [_market(i) for i in (1, 2, 3)]
        latest = {
            1: _snapshot(1, liquidity_usd=1000),
            2: _snapshot(2, liquidity_usd=50),
            3: _snapshot(3, liquidity_usd=300),
        }

        result = build_leg_details(markets, latest)
        assert result is not None
        _, _, min_liq = result
        assert min_liq == 50.0

    def test_missing_yes_price_skips(self) -> None:
        markets = [_market(i) for i in (1, 2, 3)]
        latest = {
            1: _snapshot(1),
            2: _snapshot(2),
            3: _snapshot(3, yes_price=None),
        }

        assert build_leg_details(markets, latest) is None


class TestBuildEventSnapshotRow:
    def test_builds_row_with_expected_fields(self) -> None:
        event = _event()
        markets = [_market(i) for i in (1, 2, 3)]
        latest = {i: _snapshot(i, yes_price=1 / 3) for i in (1, 2, 3)}
        snapshot_at = datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc)

        row = build_event_snapshot_row(event, markets, latest, snapshot_at)

        assert row is not None
        assert row["event_id"] == 1
        assert row["snapshot_at"] == snapshot_at
        assert row["leg_count"] == 3
        assert row["sum_yes_prices"] == pytest.approx(1.0)
        assert row["inconsistency_pp"] == pytest.approx(0.0)
        assert len(row["leg_details"]) == 3
        assert row["leg_details"][0]["yes_best_bid"] == pytest.approx(0.29)


def test_snapshot_events_processes_complete_events_only() -> None:
    event_ok = _event(event_id="ok", internal_id=10)
    event_incomplete = _event(event_id="bad", internal_id=11)

    market_a = _market(1, event_id="ok")
    market_b = _market(2, event_id="ok")
    market_c = _market(3, event_id="ok")
    market_d = _market(4, event_id="bad")
    market_e = _market(5, event_id="bad")
    market_f = _market(6, event_id="bad")

    latest = {
        1: _snapshot(1, yes_price=0.34),
        2: _snapshot(2, yes_price=0.33),
        3: _snapshot(3, yes_price=0.33),
        4: _snapshot(4, yes_price=0.5),
        5: _snapshot(5, yes_price=0.5),
    }

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    events_result = MagicMock()
    events_result.scalars.return_value.all.return_value = [event_ok, event_incomplete]

    markets_result = MagicMock()
    markets_result.scalars.return_value.all.return_value = [
        market_a,
        market_b,
        market_c,
        market_d,
        market_e,
        market_f,
    ]

    snapshots_result = MagicMock()
    snapshots_result.scalars.return_value.all.return_value = list(latest.values())

    mock_session.execute = AsyncMock(
        side_effect=[events_result, markets_result, snapshots_result, MagicMock()],
    )

    async def _run() -> int:
        with patch("pss.events.snapshot.AsyncSessionLocal", return_value=mock_session):
            result = await snapshot_events()
            return result.processed

    count = asyncio.run(_run())

    assert count == 1
    mock_session.commit.assert_awaited_once()
