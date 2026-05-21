"""Tests for event discovery (Strategi C Fase 1)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from pss.events.discovery import (
    MIN_LEG_COUNT,
    _event_values,
    _is_neg_risk_event,
    discover_events,
)


def _sample_event(
    *,
    event_id: str = "123",
    title: str = "Test event",
    neg_risk: bool = True,
    leg_count: int = 3,
) -> dict:
    markets = [{"id": str(i), "question": f"Leg {i}"} for i in range(leg_count)]
    return {
        "id": event_id,
        "title": title,
        "description": "desc",
        "slug": "test-event",
        "endDate": "2026-12-31T00:00:00Z",
        "active": True,
        "closed": False,
        "enableNegRisk": neg_risk,
        "markets": markets,
    }


class TestEventFilters:
    def test_neg_risk_from_enable_neg_risk(self) -> None:
        event = _sample_event(neg_risk=True)
        assert _is_neg_risk_event(event) is True

    def test_neg_risk_false_skipped(self) -> None:
        event = _sample_event(neg_risk=False)
        assert _event_values(event) is None

    def test_too_few_legs_skipped(self) -> None:
        event = _sample_event(leg_count=MIN_LEG_COUNT - 1)
        assert _event_values(event) is None

    def test_valid_event_maps_to_db_values(self) -> None:
        event = _sample_event(event_id="30615", leg_count=4)
        values = _event_values(event)
        assert values is not None
        assert values["event_id"] == "30615"
        assert values["neg_risk"] is True
        assert values["raw_metadata"] == event
        assert values["is_active"] is True
        assert values["is_resolved"] is False


def test_discover_events_upserts_matching_events() -> None:
    events = [
        _sample_event(event_id="1", leg_count=3),
        _sample_event(event_id="2", leg_count=2, neg_risk=True),
        _sample_event(event_id="3", leg_count=5, neg_risk=False),
    ]

    mock_gamma = MagicMock()
    mock_gamma.list_all_active_events = AsyncMock(return_value=events)
    mock_gamma.__aenter__ = AsyncMock(return_value=mock_gamma)
    mock_gamma.__aexit__ = AsyncMock(return_value=None)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    async def _run() -> int:
        with (
            patch("pss.events.discovery.GammaClient", return_value=mock_gamma),
            patch("pss.events.discovery.AsyncSessionLocal", return_value=mock_session),
        ):
            return await discover_events()

    count = asyncio.run(_run())

    assert count == 1
    assert mock_session.execute.await_count == 1
    mock_session.commit.assert_awaited_once()
