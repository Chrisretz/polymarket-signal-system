"""Tests for Polymarket reference parsing."""

from __future__ import annotations

import pytest

from pss.tracking.groups import parse_market_reference
from pss.tracking.market_refs import EventUrlError, parse_event_reference, suggest_role_label


CONDITION = "0x" + "a" * 64


class TestSuggestRoleLabel:
    def test_danish_name(self) -> None:
        assert suggest_role_label("Mette Frederiksen") == "mette_frederiksen"

    def test_from_question_heuristic(self) -> None:
        role = suggest_role_label("Will Gavin Newsom win?")
        assert role  # fallback via question path uses full string if no groupItemTitle


class TestParseMarketReference:
    def test_condition_id(self) -> None:
        kind, val = parse_market_reference(CONDITION)
        assert kind == "condition_id"
        assert val == CONDITION

    def test_event_only_url(self) -> None:
        kind, val = parse_market_reference(
            "https://polymarket.com/event/next-prime-minister-of-denmark-after-parliamentary-election",
        )
        assert kind == "event_slug"
        assert val == "next-prime-minister-of-denmark-after-parliamentary-election"

    def test_fed_event_url(self) -> None:
        kind, val = parse_market_reference(
            "https://polymarket.com/event/fed-rate-cut-by-629",
        )
        assert kind == "event_slug"
        assert val == "fed-rate-cut-by-629"

    def test_market_url(self) -> None:
        kind, val = parse_market_reference(
            "https://polymarket.com/market/fed-rate-cut-by-june-2026-meeting",
        )
        assert kind == "market_slug"
        assert val == "fed-rate-cut-by-june-2026-meeting"

    def test_nested_event_url_is_market(self) -> None:
        kind, val = parse_market_reference(
            "https://polymarket.com/event/parent-event/child-market",
        )
        assert kind == "market_slug"
        assert val == "child-market"

    def test_plain_slug(self) -> None:
        kind, val = parse_market_reference("fed-decision-january")
        assert kind == "market_slug"
        assert val == "fed-decision-january"


class TestEventUrlError:
    def test_message(self) -> None:
        err = EventUrlError("my-event")
        assert err.event_slug == "my-event"
        assert "event-link" in str(err).lower() or "event-link" in str(err)


class TestParseEventReference:
    def test_event_url(self) -> None:
        kind, val = parse_event_reference(
            "https://polymarket.com/event/next-prime-minister-of-denmark-after-parliamentary-election",
        )
        assert kind == "slug"
        assert val == "next-prime-minister-of-denmark-after-parliamentary-election"

    def test_plain_slug(self) -> None:
        kind, val = parse_event_reference("fed-rate-cut-by-629")
        assert kind == "slug"
        assert val == "fed-rate-cut-by-629"

    def test_numeric_id(self) -> None:
        kind, val = parse_event_reference("12345")
        assert kind == "id"
        assert val == "12345"

    def test_market_url_rejected(self) -> None:
        with pytest.raises(ValueError, match="event-URL"):
            parse_event_reference(
                "https://polymarket.com/market/fed-rate-cut-by-june-2026-meeting",
            )
