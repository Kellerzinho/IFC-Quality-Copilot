"""Contrato dos metadados científicos do ground truth integral."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.experiment.ground_truth_policy import (
    GroundTruthDecision,
    assert_equivalence_ids_unique,
)


def test_accepts_complete_high_confidence_decision():
    decision = GroundTruthDecision(
        expected_value=False,
        confidence="high",
        source_kind="ifc_alias",
        notes="LoadBearing=false lido literalmente do IFC.",
    )

    assert decision.expected_value is False
    assert decision.legacy_reference is False


@pytest.mark.parametrize(
    "value",
    [None, "", "unknown", "not_applicable", "review_required", "pending_review"],
)
def test_rejects_non_concrete_expected_values(value: object):
    with pytest.raises(ValidationError, match="concrete expected_value"):
        GroundTruthDecision(
            expected_value=value,
            confidence="high",
            source_kind="ifc_literal",
            notes="Evidência literal.",
        )


def test_rejects_low_confidence_without_explicit_frozen_hypothesis():
    with pytest.raises(ValidationError, match="Hipótese congelada"):
        GroundTruthDecision(
            expected_value="REI 60",
            confidence="low",
            source_kind="probable",
            notes="Valor mais provável para o elemento.",
        )


def test_rejects_duplicate_alternative_after_text_normalization():
    with pytest.raises(ValidationError, match="accepted alternative duplicates"):
        GroundTruthDecision(
            expected_value="REI 60",
            accepted_alternatives=["  rei   60 "],
            confidence="medium",
            source_kind="typology",
            notes="Referência tipológica congelada.",
        )


def test_rejects_unknown_confidence_and_source_kind():
    with pytest.raises(ValidationError):
        GroundTruthDecision(
            expected_value=2.48,
            confidence="certain",
            source_kind="internet",
            notes="Fonte inválida.",
        )


def test_detects_truncated_hash_collision_between_different_payloads():
    with pytest.raises(ValueError, match="equivalence_id collision"):
        assert_equivalence_ids_unique(
            [
                ("eq-aabbccddeeff0011", {"components": ["wall"]}),
                ("eq-aabbccddeeff0011", {"components": ["door"]}),
            ]
        )


def test_accepts_repeated_id_for_identical_payload():
    payload = {"schema": "reuse-equivalent-v1", "components": ["wall"]}
    assert_equivalence_ids_unique(
        [("eq-aabbccddeeff0011", payload), ("eq-aabbccddeeff0011", dict(payload))]
    )
