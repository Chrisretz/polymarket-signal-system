"""Tests for price normalization."""

from __future__ import annotations

import pytest

from pss.tracking.prices import build_role_prices, parse_gamma_yes_price, probability_for_outcome


def test_parse_gamma_yes_price_list() -> None:
    assert parse_gamma_yes_price({"outcomePrices": ["0.42", "0.58"]}) == pytest.approx(0.42)


def test_parse_gamma_yes_price_json_string() -> None:
    assert parse_gamma_yes_price({"outcomePrices": '["0.55", "0.45"]'}) == pytest.approx(0.55)


def test_probability_for_no_side() -> None:
    assert probability_for_outcome(0.60, "no") == pytest.approx(0.40)


def test_build_role_prices() -> None:
    prices = build_role_prices([("a", "yes", 0.5), ("b", "no", 0.8)])
    assert prices["a"] == pytest.approx(0.5)
    assert prices["b"] == pytest.approx(0.2)
