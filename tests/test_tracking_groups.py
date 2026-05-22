"""Tests for tracked group relations and URL parsing."""

from __future__ import annotations

import pytest

from pss.tracking.relations import (
    evaluate_group_relations,
    evaluate_relation,
    relation_row_signed_pp,
    validate_relation_definition,
)

CONDITION = "0x" + "a" * 64


class TestRelations:
    def test_sum_equals_consistent(self) -> None:
        prices = {"red_govt": 0.45, "party_a": 0.25, "party_b": 0.20}
        r = evaluate_relation(
            "sum_equals",
            {
                "target_role": "red_govt",
                "component_roles": ["party_a", "party_b"],
            },
            prices,
        )
        assert r.inconsistency_pp == pytest.approx(0.0, abs=0.01)
        assert r.signed_deviation_pp == pytest.approx(0.0, abs=0.01)

    def test_sum_equals_inconsistent(self) -> None:
        prices = {"red_govt": 0.50, "party_a": 0.25, "party_b": 0.20}
        r = evaluate_relation(
            "sum_equals",
            {
                "target_role": "red_govt",
                "component_roles": ["party_a", "party_b"],
            },
            prices,
        )
        assert r.inconsistency_pp == pytest.approx(5.0, abs=0.01)
        assert r.signed_deviation_pp == pytest.approx(5.0, abs=0.01)

    def test_implied_lte_consistent_signed(self) -> None:
        prices = {"left": 0.40, "right": 0.60}
        r = evaluate_relation(
            "implied_lte",
            {"left_role": "left", "right_role": "right"},
            prices,
        )
        assert r.inconsistency_pp == pytest.approx(0.0, abs=0.01)
        assert r.signed_deviation_pp == pytest.approx(-20.0, abs=0.01)

    def test_implied_lte_violation(self) -> None:
        prices = {"win_election": 0.60, "win_state": 0.50}
        r = evaluate_relation(
            "implied_lte",
            {"left_role": "win_election", "right_role": "win_state"},
            prices,
        )
        assert r.inconsistency_pp == pytest.approx(10.0, abs=0.01)
        assert r.signed_deviation_pp == pytest.approx(10.0, abs=0.01)

    def test_group_evaluation_alerts(self) -> None:
        relations = [
            (
                "sum_equals",
                {
                    "target_role": "red_govt",
                    "component_roles": ["party_a", "party_b"],
                    "label": "Red bloc",
                },
            ),
        ]
        metrics = evaluate_group_relations(
            relations,
            {"red_govt": 0.55, "party_a": 0.25, "party_b": 0.20},
            threshold_pp=3.0,
        )
        assert metrics["alert_count"] == 1
        assert metrics["max_inconsistency_pp"] == pytest.approx(10.0, abs=0.01)
        rel = metrics["relations"][0]
        assert rel["signed_deviation_pp"] == pytest.approx(10.0, abs=0.01)
        assert rel["inconsistency_pp"] == pytest.approx(10.0, abs=0.01)

    def test_validate_sum_equals(self) -> None:
        validate_relation_definition(
            "sum_equals",
            {"target_role": "a", "component_roles": ["b", "c"]},
        )

    def test_validate_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Ukendt"):
            validate_relation_definition("magic", {})

    def test_weighted_sum_equals(self) -> None:
        prices = {"sf_in_gov": 0.40, "bloc_red": 0.25, "bloc_lilla": 0.30}
        r = evaluate_relation(
            "weighted_sum_equals",
            {
                "target_role": "sf_in_gov",
                "components": [
                    {"role": "bloc_red", "weight": 1.0},
                    {"role": "bloc_lilla", "weight": 0.7},
                ],
            },
            prices,
        )
        expected = 0.25 + 0.7 * 0.30
        assert r.inconsistency_pp == pytest.approx(abs(0.40 - expected) * 100, abs=0.01)

    def test_validate_weighted_sum_equals(self) -> None:
        validate_relation_definition(
            "weighted_sum_equals",
            {
                "target_role": "sf_in_gov",
                "components": [{"role": "bloc_red", "weight": 1.0}],
            },
        )

    def test_sum_to_target_buckets(self) -> None:
        prices = {"b1": 0.40, "b2": 0.35, "b3": 0.24}
        r = evaluate_relation(
            "sum_to_target",
            {"component_roles": ["b1", "b2", "b3"], "target_probability": 1.0},
            prices,
        )
        assert r.inconsistency_pp == pytest.approx(1.0, abs=0.01)
        assert r.actual_pp == pytest.approx(99.0, abs=0.01)
        assert r.signed_deviation_pp == pytest.approx(-1.0, abs=0.01)

    def test_relation_row_signed_pp_fallback(self) -> None:
        assert relation_row_signed_pp({"signed_deviation_pp": -5.0}) == -5.0
        assert relation_row_signed_pp({"actual_pp": 70.0, "expected_pp": 88.0}) == pytest.approx(-18.0)
