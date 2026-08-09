"""Testes do harness experimental (Fase 0.5 / F2+F6+F7+F12) com Ollama mockado."""

from __future__ import annotations

import json

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.owner.settings
import ifcopenshell.guid
import pytest

from src.experiment.execution_identity import DatasetIdentity, ExecutionIdentity
from src.experiment.metrics import RunMetadata, aggregate_stability, aggregate_timing
from src.experiment.runner import (
    ExperimentRunner,
    filter_issues_by_type,
    sha256_of,
    stratified_sample,
)
from src.models import Issue, Suggestion, SuggestionMetrics, SuggestionSet

_BUILDING_CTX = {
    "building_type": "Residencial multifamiliar",
    "bioclimatic_zone": "4A",
}
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
  protocol: full-coverage-equivalent-v1
  total_items: 1
  equivalence_class_count: 1
  confidence_counts: {{high: 1, medium: 0, low: 0}}
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
# Filtro de issue_types (--issue-types) — dataset mascarado só gera nomeação
# ---------------------------------------------------------------------------


class TestFilterIssuesByType:
    def test_dedups_ids_duplicate_of_same_element(self):
        """Issue do IDS para o mesmo (guid, tipo) é descartada; a base (primeira,
        com chave natural que casa o GT) é mantida."""
        guid = "S" * 22
        base = Issue(
            element_guid=guid,
            element_class="IfcSpace",
            issue_type="space_unnamed",
            severity="low",
            description="base diagnostics",
            context={},
        )
        from_ids = Issue(
            element_guid=guid,
            element_class="IfcSpace",
            issue_type="space_unnamed",
            severity="low",
            description="gerada pelo IDS",
            context={"check_pset": "Attributes", "check_property": "Name"},
        )
        other = Issue(
            element_guid="X" * 22,
            element_class="IfcWall",
            issue_type="pset_missing",
            severity="medium",
            description="fora do filtro",
            context={"check_property": "FireRating"},
        )

        result = filter_issues_by_type([base, from_ids, other], ["space_unnamed"])

        assert result == [base]

    def test_keeps_distinct_elements_of_same_type(self):
        issues = [
            Issue(
                element_guid=f"{i:022d}",
                element_class="IfcSpace",
                issue_type="space_unnamed",
                severity="low",
                description=f"espaço {i}",
                context={},
            )
            for i in range(3)
        ]

        assert len(filter_issues_by_type(issues, ["space_unnamed"])) == 3


class TestIssueTypesFilter:
    def test_run_single_restricts_generation_to_requested_types(
        self, ifc_with_space, ground_truth_yaml
    ):
        """Com issue_types=['space_unnamed'], nenhuma issue de outro tipo é gerada."""
        ifc_path, _ = ifc_with_space
        runner = ExperimentRunner(suggestion_batch_fn=_mock_batch_correct)

        result = runner.run_single(
            ifc_path=ifc_path,
            ground_truth_path=ground_truth_yaml,
            building_context=_BUILDING_CTX,
            model_name="mock-model:test",
            cache_enabled=False,
            issue_types=["space_unnamed"],
        )

        assert set(result.decisions["issues_by_type"]) == {"space_unnamed"}
        assert result.issue_counts["issue_types_filter"] == ["space_unnamed"]
        assert result.issue_counts["total_issues"] < result.issue_counts["sampled_from"]

    def test_filter_composes_with_sampling(self, ifc_with_space, ground_truth_yaml):
        """Filtro e amostragem convivem: primeiro filtra o tipo, depois amostra."""
        ifc_path, _ = ifc_with_space
        runner = ExperimentRunner(suggestion_batch_fn=_mock_batch_correct)

        result = runner.run_single(
            ifc_path=ifc_path,
            ground_truth_path=ground_truth_yaml,
            building_context=_BUILDING_CTX,
            model_name="mock-model:test",
            cache_enabled=False,
            issue_types=["space_unnamed"],
            max_issues=1,
        )

        assert result.issue_counts["total_issues"] == 1
        assert set(result.decisions["issues_by_type"]) == {"space_unnamed"}


# ---------------------------------------------------------------------------
# Telemetria de falha de transporte (F12) — HTTP 500 / timeout contam tentativa
# ---------------------------------------------------------------------------


class TestTransportFailureTelemetry:
    def test_http_error_counts_as_attempt_and_failure(self):
        """Falha de transporte (ex.: Ollama HTTP 500) deve aparecer na
        estabilidade: attempts=1, final_status=failed — nunca invisível."""
        from unittest.mock import MagicMock

        from src.models import Issue
        from src.suggestion_engine.ollama_client import OllamaClient
        from src.suggestion_engine.suggestion import SuggestionGenerator

        client = MagicMock(spec=OllamaClient)
        client.generate.side_effect = RuntimeError(
            "Ollama HTTP error: Server error '500 Internal Server Error'"
        )
        gen = SuggestionGenerator(client)
        issue = Issue(
            element_guid="W" * 22,
            element_class="IfcWall",
            issue_type="pset_missing",
            severity="medium",
            description="Reference ausente",
            context={"check_pset": "Pset_WallCommon", "check_property": "Reference"},
        )

        result = gen.generate(issue, _BUILDING_CTX)

        assert result.metrics is not None
        assert result.metrics.attempts == 1
        assert result.metrics.final_status == "failed"
        assert result.metrics.failure_reason == "other"

        stability = aggregate_stability([result.metrics])
        assert stability.total_generated == 1
        assert stability.failed_count == 1
        assert stability.failure_rate == 1.0


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
        assert result.metadata.building_context == {
            "building_type": "Residencial multifamiliar",
            "bioclimatic_zone": "4A",
        }

    def test_metadados_antigos_carregam_com_novos_campos_vazios(self):
        metadata = RunMetadata.model_validate({"model_name": "mock-model:test"})

        assert metadata.building_context == {}
        assert metadata.dataset_key == ""
        assert metadata.execution_identity == {}
        assert metadata.execution_identity_sha256 == ""

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
        execution_identity = ExecutionIdentity(
            release_id="ifcqc-r1",
            project_sha256="1" * 64,
            models_lock_sha256="2" * 64,
            datasets=(
                DatasetIdentity(
                    key="predio",
                    ifc_sha256="3" * 64,
                    ground_truth_sha256="4" * 64,
                    ids_sha256="5" * 64,
                    building_context=tuple(sorted(_BUILDING_CTX.items())),
                    ground_truth_policy_version="full-coverage-equivalent-v1",
                    ground_truth_items=1,
                    equivalence_classes=1,
                    confidence_counts=(("high", 1), ("medium", 0), ("low", 0)),
                ),
                DatasetIdentity(
                    key="casa",
                    ifc_sha256="6" * 64,
                    ground_truth_sha256="7" * 64,
                    ids_sha256="5" * 64,
                    building_context=(
                        ("bioclimatic_zone", "4A"),
                        ("building_type", "Residencial unifamiliar"),
                    ),
                    ground_truth_policy_version="full-coverage-equivalent-v1",
                    ground_truth_items=1,
                    equivalence_classes=1,
                    confidence_counts=(("high", 1), ("medium", 0), ("low", 0)),
                ),
            ),
            replica_count=2,
            cache_enabled=False,
            prompt_version="v7.2",
            prompt_sha256="8" * 64,
            reuse_equivalent=True,
        )

        results = runner.run(
            ifc_path=ifc_path,
            ground_truth_path=ground_truth_yaml,
            building_context=_BUILDING_CTX,
            model_name="mock-model:test",
            n_replicas=2,
            output_dir=str(out_dir),
            dataset_key="predio",
            execution_identity=execution_identity,
            reuse_equivalent=True,
        )

        assert len(results) == 2
        exported = list(out_dir.rglob("run_*.json"))
        assert len(exported) == 2
        assert {result.metadata.dataset_key for result in results} == {"predio"}
        assert all(result.metadata.execution_identity for result in results)
        assert all(result.metadata.execution_identity_sha256 for result in results)
        assert all(result.metadata.reuse_equivalent is True for result in results)
        assert all(
            result.metadata.ground_truth_policy_version
            == "full-coverage-equivalent-v1"
            for result in results
        )
        assert all(result.metadata.ground_truth_items == 1 for result in results)
        assert all(
            result.metadata.ground_truth_equivalence_classes == 1 for result in results
        )
        assert all(
            result.metadata.ground_truth_confidence_counts
            == {"high": 1, "medium": 0, "low": 0}
            for result in results
        )
        for path in exported:
            metadata = json.loads(path.read_text(encoding="utf-8"))["metadata"]
            assert metadata["dataset_key"] == "predio"
            assert metadata["execution_identity"]["release_id"] == "ifcqc-r1"
            assert metadata["execution_identity"]["reuse_equivalent"] is True
            assert metadata["reuse_equivalent"] is True
            assert metadata["execution_identity_sha256"]


# ---------------------------------------------------------------------------
# Agregadores de estabilidade/eficiência (F12)
# ---------------------------------------------------------------------------


class TestAgregadores:
    def test_stability_conta_primeira_tentativa_e_reparo(self):
        metrics = [
            SuggestionMetrics(issue_id="a", attempts=1, final_status="ready"),
            SuggestionMetrics(issue_id="b", attempts=2, final_status="ready", json_repaired=True),
            SuggestionMetrics(
                issue_id="c",
                attempts=3,
                final_status="failed",
                failure_reason="json_invalid",
            ),
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


class TestFilterIssuesByProperty:
    """Recorte por propriedade alvo — medir UM estrato sem pagar pelos outros.

    O recorte por issue_type ainda é caro quando um tipo concentra muitos
    estímulos: `pset_missing` no prédio custa 54 min porque `Category` sozinho
    tem 77 estímulos distintos. Para atribuir o efeito de uma correção que mira
    FireRating e ThermalTransmittance, 24 estímulos bastam (~10 min).
    """

    def _issue(self, check_property: str, guid: str = "W" * 22) -> Issue:
        return Issue(
            element_guid=guid,
            element_class="IfcWall",
            issue_type="pset_missing",
            severity="high",
            description=f"{check_property} ausente",
            context={"check_property": check_property},
        )

    def test_keeps_only_requested_properties(self):
        from src.experiment.runner import filter_issues_by_property

        fogo = self._issue("FireRating", "A" * 22)
        termico = self._issue("ThermalTransmittance", "B" * 22)
        categoria = self._issue("Category", "C" * 22)

        result = filter_issues_by_property(
            [fogo, termico, categoria], ["FireRating", "ThermalTransmittance"]
        )

        assert result == [fogo, termico]

    def test_matches_property_names_case_and_separator_insensitively(self):
        """Mesma regra de casamento do resto do sistema (nome humano × PascalCase)."""
        from src.experiment.runner import filter_issues_by_property

        termico = self._issue("ThermalTransmittance")

        assert filter_issues_by_property([termico], ["thermal transmittance"]) == [termico]

    def test_empty_property_list_is_a_no_op(self):
        """Sem propriedades pedidas, o recorte não filtra nada."""
        from src.experiment.runner import filter_issues_by_property

        issues = [self._issue("FireRating"), self._issue("Category", "C" * 22)]

        assert filter_issues_by_property(issues, []) == issues

    def test_drops_issues_without_target_property(self):
        """Issue sem check_property (ex.: space_unnamed) sai quando há filtro."""
        from src.experiment.runner import filter_issues_by_property

        sem_propriedade = Issue(
            element_guid="S" * 22,
            element_class="IfcSpace",
            issue_type="space_unnamed",
            severity="low",
            description="sem nome",
            context={},
        )

        assert filter_issues_by_property([sem_propriedade], ["FireRating"]) == []
