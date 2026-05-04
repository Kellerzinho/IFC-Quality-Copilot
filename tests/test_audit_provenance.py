"""Testes de proveniência no AuditEntry e exportações de auditoria."""

import csv
import json
from pathlib import Path
from unittest.mock import patch

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.owner.settings
import ifcopenshell.guid
import pytest

from src.audit.logger import AuditLogger
from src.models import AuditEntry, BSDDContext, IDSContext, Suggestion, SuggestionSet, ValidationResult
from src.pipeline import QualityPipeline


_BUILDING_CTX = {
    "building_type": "Residencial unifamiliar",
    "bioclimatic_zone": "3",
    "city": "Sao Paulo",
    "state": "SP",
}


@pytest.fixture
def ifc_file_path(tmp_path) -> str:
    """IFC2X3 mínimo com um IfcSpace genérico salvo em disco."""
    f = ifcopenshell.api.run("project.create_file", version="IFC2X3")

    person = ifcopenshell.api.run("owner.add_person", f, identification="eng", family_name="Engineer")
    org = ifcopenshell.api.run("owner.add_organisation", f, identification="IFC", name="IFC Test")
    user = ifcopenshell.api.run("owner.add_person_and_organisation", f, person=person, organisation=org)
    app = ifcopenshell.api.run("owner.add_application", f)
    ifcopenshell.api.owner.settings.get_user = lambda ifc: user
    ifcopenshell.api.owner.settings.get_application = lambda ifc: app

    project = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="Teste")
    ifcopenshell.api.run("unit.assign_unit", f)
    site = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSite", name="Terreno")
    building = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuilding", name="Edificio")
    storey = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Pav 1")
    ifcopenshell.api.run("aggregate.assign_object", f, relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", f, relating_object=site, products=[building])
    ifcopenshell.api.run("aggregate.assign_object", f, relating_object=building, products=[storey])

    space = f.create_entity(
        "IfcSpace",
        GlobalId=ifcopenshell.guid.new(),
        Name="Room 1",
        LongName="Room 1",
    )
    f.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatingStructure=storey,
        RelatedElements=[space],
    )
    qto = ifcopenshell.api.run("pset.add_qto", f, product=space, name="Qto_SpaceBaseQuantities")
    ifcopenshell.api.run("pset.edit_qto", f, qto=qto, properties={"NetFloorArea": 10.0})

    path = str(tmp_path / "modelo_teste.ifc")
    f.write(path)
    return path


@pytest.fixture
def pipeline(ifc_file_path) -> QualityPipeline:
    """Pipeline com grounding ids_bsdd para validar proveniência."""
    return QualityPipeline(ifc_file_path, _BUILDING_CTX, grounding_mode="ids_bsdd")


def _mock_batch_with_suggestion(issues, ctx, on_progress=None):
    """Retorna uma sugestão enriquecida para cada issue."""
    return [
        SuggestionSet(
            issue_id=i.id,
            prompt_hash="prompt-abc123",
            suggestions=[
                Suggestion(
                    label="Sala de Estar",
                    value="Sala de Estar",
                    justification="Contexto espacial",
                    confidence="alta",
                    source="llm",
                    bsdd_uri="https://example.org/bsdd/space",
                    ids_requirement_id="req-space-name",
                )
            ],
        )
        for i in issues
    ]


def _setup_with_grounded_suggestion(pipeline: QualityPipeline):
    """Diagnostica, gera sugestão e injeta contextos IDS/bSDD para a issue alvo."""
    pipeline.diagnose()
    pipeline.suggestion_gen.generate_batch = _mock_batch_with_suggestion
    pipeline.generate_suggestions()
    issue = next(i for i, _ in pipeline.issues_suggestions if i.issue_type == "space_unnamed")
    pipeline.ids_context_map[issue.id] = IDSContext(
        spec_name="Spec Espacos",
        requirement_description="LongName must not be empty",
        check_type="not_empty",
        expected_pset=None,
        expected_property="LongName",
        severity="high",
        requirement_id="req-space-name",
    )
    pipeline.bsdd_context_map[issue.id] = BSDDContext(
        class_name="Space",
        class_uri="https://example.org/bsdd/space",
        domain_name="IFC",
        raw_query="IfcSpace LongName",
        source_uris=["https://example.org/bsdd/space"],
        source_status="cache",
    )
    return issue


def test_audit_entry_has_grounding_sources(pipeline):
    issue = _setup_with_grounded_suggestion(pipeline)

    with patch.object(
        pipeline.post_validator,
        "validate_element",
        return_value=ValidationResult(guid=issue.element_guid, status="pass"),
    ):
        entry = pipeline.apply_correction(issue.id, "Sala de Estar", "accepted", "eng")

    assert entry.grounding_mode == "ids_bsdd"
    assert entry.grounding_sources == ["ids", "bsdd"]


def test_audit_entry_has_bsdd_uri(pipeline):
    issue = _setup_with_grounded_suggestion(pipeline)

    with patch.object(
        pipeline.post_validator,
        "validate_element",
        return_value=ValidationResult(guid=issue.element_guid, status="pass"),
    ):
        entry = pipeline.apply_correction(issue.id, "Sala de Estar", "accepted", "eng")

    assert entry.bsdd_uri == "https://example.org/bsdd/space"
    assert entry.ids_requirement_id == "req-space-name"


def test_audit_entry_has_post_validation(pipeline):
    issue = _setup_with_grounded_suggestion(pipeline)
    result = ValidationResult(guid=issue.element_guid, status="fail", ids_errors=["Ainda invalido"])

    with patch.object(pipeline.post_validator, "validate_element", return_value=result):
        entry = pipeline.apply_correction(issue.id, "Sala de Estar", "accepted", "eng")

    assert entry.post_validation == "fail"
    assert pipeline.get_post_validation_result(issue.id) == result


def test_csv_export_includes_new_columns(tmp_path: Path):
    logger = AuditLogger(session_id="sess-provenance")
    logger.log(
        AuditEntry(
            element_guid="A" * 22,
            element_class="IfcSpace",
            action="renomear_espaco",
            field="LongName",
            old_value="Room 1",
            new_value="Sala de Estar",
            decision="accepted",
            confidence="alta",
            source="llm",
            grounding_mode="ids_bsdd",
            grounding_sources=["ids", "bsdd"],
            bsdd_uri="https://example.org/bsdd/space",
            ids_requirement_id="req-space-name",
            post_validation="pass",
            prompt_hash="prompt-abc123",
        )
    )
    csv_path = tmp_path / "audit.csv"

    logger.export_csv(str(csv_path))

    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames is not None
        assert "grounding_sources" in reader.fieldnames
        assert "bsdd_uri" in reader.fieldnames
        assert "ids_requirement_id" in reader.fieldnames
        assert "post_validation" in reader.fieldnames
        row = next(reader)

    assert row["grounding_sources"] == "ids|bsdd"
    assert row["bsdd_uri"] == "https://example.org/bsdd/space"
    assert row["ids_requirement_id"] == "req-space-name"
    assert row["post_validation"] == "pass"


def test_json_export_includes_new_fields(tmp_path: Path):
    logger = AuditLogger(session_id="sess-provenance")
    logger.log(
        AuditEntry(
            element_guid="B" * 22,
            element_class="IfcSpace",
            action="renomear_espaco",
            field="LongName",
            old_value="Room 1",
            new_value="Sala de Estar",
            decision="accepted",
            confidence="alta",
            source="llm",
            grounding_mode="ids_bsdd",
            grounding_sources=["ids", "bsdd"],
            bsdd_uri="https://example.org/bsdd/space",
            ids_requirement_id="req-space-name",
            post_validation="pass",
            prompt_hash="prompt-abc123",
        )
    )
    json_path = tmp_path / "audit.jsonl"

    logger.export_json(str(json_path))

    payload = json.loads(json_path.read_text(encoding="utf-8").strip())

    assert payload["grounding_mode"] == "ids_bsdd"
    assert payload["grounding_sources"] == ["ids", "bsdd"]
    assert payload["bsdd_uri"] == "https://example.org/bsdd/space"
    assert payload["ids_requirement_id"] == "req-space-name"
    assert payload["post_validation"] == "pass"
