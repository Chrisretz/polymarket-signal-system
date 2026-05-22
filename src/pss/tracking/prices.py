"""Hent og normalisér priser for tracked group markeder."""

from __future__ import annotations

import json
from typing import Any

VALID_OUTCOME_SIDES = frozenset({"yes", "no"})


def parse_gamma_outcome_prices(market_payload: dict[str, Any]) -> tuple[float | None, float | None]:
    """Returnerer (yes_price, no_price) fra Gamma outcomePrices."""
    raw = market_payload.get("outcomePrices")
    if raw is None:
        return None, None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None, None
    if not isinstance(raw, list) or len(raw) < 1:
        return None, None
    try:
        yes = float(raw[0])
        no = float(raw[1]) if len(raw) > 1 else max(0.0, 1.0 - yes)
        return yes, no
    except (TypeError, ValueError):
        return None, None


def parse_gamma_yes_price(market_payload: dict[str, Any]) -> float | None:
    yes, _ = parse_gamma_outcome_prices(market_payload)
    return yes


def probability_for_outcome(yes_price: float, outcome_side: str) -> float:
    """Binært marked: yes_price = P(YES); NO = 1 - yes_price."""
    side = outcome_side.strip().lower()
    if side not in VALID_OUTCOME_SIDES:
        raise ValueError(f"outcome_side skal være 'yes' eller 'no', fik '{outcome_side}'")
    if side == "no":
        return max(0.0, min(1.0, 1.0 - yes_price))
    return max(0.0, min(1.0, yes_price))


def build_role_prices(
    rows: list[tuple[str, str, float | None]],
) -> dict[str, float]:
    """rows: (role_label, outcome_side, yes_price)."""
    prices: dict[str, float] = {}
    for role_label, outcome_side, yes_price in rows:
        if yes_price is None:
            continue
        prices[role_label] = probability_for_outcome(yes_price, outcome_side)
    return prices
