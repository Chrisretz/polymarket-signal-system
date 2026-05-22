"""Læselig formatering af tracked group relationer."""

from __future__ import annotations

from typing import Any

RELATION_TYPE_LABELS: dict[str, str] = {
    "sum_equals": "Sum equals",
    "sum_to_target": "Sum to target",
    "implied_lte": "Implikation (≤)",
    "target_equals": "Target probability",
    "weighted_sum_equals": "Weighted sum",
}


def format_relation_definition(relation_type: str, definition: dict[str, Any]) -> str:
    label = definition.get("label")
    if label:
        return str(label)

    if relation_type == "sum_equals":
        target = definition.get("target_role", "?")
        comps = definition.get("component_roles", [])
        return f"P({target}) ≈ " + " + ".join(f"P({r})" for r in comps)

    if relation_type == "sum_to_target":
        comps = definition.get("component_roles", [])
        target = float(definition.get("target_probability", 1.0))
        return f"sum({', '.join(comps)}) ≈ {target:.0%}"

    if relation_type == "implied_lte":
        left = definition.get("left_role", "?")
        right = definition.get("right_role", "?")
        return f"P({left}) ≤ P({right})"

    if relation_type == "target_equals":
        role = definition.get("role", "?")
        target = float(definition.get("target_probability", 0))
        return f"P({role}) ≈ {target:.0%}"

    if relation_type == "weighted_sum_equals":
        target = definition.get("target_role", "?")
        parts = []
        for c in definition.get("components", []):
            w = c.get("weight", 1.0)
            parts.append(f"{w}×P({c.get('role', '?')})")
        return f"P({target}) ≈ " + " + ".join(parts)

    return str(definition)


def relation_eval_from_metrics(
    metrics: dict[str, Any] | None,
    relation_type: str,
    definition: dict[str, Any],
) -> dict[str, Any] | None:
    """Find seneste evaluering for en relation (match på label eller type)."""
    if not metrics:
        return None
    want_label = format_relation_definition(relation_type, definition)
    for row in metrics.get("relations", []):
        if row.get("label") == want_label:
            return row
        if row.get("relation_type") == relation_type and definition.get("label") is None:
            return row
    return None
