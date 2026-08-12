"""Smoke do runner contra os ground truths congelados, sem chamar Ollama."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from src.experiment.runner import ExperimentRunner
from src.models import SuggestionMetrics, SuggestionSet

ROOT = Path(__file__).resolve().parents[2]
IDS_PATH = ROOT / "data" / "ids_templates" / "residencial_nbr15575.ids"
SMOKE_HARDWARE = {"source": "ground-truth-runner-smoke"}


def _deterministic_batch(issues, _context, on_progress=None, **_kwargs):
    """Double local: exercita o runner sem transporte nem modelo Ollama."""
    if on_progress is not None:
        on_progress(len(issues), len(issues))
    return [
        SuggestionSet(
            issue_id=issue.id,
            metrics=SuggestionMetrics(
                issue_id=issue.id,
                attempts=0,
                final_status="ready",
            ),
        )
        for issue in issues
    ]


@pytest.mark.integration
@pytest.mark.parametrize(
    (
        "dataset",
        "relative_ifc",
        "relative_ground_truth",
        "building_context",
        "expected_items",
        "expected_equivalences",
        "expected_confidence",
    ),
    [
        (
            "predio",
            Path("data/evaluation/predio/predio_v1.ifc"),
            Path("data/evaluation/predio/ground_truth.yaml"),
            {"building_type": "Residencial multifamiliar", "bioclimatic_zone": "4A"},
            4720,
            202,
            {"high": 2307, "medium": 1365, "low": 1048},
        ),
        (
            "casa",
            Path("data/evaluation/casa/casa_v1.ifc"),
            Path("data/evaluation/casa/ground_truth.yaml"),
            {"building_type": "Residencial unifamiliar", "bioclimatic_zone": "4A"},
            263,
            101,
            {"high": 52, "medium": 132, "low": 79},
        ),
    ],
)
def test_runner_smoke_loads_frozen_ground_truth_without_mutating_ifc(
    dataset: str,
    relative_ifc: Path,
    relative_ground_truth: Path,
    building_context: dict[str, str],
    expected_items: int,
    expected_equivalences: int,
    expected_confidence: dict[str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quebra se o runner deixar de respeitar o GT, a cópia ou o reuso pedido."""
    ifc_path = ROOT / relative_ifc
    if not ifc_path.is_file():
        pytest.skip(f"IFC grande ausente para {dataset}: {ifc_path}")
    ground_truth_path = ROOT / relative_ground_truth

    # Estas sondas são telemetria best-effort do runner, não parte do smoke.
    # Neutralizá-las garante que o teste jamais consulta um servidor Ollama real.
    import src.experiment.runner as runner_module

    monkeypatch.setattr(runner_module, "gpu_residency", lambda *_args: None)
    monkeypatch.setattr(runner_module, "ollama_model_digest", lambda *_args: None)
    monkeypatch.setattr(runner_module, "_ollama_version", lambda *_: None)
    monkeypatch.setattr(runner_module, "hardware_snapshot", lambda: SMOKE_HARDWARE)

    before = hashlib.sha256(ifc_path.read_bytes()).hexdigest()
    result = ExperimentRunner(suggestion_batch_fn=_deterministic_batch).run_single(
        ifc_path=str(ifc_path),
        ground_truth_path=str(ground_truth_path),
        building_context=building_context,
        ids_path=str(IDS_PATH),
        model_name="smoke-double",
        cache_enabled=False,
        max_issues=1,
        reuse_equivalent=True,
    )

    assert result.issue_counts["total_issues"] == 1
    assert result.metadata.ground_truth_sha256 == hashlib.sha256(
        ground_truth_path.read_bytes()
    ).hexdigest()
    assert result.metadata.reuse_equivalent is True
    assert result.metadata.ground_truth_policy_version == "full-coverage-equivalent-v1"
    assert result.metadata.ground_truth_items == expected_items
    assert result.metadata.ground_truth_equivalence_classes == expected_equivalences
    assert result.metadata.ground_truth_confidence_counts == expected_confidence
    assert result.evaluation.accuracy_all.total == 1
    assert result.evaluation.accuracy_equivalence.total == 1
    assert result.metadata.hardware == SMOKE_HARDWARE
    assert hashlib.sha256(ifc_path.read_bytes()).hexdigest() == before
