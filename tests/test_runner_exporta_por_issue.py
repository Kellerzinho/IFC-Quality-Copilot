"""O runner grava o JSONL por issue ao lado do run_N.json.

Sem esse gancho o export por issue existe mas nada o produz — foi exatamente o
que aconteceu no benchmark de 2026-07-27, cujos 20 estágios só deixaram
agregados e impossibilitaram qualquer breakdown depois do run.
"""

from __future__ import annotations

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.owner.settings
import ifcopenshell.guid
import pytest

from src.experiment.per_issue import read_outcomes_jsonl
from src.experiment.runner import ExperimentRunner
from src.models import Suggestion, SuggestionMetrics, SuggestionSet

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
    space = f.create_entity("IfcSpace", GlobalId=space_guid, Name="Room 1", LongName="Room 1")
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


def test_export_grava_jsonl_por_issue_ao_lado_do_run_json(
    tmp_path, ifc_with_space, ground_truth_yaml
):
    """Cada réplica exportada deixa run_N.json e run_N_issues.jsonl."""
    ifc_path, space_guid = ifc_with_space
    runner = ExperimentRunner(suggestion_batch_fn=_mock_batch_correct)

    result = runner.run_single(
        ifc_path=ifc_path,
        ground_truth_path=ground_truth_yaml,
        building_context=_BUILDING_CTX,
        model_name="mock-model",
    )
    out_dir = tmp_path / "resultados"
    ExperimentRunner._export(result, str(out_dir))

    jsonl = out_dir / "mock-model" / "run_0_issues.jsonl"
    assert jsonl.is_file(), "JSONL por issue não foi gravado ao lado do run_0.json"

    outcomes = read_outcomes_jsonl(jsonl)
    assert len(outcomes) == result.evaluation.total_evaluated
    assert outcomes[0].element_guid == space_guid
    assert outcomes[0].stratum == "space_unnamed"
    assert outcomes[0].match_top1 is True


def test_soma_dos_acertos_por_issue_bate_com_o_agregado(
    tmp_path, ifc_with_space, ground_truth_yaml
):
    """O breakdown e o agregado não podem divergir: mesma comparação normalizada."""
    ifc_path, _ = ifc_with_space
    runner = ExperimentRunner(suggestion_batch_fn=_mock_batch_correct)

    result = runner.run_single(
        ifc_path=ifc_path,
        ground_truth_path=ground_truth_yaml,
        building_context=_BUILDING_CTX,
        model_name="mock-model",
    )
    out_dir = tmp_path / "resultados"
    ExperimentRunner._export(result, str(out_dir))
    outcomes = read_outcomes_jsonl(out_dir / "mock-model" / "run_0_issues.jsonl")

    acertos = sum(o.match_top1 for o in outcomes)
    esperado = round(result.evaluation.accuracy_top1 * result.evaluation.total_evaluated)
    assert acertos == esperado
