"""Testes do harness experimental (Fase 0.5 / F2+F6+F7+F12) com Ollama mockado."""

from __future__ import annotations

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.owner.settings
import ifcopenshell.guid
import pytest

from src.experiment.metrics import aggregate_stability, aggregate_timing
from src.experiment.runner import ExperimentRunner, sha256_of, stratified_sample
from src.models import Issue, Suggestion, SuggestionMetrics, SuggestionSet

_BUILDING_CTX = {"building_type": "Residencial unifamiliar", "bioclimatic_zone": "3"}
_SPACE_NAME = "Sala de Estar"


@pytest.fixture
def ifc_with_space(tmp_path) -> tuple[str, str]:
    """IFC2X3 mínimo com 1 IfcSpace genérico. Retorna (caminho, guid_do_espaco)."""
    f = ifcopenshell.api.run("project.create_file", version="IFC2X3")
    person = ifcopenshell.api.run("owner.add_person", f, identification="eng", family_name="Eng")
    org = ifcopenshell.api.run("owner.add_organisation", f, identification="IFC", name="IFC Test")
    user = ifcopenshell.api.run(
        "owner.add_person_and_organisation", f, person=person, organisation=org
    )
    app = ifcopenshell.api.run("owner.add_application", f)
    ifcopenshell.api.owner.settings.get_user = lambda ifc: user
    ifcopenshell.api.owner.settings.get_application = lambda ifc: app

    ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="Teste")
    ifcopenshell.api.run("unit.assign_unit", f)
    storey = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="P1")

    space_guid = ifcopenshell.guid.new()
    space = f.create_entity(
        "IfcSpace", GlobalId=space_guid, Name="Room 1", LongName="Room 1"
    )
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[space],
    )
    qto = ifcopenshell.api.run("pset.add_qto", f, product=space, name="Qto_SpaceBaseQuantities")
    ifcopenshell.api.run("pset.edit_qto", f, qto=qto, properties={"NetFloorArea": 10.0})

    path = str(tmp_path / "predio_v1.ifc")
    f.write(path)
    return path, space_guid


@pytest.fixture
def ground_truth_yaml(tmp_path, ifc_with_space) -> str:
    """ground_truth.yaml casando o espaço pela chave natural."""
    _, space_guid = ifc_with_space
    text = f"""
metadata:
  source: teste
  verified_by: pytest
items:
  - element_guid: "{space_guid}"
    issue_type: space_unnamed
    expected_value: "{_SPACE_NAME}"
    verified: true
"""
    path = str(tmp_path / "ground_truth.yaml")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def _mock_batch_correct(issues, ctx, on_progress=None):
    """Mock do LLM: devolve a sugestão correta (== GT) com telemetria de 1 tentativa."""
    out = []
    for i in issues:
        value = _SPACE_NAME if i.issue_type == "space_unnamed" else "X"
        out.append(
            SuggestionSet(
                issue_id=i.id,
                suggestions=[
                    Suggestion(
                        label=value,
                        value=value,
                        justification="10m²",
                        confidence="alta",
                        source="llm",
                    )
                ],
                metrics=SuggestionMetrics(
                    issue_id=i.id,
                    attempts=1,
                    final_status="ready",
                    llm_total_ms=42.0,
                    output_tokens=12,
                ),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Amostragem estratificada (--max-issues)
# ---------------------------------------------------------------------------


def _make_issues(counts: dict[str, int]) -> list[Issue]:
    """Gera issues sintéticas com GUIDs distintos por tipo."""
    issues: list[Issue] = []
    for issue_type, n in counts.items():
        for i in range(n):
            issues.append(
                Issue(
                    element_guid=f"{issue_type[:1].upper()}{i:021d}",
                    element_class="IfcWall",
                    issue_type=issue_type,  # type: ignore[arg-type]
                    severity="medium",
                    description=f"{issue_type} {i}",
                    context={"check_property": "P"},
                )
            )
    return issues


class TestStratifiedSample:
    def test_sample_respects_max_and_covers_all_types(self):
        issues = _make_issues(
            {"pset_missing": 80, "system_unclassified": 15, "space_unnamed": 5}
        )
        sampled = stratified_sample(issues, 20, seed=42)

        assert len(sampled) == 20
        types = {i.issue_type for i in sampled}
        assert types == {"pset_missing", "system_unclassified", "space_unnamed"}

    def test_sample_is_deterministic_for_same_seed(self):
        issues = _make_issues({"pset_missing": 50, "system_unclassified": 50})
        a = [i.id for i in stratified_sample(issues, 10, seed=42)]
        b = [i.id for i in stratified_sample(issues, 10, seed=42)]
        c = [i.id for i in stratified_sample(issues, 10, seed=7)]

        assert a == b
        assert a != c

    def test_sample_preserves_diagnose_order(self):
        issues = _make_issues({"pset_missing": 30, "system_unclassified": 30})
        sampled = stratified_sample(issues, 12, seed=42)
        original_index = {issue.id: idx for idx, issue in enumerate(issues)}
        indices = [original_index[i.id] for i in sampled]

        assert indices == sorted(indices)

    def test_no_sampling_when_under_limit(self):
        issues = _make_issues({"pset_missing": 5})
        assert stratified_sample(issues, 10, seed=42) == issues

    def test_proportional_allocation(self):
        """Estrato 9x maior recebe ~9x mais amostras."""
        issues = _make_issues({"pset_missing": 90, "space_unnamed": 10})
        sampled = stratified_sample(issues, 20, seed=42)
        from collections import Counter

        counts = Counter(i.issue_type for i in sampled)
        assert counts["pset_missing"] == 18
        assert counts["space_unnamed"] == 2


# ---------------------------------------------------------------------------
# Harness end-to-end com Ollama mockado
# ---------------------------------------------------------------------------


class TestHarnessEndToEnd:
    def test_run_single_gera_todas_as_metricas(self, ifc_with_space, ground_truth_yaml):
        ifc_path, _ = ifc_with_space
        runner = ExperimentRunner(suggestion_batch_fn=_mock_batch_correct)

        result = runner.run_single(
            ifc_path=ifc_path,
            ground_truth_path=ground_truth_yaml,
            building_context=_BUILDING_CTX,
            model_name="mock-model:test",
            cache_enabled=False,
            replica_index=0,
        )

        # Avaliação
        assert result.evaluation.total_evaluated >= 1
        assert result.evaluation.accuracy_top1 == pytest.approx(1.0)
        # Revisor simulado (proxy) — sugestão correta → accepted
        assert result.review_proxy.simulation is True
        assert result.review_proxy.accepted >= 1
        # Estabilidade (F12)
        assert result.stability.total_generated >= 1
        assert result.stability.json_valid_first_try_rate == pytest.approx(1.0)
        # Metadados (F7)
        assert result.metadata.model_name == "mock-model:test"
        assert result.metadata.prompt_version
        assert result.metadata.ifc_sha256
        assert result.metadata.cache_enabled is False

    def test_ifc_original_nao_e_alterado(self, ifc_with_space, ground_truth_yaml):
        """O hash do IFC original deve ser idêntico antes e depois do run (revisor em cópia)."""
        ifc_path, _ = ifc_with_space
        before = sha256_of(ifc_path)

        runner = ExperimentRunner(suggestion_batch_fn=_mock_batch_correct)
        result = runner.run_single(
            ifc_path=ifc_path,
            ground_truth_path=ground_truth_yaml,
            building_context=_BUILDING_CTX,
        )
        # O revisor simulado aplicou correções (accepted) numa cópia descartável.
        assert result.review_proxy.accepted >= 1

        after = sha256_of(ifc_path)
        assert before == after, "O IFC original foi alterado pelo harness!"

    def test_run_exporta_json_por_replica(self, ifc_with_space, ground_truth_yaml, tmp_path):
        ifc_path, _ = ifc_with_space
        out_dir = tmp_path / "results"
        runner = ExperimentRunner(suggestion_batch_fn=_mock_batch_correct)

        results = runner.run(
            ifc_path=ifc_path,
            ground_truth_path=ground_truth_yaml,
            building_context=_BUILDING_CTX,
            model_name="mock-model:test",
            n_replicas=2,
            output_dir=str(out_dir),
        )

        assert len(results) == 2
        exported = list(out_dir.rglob("run_*.json"))
        assert len(exported) == 2


# ---------------------------------------------------------------------------
# Agregadores de estabilidade/eficiência (F12)
# ---------------------------------------------------------------------------


class TestAgregadores:
    def test_stability_conta_primeira_tentativa_e_reparo(self):
        metrics = [
            SuggestionMetrics(issue_id="a", attempts=1, final_status="ready"),
            SuggestionMetrics(issue_id="b", attempts=2, final_status="ready", json_repaired=True),
            SuggestionMetrics(issue_id="c", attempts=3, final_status="failed", failure_reason="json_invalid"),
            # cache hit não conta (attempts=0)
            SuggestionMetrics(issue_id="d", attempts=0, cache_hit=True, final_status="cached"),
        ]
        stab = aggregate_stability(metrics)
        assert stab.total_generated == 3
        assert stab.json_valid_first_try == 1
        assert stab.json_valid_first_try_rate == pytest.approx(1 / 3)
        assert stab.json_repaired_count == 1
        assert stab.failed_count == 1
        assert stab.failure_reasons == {"json_invalid": 1}

    def test_timing_percentis_e_tokens(self):
        metrics = [
            SuggestionMetrics(issue_id="a", attempts=1, llm_total_ms=10.0, output_tokens=5),
            SuggestionMetrics(issue_id="b", attempts=1, llm_total_ms=30.0, output_tokens=15),
        ]
        timing = aggregate_timing(metrics)
        assert timing.samples == 2
        assert timing.latency_ms_p50 == pytest.approx(20.0)
        assert timing.output_tokens_total == 20
        assert timing.output_tokens_per_sample == pytest.approx(10.0)
