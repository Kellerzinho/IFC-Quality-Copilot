"""Contrato científico dos ground truths integrais congelados."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.experiment.evaluator import Evaluator, GroundTruth, GroundTruthItem
from src.experiment.ground_truth_validation import (
    ACOUSTIC_RATING_PATTERN,
    CATEGORY_VALUES,
    FIRE_RATING_PATTERN,
    IFC_RELATION_PATTERN,
    SLAB_SYSTEM_VALUES,
    WALL_SYSTEM_VALUES,
    validate_ground_truth_document,
    validate_legacy_reference_lock,
)
from src.models import Issue, Suggestion, SuggestionSet

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASET_CONTRACTS = {
    "predio": {"items": 4720, "legacy": 1654, "equivalences": 202},
    "casa": {"items": 263, "legacy": 12, "equivalences": 101},
}
BOOLEAN_PROPERTIES = {"LoadBearing", "IsLoadBearing", "HasNonSkidSurface"}
NORMATIVE_CLAIM = re.compile(r"\b(?:ABNT|NBR|IT[- ]?\d+)\b", re.IGNORECASE)


def _load(dataset: str) -> tuple[dict[str, Any], GroundTruth]:
    path = PROJECT_ROOT / "data" / "evaluation" / dataset / "ground_truth.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document, GroundTruth.model_validate(document)


@pytest.mark.parametrize("dataset", DATASET_CONTRACTS)
def test_every_diagnostic_has_a_concrete_frozen_value(dataset: str):
    contract = DATASET_CONTRACTS[dataset]
    document, ground_truth = _load(dataset)
    metadata = ground_truth.metadata

    assert document["skipped"] == []
    assert len(ground_truth.items) == contract["items"]
    assert metadata["protocol"] == "full-coverage-equivalent-v1"
    assert metadata["policy_version"] == "full-coverage-equivalent-v1"
    assert metadata["total_diagnostic_issues"] == contract["items"]
    assert metadata["total_items"] == contract["items"]
    assert metadata["total_skipped"] == 0
    assert metadata["equivalence_class_count"] == contract["equivalences"]
    assert sum(metadata["confidence_counts"].values()) == contract["items"]
    assert sum(bool(item.legacy_reference) for item in ground_truth.items) == contract["legacy"]
    assert all(item.expected_value is not None for item in ground_truth.items)
    assert validate_ground_truth_document(
        PROJECT_ROOT / "data" / "evaluation" / dataset / "ground_truth.yaml"
    ).total_items == contract["items"]
    validate_legacy_reference_lock(document)


@pytest.mark.parametrize("dataset", DATASET_CONTRACTS)
def test_equivalent_diagnostics_share_one_scientific_decision(dataset: str):
    _, ground_truth = _load(dataset)
    decisions: dict[str, set[tuple[str, tuple[str, ...], str, str]]] = defaultdict(set)
    for item in ground_truth.items:
        assert item.equivalence_id is not None
        assert item.confidence is not None
        assert item.source_kind is not None
        decisions[item.equivalence_id].add(
            (
                repr(item.expected_value),
                tuple(repr(value) for value in item.accepted_alternatives),
                item.confidence,
                item.source_kind,
            )
        )
        if item.confidence == "low":
            assert item.notes.startswith("Hipótese congelada:")
        if item.source_kind == "probable":
            assert not NORMATIVE_CLAIM.search(item.notes)

    assert all(len(values) == 1 for values in decisions.values())


@pytest.mark.parametrize("dataset", DATASET_CONTRACTS)
def test_values_stay_inside_the_declared_technical_domains(dataset: str):
    _, ground_truth = _load(dataset)
    systems = WALL_SYSTEM_VALUES | SLAB_SYSTEM_VALUES

    for item in ground_truth.items:
        value = item.expected_value
        if item.check_property in BOOLEAN_PROPERTIES:
            assert type(value) is bool
        elif item.check_property == "ThermalTransmittance":
            assert not isinstance(value, bool)
            assert isinstance(value, (int, float))
            assert 0 < float(value) <= 8
            assert "W/(m²·K)" in item.notes
        elif item.check_property == "SolarHeatGainCoefficient":
            assert not isinstance(value, bool)
            assert isinstance(value, (int, float))
            assert 0 <= float(value) <= 1
        elif item.check_property == "FireRating":
            assert isinstance(value, str)
            assert FIRE_RATING_PATTERN.fullmatch(value)
        elif item.check_property == "AcousticRating":
            assert isinstance(value, str)
            assert ACOUSTIC_RATING_PATTERN.fullmatch(value)
        elif item.check_property == "Category":
            assert value in CATEGORY_VALUES
        elif item.issue_type == "system_unclassified":
            assert value in systems
        elif item.issue_type == "relation_broken":
            assert isinstance(value, str)
            assert IFC_RELATION_PATTERN.fullmatch(value)


def test_all_685_declared_load_bearing_aliases_are_preserved_as_false_high_confidence():
    aliases: list[GroundTruthItem] = []
    for dataset in DATASET_CONTRACTS:
        _, ground_truth = _load(dataset)
        aliases.extend(
            item
            for item in ground_truth.items
            if item.check_property in {"LoadBearing", "IsLoadBearing"}
            and item.source_kind == "ifc_alias"
        )

    assert len(aliases) == 685
    assert all(item.expected_value is False and item.confidence == "high" for item in aliases)


@pytest.mark.parametrize("dataset", DATASET_CONTRACTS)
def test_exact_oracle_scores_one_in_every_nonempty_scientific_slice(dataset: str):
    _, ground_truth = _load(dataset)
    results: list[tuple[Issue, SuggestionSet]] = []
    for item in ground_truth.items:
        issue = Issue(
            id=item.issue_id,
            element_guid=item.element_guid,
            element_class="IfcWall",
            issue_type=item.issue_type,
            severity="medium",
            description="oracle integral",
            context={"check_property": item.check_property},
        )
        suggestion = Suggestion(
            label="oracle",
            value=item.expected_value,
            justification="valor exato do ground truth congelado",
            confidence="alta",
        )
        results.append(
            (
                issue,
                SuggestionSet(issue_id=issue.id, suggestions=[suggestion]),
            )
        )

    metrics = Evaluator().evaluate(results, ground_truth)

    assert metrics.accuracy_all.top1 == 1.0
    assert metrics.accuracy_all.top3 == 1.0
    assert metrics.accuracy_equivalence.top1 == 1.0
    assert metrics.accuracy_equivalence.top3 == 1.0
    assert metrics.accuracy_legacy.top1 == 1.0
    for confidence in ("high", "medium", "low"):
        assert metrics.accuracy_by_confidence[confidence].total > 0
        assert metrics.accuracy_by_confidence[confidence].top1 == 1.0
