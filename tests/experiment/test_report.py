"""Testes do gerador de relatório do benchmark (Fase B.4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.experiment.report import (
    aggregate,
    generate_report,
    load_results,
    to_latex,
    to_markdown,
)


def _run_json(
    model: str,
    replica: int,
    top1: float,
    latency: float,
    *,
    equivalence_top1: float | None = None,
) -> dict:
    """ExperimentResult mínimo com os campos que o report consome."""
    return {
        "metadata": {"model_name": model, "replica_index": replica},
        "evaluation": {
            "accuracy_top1": top1,
            "accuracy_top3": min(top1 + 0.1, 1.0),
            "precision": top1,
            "total_evaluated": 20,
            **(
                {
                    "accuracy_all": {"top1": top1, "top3": min(top1 + 0.1, 1.0), "total": 20},
                    "accuracy_equivalence": {
                        "top1": equivalence_top1,
                        "top3": min(equivalence_top1 + 0.1, 1.0),
                        "total": 4,
                    },
                    "accuracy_by_confidence": {
                        "high": {"top1": top1, "top3": top1, "total": 10},
                        "medium": {"top1": top1, "top3": top1, "total": 5},
                        "low": {"top1": top1, "top3": top1, "total": 5},
                    },
                    "accuracy_legacy": {"top1": top1, "top3": top1, "total": 3},
                }
                if equivalence_top1 is not None
                else {}
            ),
        },
        "review_proxy": {
            "ids_conformity_rate": 0.9,
            "acceptance_rate": top1,
            "review_rate": 0.5,
        },
        "stability": {
            "json_valid_first_try_rate": 0.8,
            "avg_attempts": 1.2,
            "failure_rate": 0.05,
        },
        "timing": {
            "latency_ms_p50": latency,
            "latency_ms_p95": latency * 2,
            "output_tokens_per_sample": 500.0,
        },
    }


@pytest.fixture
def results_dir(tmp_path: Path) -> Path:
    """Diretório de resultados sintético: 2 modelos × 2 réplicas."""
    for model, safe, top1, latency in [
        ("qwen2.5:7b-instruct", "qwen2.5_7b-instruct", 0.40, 15000.0),
        ("mistral:7b", "mistral_7b", 0.30, 9000.0),
    ]:
        model_dir = tmp_path / safe
        model_dir.mkdir()
        for replica in (0, 1):
            payload = _run_json(model, replica, top1 + 0.02 * replica, latency)
            (model_dir / f"run_{replica}.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
    return tmp_path


class TestLoadAndAggregate:
    def test_load_results_one_row_per_replica(self, results_dir: Path):
        df = load_results(results_dir)

        assert len(df) == 4
        assert set(df["model"]) == {"qwen2.5:7b-instruct", "mistral:7b"}

    def test_load_results_empty_dir_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_results(tmp_path)

    def test_aggregate_means_and_ordering(self, results_dir: Path):
        agg = aggregate(load_results(results_dir))

        assert list(agg["model"]) == ["qwen2.5:7b-instruct", "mistral:7b"]  # top-1 desc
        qwen = agg.iloc[0]
        assert qwen["accuracy_top1_mean"] == pytest.approx(0.41)
        assert qwen["replicas"] == 2

    def test_ranking_prefers_equivalence_and_marks_legacy_fallback(self, tmp_path: Path):
        for model, occurrence, equivalence in [
            ("repeated-winner", 0.95, 0.20),
            ("class-winner", 0.60, 0.80),
        ]:
            directory = tmp_path / model
            directory.mkdir()
            payload = _run_json(
                model,
                0,
                occurrence,
                1000.0,
                equivalence_top1=equivalence,
            )
            (directory / "run_0.json").write_text(json.dumps(payload), encoding="utf-8")

        ranked = aggregate(load_results(tmp_path))

        assert list(ranked["model"]) == ["class-winner", "repeated-winner"]
        assert set(ranked["metric_basis"]) == {"equivalence"}

        legacy_dir = tmp_path / "legacy"
        legacy_dir.mkdir()
        legacy = _run_json("legacy", 0, 0.70, 1000.0)
        (legacy_dir / "run_0.json").write_text(json.dumps(legacy), encoding="utf-8")
        loaded = load_results(legacy_dir.parent)
        legacy_row = loaded.loc[loaded["model"] == "legacy"].iloc[0]
        assert legacy_row["accuracy_equivalence_top1"] == pytest.approx(0.70)
        assert legacy_row["metric_basis"] == "legacy_occurrence"


class TestTables:
    def test_markdown_table_has_models_and_percentages(self, results_dir: Path):
        md = to_markdown(aggregate(load_results(results_dir)))

        assert "qwen2.5:7b-instruct" in md
        assert "41.0%" in md
        assert md.count("\n") >= 3  # header + separador + 2 modelos

    def test_latex_table_escapes_and_wraps(self, results_dir: Path):
        tex = to_latex(aggregate(load_results(results_dir)))

        assert tex.startswith("\\begin{tabular}")
        assert "\\toprule" in tex
        assert "41.0\\%" in tex


class TestGenerateReport:
    def test_generates_all_artifacts(self, results_dir: Path, tmp_path: Path):
        out = tmp_path / "report"

        paths = generate_report(results_dir, out)

        for key in ("raw_csv", "table_md", "table_tex", "fig_topk", "fig_quality_latency"):
            assert paths[key].is_file(), key
        html = paths["fig_topk"].read_text(encoding="utf-8")
        assert "plotly" in html.casefold()
