"""Integração dos ground truths congelados com os diagnósticos IFC reais."""

from __future__ import annotations

import subprocess
import sys

import pytest
import yaml

from scripts import build_ground_truths as builder
from src.experiment.evaluator import GroundTruth
from src.experiment.ground_truth_validation import (
    load_ground_truth_document,
    validate_ground_truth_against_issues,
)
from src.models import Issue
from src.pipeline import QualityPipeline


def _skip_when_large_ifc_is_missing() -> None:
    missing = [
        f"{key}: {spec.ifc_path}"
        for key, spec in builder.DATASETS.items()
        if not spec.ifc_path.is_file()
    ]
    if missing:
        pytest.skip(f"IFC(s) grande(s) ausente(s): {', '.join(missing)}")


@pytest.mark.integration
@pytest.mark.parametrize("dataset", ["casa", "predio"])
def test_frozen_ground_truth_covers_real_diagnostics(dataset: str) -> None:
    """Cada diagnóstico do IFC instalado recebe um valor no GT integral."""
    _skip_when_large_ifc_is_missing()
    spec = builder.DATASETS[dataset]

    pipeline = QualityPipeline(
        str(spec.ifc_path),
        spec.building_context,
        ids_path=str(builder.IDS_PATH),
    )
    try:
        issues = list(pipeline.diagnose().issues)
    finally:
        pipeline.close()

    report = validate_ground_truth_against_issues(
        spec.ground_truth_path,
        issues,
        ifc_path=spec.ifc_path,
        ids_path=builder.IDS_PATH,
    )
    ground_truth = GroundTruth.from_yaml(spec.ground_truth_path)
    document = load_ground_truth_document(spec.ground_truth_path)

    assert all(item.verified for item in ground_truth.items)
    diagnostic_keys = {
        (
            issue.element_guid,
            issue.issue_type,
            str(issue.context.get("check_property") or ""),
        )
        for issue in issues
    }
    assert report.item_keys.isdisjoint(report.skipped_keys)
    assert report.item_keys | report.skipped_keys == diagnostic_keys
    assert report.skipped_keys == set()
    assert document["skipped"] == []
    assert len(ground_truth.items) == {"casa": 263, "predio": 4720}[dataset]

    if dataset == "casa":
        properties = {item.check_property for item in ground_truth.items}
        assert {"AcousticRating", "SolarHeatGainCoefficient"} <= properties
    else:
        assert document["metadata"]["previous_gt_sha256"] == builder.RATIFIED_LEGACY_SHA256


def test_relation_issue_without_check_property_uses_empty_natural_key() -> None:
    """Relações quebradas reais não têm propriedade-alvo, mas continuam cobertas."""
    issue = Issue(
        element_guid="3bzWotDL93mufPfIaOU_Yx",
        element_class="IfcDoor",
        issue_type="relation_broken",
        severity="medium",
        description="Relação de preenchimento ausente.",
        context={"expected_relation": "IfcRelFillsElement"},
    )

    assert builder._literal_check_property(issue) == ""


@pytest.mark.integration
def test_real_check_rejects_semantically_valid_temporary_drift() -> None:
    """O reuso canônico recusa até uma alteração YAML semanticamente aceitável."""
    _skip_when_large_ifc_is_missing()
    path = builder.DATASETS["predio"].ground_truth_path
    original = path.read_bytes()
    document = yaml.safe_load(original.decode("utf-8"))
    category_item = next(item for item in document["items"] if item["check_property"] == "Category")
    category_item["expected_value"] = (
        "OFFICE" if category_item["expected_value"] != "OFFICE" else "BEDROOM"
    )
    try:
        path.write_text(
            yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        completed = subprocess.run(
            [sys.executable, "scripts/build_ground_truths.py", "--dataset", "predio", "--check"],
            cwd=builder.PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        path.write_bytes(original)

    assert completed.returncode == 1
    assert "hash canonico de predio diverge" in completed.stderr
