"""Contratos estruturais do documento canônico de ground truth."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
import yaml

from src.experiment.evaluator import GroundTruth
from src.experiment.ground_truth_validation import (
    GroundTruthValidationError,
    validate_ground_truth_document,
)


def _valid_document() -> dict[str, Any]:
    """Documento mínimo, completo e independente do validador."""
    return {
        "metadata": {"total_items": 2, "total_skipped": 1},
        "items": [
            {
                "element_guid": "GUID_WALL_01",
                "issue_type": "pset_missing",
                "check_property": "ThermalTransmittance",
                "issue_id": "issue-wall-01",
                "expected_value": 2.5,
                "verified": True,
            },
            {
                "element_guid": "GUID_SPACE_01",
                "issue_type": "pset_missing",
                "check_property": "ThermalTransmittance",
                "issue_id": "issue-space-01",
                "expected_value": "Lavabo",
                "verified": True,
            },
        ],
        "skipped": [
            {
                "element_guid": "GUID_SKIP_01",
                "issue_type": "pset_missing",
                "check_property": "ThermalTransmittance",
                "issue_id": "issue-skip-01",
                "reason": "Fora do escopo",
            }
        ],
    }


def _write_document(tmp_path, document: dict[str, Any]):
    path = tmp_path / "ground_truth.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _assert_invariant(path, invariant: str) -> None:
    with pytest.raises(GroundTruthValidationError) as error:
        validate_ground_truth_document(path)
    assert invariant in str(error.value)


def test_rejects_unverified_item(tmp_path):
    """Impede que uma correção não confirmada entre no ground truth canônico."""
    document = _valid_document()
    document["items"][0]["verified"] = False

    _assert_invariant(_write_document(tmp_path, document), "unverified_item")


def test_rejects_null_expected_value(tmp_path):
    """Impede que uma correção canônica não tenha valor esperado."""
    document = _valid_document()
    document["items"][0]["expected_value"] = None

    _assert_invariant(_write_document(tmp_path, document), "null_expected_value")


def test_rejects_empty_check_property_for_pset_missing(tmp_path):
    """Impede pset_missing sem a propriedade que deve ser preenchida."""
    document = _valid_document()
    document["items"][0]["check_property"] = ""

    _assert_invariant(_write_document(tmp_path, document), "pset_missing_requires_check_property")


def test_rejects_duplicate_natural_key(tmp_path):
    """Impede duas correções para a mesma chave natural."""
    document = _valid_document()
    document["items"][1]["element_guid"] = "GUID_WALL_01"

    _assert_invariant(_write_document(tmp_path, document), "duplicate_natural_key")


def test_rejects_duplicate_issue_id(tmp_path):
    """Impede que o fallback por issue_id fique ambíguo."""
    document = _valid_document()
    document["items"][1]["issue_id"] = "issue-wall-01"

    _assert_invariant(_write_document(tmp_path, document), "duplicate_issue_id")


def test_rejects_item_and_skip_overlap(tmp_path):
    """Impede que a mesma issue seja avaliada e ignorada simultaneamente."""
    document = _valid_document()
    document["skipped"][0]["element_guid"] = "GUID_WALL_01"

    _assert_invariant(_write_document(tmp_path, document), "item_and_skip_overlap")


def test_rejects_declared_count_mismatch(tmp_path):
    """Impede metadados de contagem divergentes do conteúdo real."""
    document = _valid_document()
    document["metadata"]["total_items"] = 3

    _assert_invariant(_write_document(tmp_path, document), "declared_count_mismatch")


def test_accepts_valid_document(tmp_path):
    """Aceita documento íntegro e mantém skips fora do loader de avaliação."""
    path = _write_document(tmp_path, deepcopy(_valid_document()))

    report = validate_ground_truth_document(path)
    ground_truth = GroundTruth.from_yaml(path)

    assert report.total_items == 2
    assert report.total_skipped == 1
    assert report.item_keys == {
        ("GUID_WALL_01", "pset_missing", "ThermalTransmittance"),
        ("GUID_SPACE_01", "pset_missing", "ThermalTransmittance"),
    }
    assert report.skipped_keys == {("GUID_SKIP_01", "pset_missing", "ThermalTransmittance")}
    assert len(ground_truth.items) == 2
    assert {item.issue_id for item in ground_truth.items} == {"issue-wall-01", "issue-space-01"}
