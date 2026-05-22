"""Evaluér manuelt definerede relationer mellem gruppe-markeder."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class RelationResult:
    relation_type: str
    label: str
    expected_pp: float | None
    actual_pp: float | None
    inconsistency_pp: float
    signed_deviation_pp: float | None
    details: dict[str, Any] = field(default_factory=dict)


def _missing_result(
    relation_type: str,
    label: str,
    *,
    details: dict[str, Any] | None = None,
) -> RelationResult:
    return RelationResult(
        relation_type=relation_type,
        label=label,
        expected_pp=None,
        actual_pp=None,
        inconsistency_pp=0.0,
        signed_deviation_pp=None,
        details=details or {"error": "missing_role_price"},
    )


def relation_row_signed_pp(rel: dict[str, Any]) -> float | None:
    """Signed afvigelse fra snapshot-række; fallback for ældre snapshots."""
    if rel.get("signed_deviation_pp") is not None:
        return float(rel["signed_deviation_pp"])
    actual = rel.get("actual_pp")
    expected = rel.get("expected_pp")
    if actual is not None and expected is not None:
        return float(actual) - float(expected)
    return None


def _prob(prices: dict[str, float], role: str) -> float | None:
    if role not in prices:
        return None
    return float(prices[role])


def evaluate_sum_equals(
    definition: dict[str, Any],
    prices: dict[str, float],
) -> RelationResult:
    """P(target) skal ≈ sum P(components)."""
    target = definition["target_role"]
    components = definition["component_roles"]
    label = definition.get("label") or f"{target} = sum({', '.join(components)})"

    p_target = _prob(prices, target)
    comp_probs = [_prob(prices, r) for r in components]
    if p_target is None or any(p is None for p in comp_probs):
        return _missing_result("sum_equals", label)

    expected = sum(comp_probs)  # type: ignore[arg-type]
    signed = (p_target - expected) * 100
    return RelationResult(
        relation_type="sum_equals",
        label=label,
        expected_pp=expected * 100,
        actual_pp=p_target * 100,
        inconsistency_pp=abs(signed),
        signed_deviation_pp=signed,
        details={
            "target_role": target,
            "component_roles": components,
            "component_probs_pp": {r: prices[r] * 100 for r in components},
        },
    )


def evaluate_implied_lte(
    definition: dict[str, Any],
    prices: dict[str, float],
) -> RelationResult:
    """P(left) ≤ P(right) — probabilistisk implikation."""
    left = definition["left_role"]
    right = definition["right_role"]
    label = definition.get("label") or f"P({left}) ≤ P({right})"

    p_left = _prob(prices, left)
    p_right = _prob(prices, right)
    if p_left is None or p_right is None:
        return _missing_result("implied_lte", label)

    signed = (p_left - p_right) * 100
    return RelationResult(
        relation_type="implied_lte",
        label=label,
        expected_pp=p_right * 100,
        actual_pp=p_left * 100,
        inconsistency_pp=max(0.0, signed),
        signed_deviation_pp=signed,
        details={"left_role": left, "right_role": right},
    )


def evaluate_target_equals(
    definition: dict[str, Any],
    prices: dict[str, float],
) -> RelationResult:
    """P(role) skal ≈ target_probability (0–1)."""
    role = definition["role"]
    target = float(definition["target_probability"])
    label = definition.get("label") or f"{role} ≈ {target:.0%}"

    p = _prob(prices, role)
    if p is None:
        return _missing_result("target_equals", label)

    signed = (p - target) * 100
    return RelationResult(
        relation_type="target_equals",
        label=label,
        expected_pp=target * 100,
        actual_pp=p * 100,
        inconsistency_pp=abs(signed),
        signed_deviation_pp=signed,
        details={"role": role},
    )


def evaluate_weighted_sum_equals(
    definition: dict[str, Any],
    prices: dict[str, float],
) -> RelationResult:
    """P(target) ≈ sum(weight_i * P(role_i))."""
    target = definition["target_role"]
    components = definition["components"]
    label = definition.get("label") or (
        f"{target} = " + " + ".join(f"{c.get('weight', 1)}*{c['role']}" for c in components)
    )

    p_target = _prob(prices, target)
    weighted_parts: list[tuple[str, float, float | None]] = []
    for comp in components:
        role = comp["role"]
        weight = float(comp.get("weight", 1.0))
        p = _prob(prices, role)
        weighted_parts.append((role, weight, p))

    if p_target is None or any(p is None for _, _, p in weighted_parts):
        return _missing_result("weighted_sum_equals", label)

    expected = sum(w * p for _, w, p in weighted_parts)  # type: ignore[misc]
    signed = (p_target - expected) * 100
    return RelationResult(
        relation_type="weighted_sum_equals",
        label=label,
        expected_pp=expected * 100,
        actual_pp=p_target * 100,
        inconsistency_pp=abs(signed),
        signed_deviation_pp=signed,
        details={
            "target_role": target,
            "components": [
                {"role": r, "weight": w, "prob_pp": prices[r] * 100}
                for r, w, _ in weighted_parts
            ],
        },
    )


def evaluate_sum_to_target(
    definition: dict[str, Any],
    prices: dict[str, float],
) -> RelationResult:
    """sum(P(components)) ≈ target_probability — typisk 1.0 for mutually exclusive buckets."""
    components = definition["component_roles"]
    target = float(definition.get("target_probability", 1.0))
    label = definition.get("label") or (
        f"sum({', '.join(components)}) ≈ {target:.0%}"
    )

    comp_probs = [_prob(prices, r) for r in components]
    if any(p is None for p in comp_probs):
        return _missing_result("sum_to_target", label)

    actual = sum(comp_probs)  # type: ignore[arg-type]
    signed = (actual - target) * 100
    return RelationResult(
        relation_type="sum_to_target",
        label=label,
        expected_pp=target * 100,
        actual_pp=actual * 100,
        inconsistency_pp=abs(signed),
        signed_deviation_pp=signed,
        details={
            "component_roles": components,
            "component_probs_pp": {r: prices[r] * 100 for r in components},
            "target_probability": target,
        },
    )


_EVALUATORS = {
    "sum_equals": evaluate_sum_equals,
    "sum_to_target": evaluate_sum_to_target,
    "weighted_sum_equals": evaluate_weighted_sum_equals,
    "implied_lte": evaluate_implied_lte,
    "target_equals": evaluate_target_equals,
}


def evaluate_relation(
    relation_type: str,
    definition: dict[str, Any],
    prices: dict[str, float],
) -> RelationResult:
    fn = _EVALUATORS.get(relation_type)
    if fn is None:
        return RelationResult(
            relation_type=relation_type,
            label=definition.get("label") or relation_type,
            expected_pp=None,
            actual_pp=None,
            inconsistency_pp=0.0,
            signed_deviation_pp=None,
            details={"error": f"unknown_relation_type:{relation_type}"},
        )
    return fn(definition, prices)


def evaluate_group_relations(
    relations: list[tuple[str, dict[str, Any]]],
    prices: dict[str, float],
    *,
    threshold_pp: float = 3.0,
) -> dict[str, Any]:
    """Evaluér alle relationer; returnér metrics til snapshot/alert."""
    results: list[dict[str, Any]] = []
    max_inconsistency = 0.0
    alerts: list[dict[str, Any]] = []

    for relation_type, definition in relations:
        r = evaluate_relation(relation_type, definition, prices)
        row = {
            "relation_type": r.relation_type,
            "label": r.label,
            "expected_pp": r.expected_pp,
            "actual_pp": r.actual_pp,
            "inconsistency_pp": r.inconsistency_pp,
            "signed_deviation_pp": r.signed_deviation_pp,
            "details": r.details,
        }
        results.append(row)
        max_inconsistency = max(max_inconsistency, r.inconsistency_pp)
        if r.inconsistency_pp >= threshold_pp:
            alerts.append(row)

    return {
        "prices_pp": {k: v * 100 for k, v in prices.items()},
        "relations": results,
        "max_inconsistency_pp": max_inconsistency,
        "alerts": alerts,
        "alert_count": len(alerts),
    }


def validate_relation_definition(relation_type: str, definition: dict[str, Any]) -> None:
    """Valider definition før persist."""
    if relation_type == "sum_equals":
        if not definition.get("target_role"):
            raise ValueError("sum_equals kræver target_role")
        comps = definition.get("component_roles")
        if not comps or not isinstance(comps, list):
            raise ValueError("sum_equals kræver component_roles (liste)")
    elif relation_type == "sum_to_target":
        comps = definition.get("component_roles")
        if not comps or not isinstance(comps, list):
            raise ValueError("sum_to_target kræver component_roles (liste)")
        if "target_probability" in definition:
            t = float(definition["target_probability"])
            if not 0 <= t <= 1:
                raise ValueError("target_probability skal være mellem 0 og 1")
    elif relation_type == "weighted_sum_equals":
        if not definition.get("target_role"):
            raise ValueError("weighted_sum_equals kræver target_role")
        comps = definition.get("components")
        if not comps or not isinstance(comps, list):
            raise ValueError("weighted_sum_equals kræver components (liste med role, weight)")
        for comp in comps:
            if not comp.get("role"):
                raise ValueError("hvert component skal have role")
    elif relation_type == "implied_lte":
        if not definition.get("left_role") or not definition.get("right_role"):
            raise ValueError("implied_lte kræver left_role og right_role")
    elif relation_type == "target_equals":
        if not definition.get("role") or "target_probability" not in definition:
            raise ValueError("target_equals kræver role og target_probability")
    else:
        raise ValueError(f"Ukendt relation_type: {relation_type}")
