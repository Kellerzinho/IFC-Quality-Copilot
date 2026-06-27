"""Testes para QualityPipeline — orquestração principal do sistema."""

from pathlib import Path
from unittest.mock import patch

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.owner.settings
import ifcopenshell.guid
import ifcopenshell.util.element
import pytest

import json

from src.models import (
    AuditEntry,
    BSDDContext,
    DiagnosticReport,
    IDSContext,
    Issue,
    OperationalRule,
    ReadinessProfile,
    Suggestion,
    SuggestionSet,
    ValidationResult,
)
from src.pipeline import QualityPipeline


_BUILDING_CTX = {
    "building_type": "Residencial unifamiliar",
    "bioclimatic_zone": "3",
    "city": "São Paulo",
    "state": "SP",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ifc_file_path(tmp_path) -> str:
    """IFC2X3 mínimo com 1 IfcSpace genérico salvo em disco."""
    f = ifcopenshell.api.run("project.create_file", version="IFC2X3")

    # Owner obrigatório para IFC2X3
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

    # Espaço com nome genérico → gera issue space_unnamed
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
    """Pipeline com modelo mínimo."""
    return QualityPipeline(ifc_file_path, _BUILDING_CTX)


def _mock_batch(issues, ctx, on_progress=None):
    """Gerador LLM falso: retorna SuggestionSet vazio para cada issue."""
    return [SuggestionSet(issue_id=i.id, suggestions=[]) for i in issues]


def _mock_batch_with_suggestion(issues, ctx, on_progress=None):
    """Gerador LLM falso: retorna SuggestionSet com 1 sugestão para cada issue."""
    return [
        SuggestionSet(
            issue_id=i.id,
            suggestions=[
                Suggestion(
                    label="Sala de Estar",
                    value="Sala de Estar",
                    justification="25m²",
                    confidence="alta",
                    source="llm",
                )
            ],
        )
        for i in issues
    ]


def _setup_with_suggestions(pipeline, mock_batch=_mock_batch_with_suggestion) -> Issue:
    """Diagnose + generate_suggestions. Retorna a primeira space_unnamed issue."""
    pipeline.diagnose()
    pipeline.suggestion_gen.generate_batch = mock_batch
    pipeline.generate_suggestions()
    return next(i for i, _ in pipeline.issues_suggestions if i.issue_type == "space_unnamed")


# ---------------------------------------------------------------------------
# diagnose
# ---------------------------------------------------------------------------

def test_pipeline_diagnose(pipeline):
    """diagnose() retorna DiagnosticReport e o armazena em pipeline.report."""
    report = pipeline.diagnose()

    # Verifica atributos em vez de isinstance para evitar conflito de módulo
    # (analyzer.py usa src.models, tests usam models — mesmo arquivo, keys diferentes)
    assert hasattr(report, "issues")
    assert hasattr(report, "model_name")
    assert pipeline.report is report


def test_pipeline_diagnose_model_name(pipeline):
    """diagnose() popula model_name corretamente a partir do nome do arquivo."""
    report = pipeline.diagnose()

    assert report.model_name == "modelo_teste"


def test_pipeline_diagnose_finds_space_issue(pipeline):
    """diagnose() detecta ao menos 1 issue space_unnamed no modelo de teste."""
    report = pipeline.diagnose()

    space_issues = [i for i in report.issues if i.issue_type == "space_unnamed"]
    assert len(space_issues) >= 1


# ---------------------------------------------------------------------------
# generate_suggestions
# ---------------------------------------------------------------------------

def test_pipeline_generate_suggestions(pipeline):
    """generate_suggestions() retorna 1 par por issue, todos com tipos corretos."""
    pipeline.diagnose()
    pipeline.suggestion_gen.generate_batch = _mock_batch

    pairs = pipeline.generate_suggestions()

    assert isinstance(pairs, list)
    assert len(pairs) == len(pipeline.report.issues)
    # Issue e SuggestionSet podem vir de src.models (analyzer) ou models (mocks);
    # checar atributos é mais robusto que isinstance entre caminhos de módulo distintos
    assert all(hasattr(p[0], "issue_type") for p in pairs)
    assert all(hasattr(p[1], "suggestions") for p in pairs)


def test_pipeline_generate_suggestions_populates_state(pipeline):
    """generate_suggestions() preenche pipeline.issues_suggestions."""
    pipeline.diagnose()
    pipeline.suggestion_gen.generate_batch = _mock_batch

    pipeline.generate_suggestions()

    assert len(pipeline.issues_suggestions) > 0


def test_pipeline_generate_suggestions_calls_progress(pipeline):
    """generate_suggestions() repassa on_progress ao generate_batch."""
    pipeline.diagnose()
    progress_calls: list[tuple[int, int]] = []

    def fake_batch(issues, ctx, on_progress=None):
        if on_progress:
            for i in range(1, len(issues) + 1):
                on_progress(i, len(issues))
        return [SuggestionSet(issue_id=iss.id) for iss in issues]

    pipeline.suggestion_gen.generate_batch = fake_batch

    pipeline.generate_suggestions(on_progress=lambda c, t: progress_calls.append((c, t)))

    n = len(pipeline.report.issues)
    assert len(progress_calls) == n


def test_pipeline_sends_all_issues_to_llm(ifc_file_path):
    """O pipeline envia todas as issues ao LLM."""
    pipeline = QualityPipeline(ifc_file_path, _BUILDING_CTX)
    pipeline.diagnose()
    pipeline.suggestion_gen.generate_batch = _mock_batch

    pairs = pipeline.generate_suggestions()

    assert len(pairs) == len(pipeline.report.issues)


def test_pipeline_grounding_mode_ids_bsdd(ifc_file_path):
    """Em ids_bsdd, o pipeline preserva hooks de generate_batch e repassa o grounding."""
    fake_bsdd = BSDDContext(
        class_name="IfcSpace",
        class_uri="https://bsdd.example/IfcSpace",
        source_uris=["https://bsdd.example/IfcSpace"],
        source_status="live",
    )
    calls: list[dict] = []

    with (
        patch("src.pipeline.BSDDClient") as mock_bsdd_client,
        patch("src.pipeline.BSDDContextBuilder") as mock_builder_cls,
    ):
        mock_builder = mock_builder_cls.return_value
        mock_builder.build.return_value = fake_bsdd

        pipeline = QualityPipeline(ifc_file_path, _BUILDING_CTX, grounding_mode="ids_bsdd")
        report = pipeline.diagnose()
        issue = report.issues[0]
        issue.context["ids_context"] = IDSContext(
            spec_name="Spec Thermal",
            requirement_description="IfcSpace.LongName must be classified",
            check_type="exists",
            expected_pset="Pset_SpaceCommon",
            expected_property="LongName",
            expected_unit=None,
            expected_value=None,
            severity="high",
            requirement_id="REQ-1",
        ).model_dump()

        def fake_batch(
            issues,
            ctx,
            on_progress=None,
            ids_context_map=None,
            bsdd_context_map=None,
            grounding_mode="none",
        ):
            calls.append(
                {
                    "issue_ids": [current.id for current in issues],
                    "ids_context_map": ids_context_map,
                    "bsdd_context_map": bsdd_context_map,
                    "grounding_mode": grounding_mode,
                }
            )
            if on_progress:
                for index in range(1, len(issues) + 1):
                    on_progress(index, len(issues))
            return [SuggestionSet(issue_id=current.id, suggestions=[]) for current in issues]

        pipeline.suggestion_gen.generate_batch = fake_batch
        pairs = pipeline.generate_suggestions()

    assert len(pairs) == len(report.issues)
    assert len(calls) == 1
    assert calls[0]["grounding_mode"] == "ids_bsdd"
    assert issue.id in calls[0]["ids_context_map"]
    assert isinstance(calls[0]["ids_context_map"][issue.id], IDSContext)
    assert calls[0]["ids_context_map"][issue.id].spec_name == "Spec Thermal"
    assert calls[0]["bsdd_context_map"][issue.id] == fake_bsdd
    mock_bsdd_client.assert_called_once()
    mock_builder_cls.assert_called_once_with(mock_bsdd_client.return_value)
    mock_builder.build.assert_called()


def test_pipeline_forces_bsdd_even_when_none_is_requested(ifc_file_path):
    """O pipeline normaliza modos legados para ids_bsdd e inicializa bSDD."""
    with (
        patch("src.pipeline.BSDDClient") as mock_bsdd_client,
        patch("src.pipeline.BSDDContextBuilder") as mock_builder_cls,
    ):
        pipeline = QualityPipeline(ifc_file_path, _BUILDING_CTX, grounding_mode="none")
        pipeline.diagnose()
        pipeline.suggestion_gen.generate_batch = _mock_batch

        pairs = pipeline.generate_suggestions()

    assert len(pairs) == len(pipeline.report.issues)
    assert pipeline.grounding_mode == "ids_bsdd"
    mock_bsdd_client.assert_called_once()
    mock_builder_cls.assert_called_once_with(mock_bsdd_client.return_value)


# ---------------------------------------------------------------------------
# cache multi-modelo (F4)
# ---------------------------------------------------------------------------

def test_pipeline_init_preserves_other_model_cache(ifc_file_path, tmp_path, monkeypatch):
    """Instanciar a pipeline NÃO deve apagar o cache de outros modelos (benchmark multi-modelo, F4)."""
    from src.config import get_settings
    from src.suggestion_engine.suggestion_cache import (
        PROMPT_VERSION,
        SuggestionCache,
        compute_signature,
    )

    cache_path = tmp_path / "sug_cache.db"
    cache = SuggestionCache(cache_path)
    sig = compute_signature(
        model_version="modelo-antigo",
        prompt_version=PROMPT_VERSION,
        issue_type="pset_missing",
        ifc_class="IfcWall",
        target_pset=None,
        target_property=None,
        expected_type=None,
        expected_unit=None,
        requirement_id=None,
        candidates=None,
    )
    cache.set(
        sig,
        [Suggestion(label="x", value="x", justification="j", confidence="alta", source="llm")],
        model_version="modelo-antigo",
        prompt_version=PROMPT_VERSION,
    )
    cache.close()

    monkeypatch.setenv("SUGGESTION_CACHE_ENABLED", "true")
    monkeypatch.setenv("SUGGESTION_CACHE_PATH", str(cache_path))
    get_settings.cache_clear()
    try:
        pipeline = QualityPipeline(ifc_file_path, _BUILDING_CTX)
        assert pipeline.suggestion_cache is not None
        # A entrada de "modelo-antigo" deve sobreviver (modelo atual difere dela).
        assert pipeline.suggestion_cache.size() == 1
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# apply_correction
# ---------------------------------------------------------------------------

def test_pipeline_apply_correction(pipeline):
    """apply_correction() retorna AuditEntry com campos corretos."""
    issue = _setup_with_suggestions(pipeline)

    entry = pipeline.apply_correction(issue.id, "Sala de Estar", "accepted", "engenheiro")

    assert isinstance(entry, AuditEntry)
    assert entry.element_guid == issue.element_guid
    assert entry.new_value == "Sala de Estar"
    assert entry.decision == "accepted"
    assert entry.user == "engenheiro"


def test_pipeline_apply_correction_updates_issue_status(pipeline):
    """apply_correction() atualiza status da issue para o decision informado."""
    issue = _setup_with_suggestions(pipeline)

    pipeline.apply_correction(issue.id, "Sala de Estar", "accepted", "eng")

    assert issue.status == "accepted"


def test_pipeline_apply_correction_logs_to_audit(pipeline):
    """apply_correction() registra a entrada no AuditLogger."""
    issue = _setup_with_suggestions(pipeline)

    pipeline.apply_correction(issue.id, "Lavabo", "accepted", "eng")

    assert len(pipeline.audit_logger.entries) == 1
    assert pipeline.audit_logger.entries[0].new_value == "Lavabo"


def test_apply_correction_falls_back_to_grounded_provenance_when_top_suggestion_is_missing_fields(ifc_file_path):
    """apply_correction() usa a proveniencia do grounding quando a sugestao nao a preenche."""
    pipeline = QualityPipeline(ifc_file_path, _BUILDING_CTX, grounding_mode="ids_bsdd")
    pipeline.diagnose()

    issue = pipeline.report.issues[0]
    pipeline.ids_context_map[issue.id] = IDSContext(
        spec_name="Spec Thermal",
        requirement_description="IfcSpace.LongName must be classified",
        check_type="exists",
        expected_pset="Pset_SpaceCommon",
        expected_property="LongName",
        expected_unit=None,
        expected_value=None,
        severity="high",
        requirement_id="REQ-1",
    )
    pipeline.bsdd_context_map[issue.id] = BSDDContext(
        class_name="IfcSpace",
        class_uri="https://bsdd.example/IfcSpace",
        source_uris=["https://bsdd.example/IfcSpace"],
        source_status="live",
    )
    pipeline.issues_suggestions = [
        (
            issue,
            SuggestionSet(
                issue_id=issue.id,
                suggestions=[
                    Suggestion(
                        label="Sala de Estar",
                        value="Sala de Estar",
                        justification="Preenchimento sugerido",
                        confidence="alta",
                        source="llm",
                        bsdd_uri=None,
                        ids_requirement_id=None,
                    )
                ],
            ),
        )
    ]

    entry = pipeline.apply_correction(issue.id, "Sala de Estar", "accepted", "eng")

    assert entry.bsdd_uri == "https://bsdd.example/IfcSpace"
    assert entry.ids_requirement == "REQ-1"


def test_apply_correction_runs_post_validation(pipeline):
    """apply_correction() roda pÃ³s-validaÃ§Ã£o automaticamente apÃ³s a escrita."""
    issue = _setup_with_suggestions(pipeline)
    result = ValidationResult(guid=issue.element_guid, status="pass")

    with patch.object(pipeline.post_validator, "validate_element", return_value=result) as mock_validate:
        pipeline.apply_correction(issue.id, "Sala de Estar", "accepted", "eng")

    mock_validate.assert_called_once_with(issue.element_guid)
    assert pipeline.get_post_validation_result(issue.id) == result


def test_apply_correction_records_post_validation_in_audit(pipeline):
    """apply_correction() registra o resultado da pÃ³s-validaÃ§Ã£o na auditoria."""
    issue = _setup_with_suggestions(pipeline)
    result = ValidationResult(
        guid=issue.element_guid,
        status="fail",
        ids_errors=["Ainda viola requisito IDS"],
    )

    with patch.object(pipeline.post_validator, "validate_element", return_value=result):
        entry = pipeline.apply_correction(issue.id, "Sala de Estar", "accepted", "eng")

    assert entry.post_validation == "fail"
    assert pipeline.audit_logger.entries[0].post_validation == "fail"
    assert pipeline.get_post_validation_result(issue.id) == result
    assert issue.status == "accepted"


def test_apply_correction_normalizes_decorated_numeric_value(pipeline):
    issue = Issue(
        element_guid="A" * 22,
        element_class="IfcWall",
        issue_type="pset_missing",
        severity="high",
        description="ThermalTransmittance ausente",
        context={"check_property": "ThermalTransmittance", "pset_name": "Pset_WallCommon"},
    )
    pipeline.diagnose()
    pipeline.issues_suggestions = [(issue, SuggestionSet(issue_id=issue.id, suggestions=[]))]

    with patch.object(pipeline, "_write_correction", return_value=None) as mock_write:
        entry = pipeline.apply_correction(
            issue.id,
            "Pset_WallCommon.ThermalTransmittance = 2.50 W/(m².K)",
            "edited",
            "eng",
        )

    mock_write.assert_called_once_with(issue, pytest.approx(2.5))
    assert entry.new_value == pytest.approx(2.5)


def test_apply_correction_rejects_invalid_numeric_value(pipeline):
    issue = Issue(
        element_guid="A" * 22,
        element_class="IfcWall",
        issue_type="pset_missing",
        severity="high",
        description="ThermalTransmittance ausente",
        context={"check_property": "ThermalTransmittance", "pset_name": "Pset_WallCommon"},
    )
    pipeline.diagnose()
    pipeline.issues_suggestions = [(issue, SuggestionSet(issue_id=issue.id, suggestions=[]))]

    with pytest.raises(ValueError, match="Valor invalido"):
        pipeline.apply_correction(issue.id, "zero", "edited", "eng")


def test_apply_correction_writes_quantity_missing_to_qto(pipeline):
    pipeline.diagnose()
    space = pipeline.ifc_file.by_type("IfcSpace")[0]
    issue = Issue(
        element_guid=space.GlobalId,
        element_class="IfcSpace",
        issue_type="quantity_missing",
        severity="low",
        description="NetFloorArea ausente",
        context={"check_pset": "Qto_SpaceBaseQuantities", "check_property": "NetFloorArea"},
    )
    pipeline.issues_suggestions = [
        (
            issue,
            SuggestionSet(
                issue_id=issue.id,
                suggestions=[
                    Suggestion(
                        label="12.5",
                        value=12.5,
                        justification="valor editado",
                        confidence="alta",
                    )
                ],
            ),
        )
    ]

    entry = pipeline.apply_correction(issue.id, "12,5 m2", "edited", "eng")

    qtos = ifcopenshell.util.element.get_psets(space, qtos_only=True)
    assert qtos["Qto_SpaceBaseQuantities"]["NetFloorArea"] == pytest.approx(12.5)
    assert entry.action == "preencher_base_quantities"


def test_apply_correction_rejects_material_unmapped_auto_write(pipeline):
    pipeline.diagnose()
    space = pipeline.ifc_file.by_type("IfcSpace")[0]
    issue = Issue(
        element_guid=space.GlobalId,
        element_class="IfcSpace",
        issue_type="material_unmapped",
        severity="low",
        description="Material nao mapeado",
        context={},
    )
    pipeline.issues_suggestions = [(issue, SuggestionSet(issue_id=issue.id, suggestions=[]))]

    with pytest.raises(ValueError, match="Valor invalido"):
        pipeline.apply_correction(issue.id, "Material nao mapeado para IfcMaterial", "accepted", "eng")


def test_post_validation_disabled_skips(pipeline):
    """Com post_validation_enabled=False, apply_correction() nÃ£o chama o PostValidator."""
    issue = _setup_with_suggestions(pipeline)
    pipeline.settings.post_validation_enabled = False

    with patch.object(pipeline.post_validator, "validate_element") as mock_validate:
        entry = pipeline.apply_correction(issue.id, "Sala de Estar", "accepted", "eng")

    mock_validate.assert_not_called()
    assert entry.post_validation == "skip"
    assert pipeline.get_post_validation_result(issue.id) is not None
    assert pipeline.get_post_validation_result(issue.id).status == "skip"


def test_pipeline_apply_correction_unknown_id_raises(pipeline):
    """apply_correction() levanta ValueError para issue_id inexistente."""
    pipeline.diagnose()
    pipeline.issues_suggestions = []

    with pytest.raises(ValueError, match="não encontrada"):
        pipeline.apply_correction("nao-existe", "x", "accepted", "eng")


# ---------------------------------------------------------------------------
# skip_issue
# ---------------------------------------------------------------------------

def test_pipeline_skip_issue(pipeline):
    """skip_issue() atualiza status da issue para 'skipped'."""
    issue = _setup_with_suggestions(pipeline)

    pipeline.skip_issue(issue.id, "engenheiro")

    assert issue.status == "skipped"


def test_pipeline_skip_issue_unknown_id_raises(pipeline):
    """skip_issue() levanta ValueError para issue_id inexistente."""
    pipeline.diagnose()
    pipeline.issues_suggestions = []

    with pytest.raises(ValueError, match="não encontrada"):
        pipeline.skip_issue("nao-existe", "eng")


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

def test_pipeline_export(pipeline, tmp_path):
    """export() grava IFC corrigido e logs de auditoria, retornando caminhos."""
    pipeline.diagnose()
    pipeline.issues_suggestions = []
    output_dir = str(tmp_path / "output")

    result = pipeline.export(output_dir)

    assert set(result.keys()) >= {"ifc", "csv", "json", "bcf"}
    assert Path(result["ifc"]).exists()
    assert Path(result["csv"]).exists()
    assert Path(result["json"]).exists()
    assert Path(result["bcf"]).exists()


def test_pipeline_export_ifc_name_contains_model_stem(pipeline, tmp_path):
    """export() inclui o nome do modelo no arquivo IFC exportado."""
    pipeline.diagnose()
    pipeline.issues_suggestions = []

    result = pipeline.export(str(tmp_path / "out"))

    assert "modelo_teste" in Path(result["ifc"]).name


def test_pipeline_export_creates_output_dir(pipeline, tmp_path):
    """export() cria o diretório de saída se não existir."""
    pipeline.diagnose()
    pipeline.issues_suggestions = []
    output_dir = str(tmp_path / "novo" / "sub")

    pipeline.export(output_dir)

    assert Path(output_dir).is_dir()


def test_export_generates_bcf_file(pipeline, tmp_path):
    """export() deve gerar arquivo .bcf no diretório de saída."""
    pipeline.diagnose()
    pipeline.issues_suggestions = []

    result = pipeline.export(str(tmp_path / "out"))

    assert "bcf" in result
    assert Path(result["bcf"]).exists()
    assert Path(result["bcf"]).suffix == ".bcf"


# ---------------------------------------------------------------------------
# get_progress
# ---------------------------------------------------------------------------

def test_pipeline_progress_empty(pipeline):
    """get_progress() retorna zeros quando issues_suggestions está vazio."""
    progress = pipeline.get_progress()

    assert progress == {"total": 0, "resolved": 0, "pending": 0, "percentage": 0.0}


def test_pipeline_progress_before_any_resolution(pipeline):
    """get_progress() mostra tudo como pending antes de qualquer correção."""
    pipeline.diagnose()
    pipeline.suggestion_gen.generate_batch = _mock_batch
    pipeline.generate_suggestions()

    progress = pipeline.get_progress()

    assert progress["total"] > 0
    assert progress["pending"] == progress["total"]
    assert progress["resolved"] == 0
    assert progress["percentage"] == 0.0


def test_pipeline_progress(pipeline):
    """get_progress() atualiza após apply_correction."""
    issue = _setup_with_suggestions(pipeline)
    total = pipeline.get_progress()["total"]

    pipeline.apply_correction(issue.id, "Sala de Estar", "accepted", "eng")

    after = pipeline.get_progress()
    assert after["resolved"] == 1
    assert after["pending"] == total - 1
    assert after["percentage"] == pytest.approx(1 / total * 100, rel=1e-3)


# ---------------------------------------------------------------------------
# get_issue_by_id
# ---------------------------------------------------------------------------

def test_pipeline_get_issue_by_id_found(pipeline):
    """get_issue_by_id() retorna (Issue, SuggestionSet) para ID válido."""
    issue = _setup_with_suggestions(pipeline)

    result = pipeline.get_issue_by_id(issue.id)

    assert result is not None
    assert result[0].id == issue.id
    assert isinstance(result[1], SuggestionSet)


def test_pipeline_get_issue_by_id_not_found(pipeline):
    """get_issue_by_id() retorna None para ID inexistente."""
    pipeline.diagnose()
    pipeline.issues_suggestions = []

    assert pipeline.get_issue_by_id("nao-existe") is None


# ---------------------------------------------------------------------------
# Integração IDS
# ---------------------------------------------------------------------------

def _make_ids_issue(guid: str, issue_type: str = "pset_missing", check_property: str = "TestProp") -> Issue:
    """Cria Issue mínima simulando saída do apply_rules."""
    return Issue(
        element_guid=guid,
        element_class="IfcWall",
        issue_type=issue_type,  # type: ignore[arg-type]
        severity="high",
        description=f"Pset.{check_property} ausente",
        context={"check_property": check_property},
    )


def _make_operational_rule(severity: str = "high") -> OperationalRule:
    """Cria OperationalRule mínima para testes."""
    return OperationalRule(
        source_spec="Spec Teste",
        filter_entity="IfcWall",
        check_pset="Pset_WallCommon",
        check_property="TestProp",
        check_type="exists",
        severity=severity,  # type: ignore[arg-type]
    )


def test_pipeline_with_ids_generates_additional_issues(ifc_file_path):
    """diagnose() com IDS válido adiciona issues extras ao relatório."""
    pipeline = QualityPipeline(ifc_file_path, _BUILDING_CTX, ids_path="fake.ids")

    fake_issue = _make_ids_issue("A" * 22, check_property="UniqueIDSProp")
    fake_rule = _make_operational_rule()

    with (
        patch("src.pipeline.parse_ids", return_value=[]) as mock_parse,
        patch("src.pipeline.generate_rules", return_value=[fake_rule]),
        patch("src.pipeline.apply_rules", return_value=[fake_issue]),
    ):
        mock_parse.return_value = [object()]  # 1 spec qualquer
        report = pipeline.diagnose()

    issue_props = [i.context.get("check_property") for i in report.issues]
    assert "UniqueIDSProp" in issue_props
    assert pipeline._ids_issues_count >= 1


def test_pipeline_without_ids_works_normally(ifc_file_path):
    """diagnose() sem ids_path funciona normalmente e get_ids_summary() retorna None."""
    pipeline = QualityPipeline(ifc_file_path, _BUILDING_CTX)

    report = pipeline.diagnose()

    assert hasattr(report, "issues")
    assert pipeline.get_ids_summary() is None


def test_pipeline_ids_deduplicates_issues(ifc_file_path):
    """diagnose() com IDS não duplica issues já detectadas pelo IFCAnalyzer."""
    pipeline = QualityPipeline(ifc_file_path, _BUILDING_CTX, ids_path="fake.ids")

    # Primeiro diagnose sem IDS para capturar issues do IFCAnalyzer
    pipeline_base = QualityPipeline(ifc_file_path, _BUILDING_CTX)
    base_report = pipeline_base.diagnose()
    base_count = len(base_report.issues)

    # IDS retorna as mesmas issues já existentes (mesma guid + issue_type + check_property)
    overlapping_issues = [
        _make_ids_issue(
            i.element_guid,
            issue_type=i.issue_type,
            check_property=i.context.get("check_property", ""),
        )
        for i in base_report.issues
    ]

    with (
        patch("src.pipeline.parse_ids", return_value=[object()]),
        patch("src.pipeline.generate_rules", return_value=[_make_operational_rule()]),
        patch("src.pipeline.apply_rules", return_value=overlapping_issues),
    ):
        report = pipeline.diagnose()

    assert len(report.issues) == base_count
    assert pipeline._ids_issues_count == 0


def test_pipeline_ids_parse_error_falls_back(ifc_file_path, tmp_path):
    """diagnose() com ids_path inválido não levanta exceção e retorna relatório normal."""
    invalid_ids_path = str(tmp_path / "nao_existe.ids")
    pipeline = QualityPipeline(ifc_file_path, _BUILDING_CTX, ids_path=invalid_ids_path)

    report = pipeline.diagnose()

    assert hasattr(report, "issues")
    assert pipeline._ids_loaded is False
    assert pipeline.get_ids_summary() is None


def test_pipeline_get_ids_summary(ifc_file_path):
    """get_ids_summary() retorna dict com todas as chaves esperadas após IDS carregado."""
    pipeline = QualityPipeline(ifc_file_path, _BUILDING_CTX, ids_path="fake.ids")

    rules = [_make_operational_rule("high"), _make_operational_rule("medium")]

    with (
        patch("src.pipeline.parse_ids", return_value=[object(), object()]),
        patch("src.pipeline.generate_rules", return_value=rules),
        patch("src.pipeline.apply_rules", return_value=[_make_ids_issue("B" * 22)]),
    ):
        pipeline.diagnose()

    summary = pipeline.get_ids_summary()

    assert summary is not None
    assert summary["specs_count"] == 2
    assert summary["rules_count"] == 2
    assert "rules_by_severity" in summary
    assert summary["rules_by_severity"].get("high") == 1
    assert summary["rules_by_severity"].get("medium") == 1
    assert summary["issues_from_ids"] >= 0


# ---------------------------------------------------------------------------
# Perfis de readiness
# ---------------------------------------------------------------------------

_IDS_TEMPLATES_DIR = Path(__file__).parent.parent / "data" / "ids_templates"
_EXISTING_IDS_FILENAME = "residencial_nbr15575.ids"


def _make_profile(issue_types: list[str], ids_filename: str | None = None) -> ReadinessProfile:
    """Cria ReadinessProfile mínimo para testes."""
    return ReadinessProfile(
        id="test_profile",
        name="Perfil de Teste",
        description="Perfil criado em testes automatizados.",
        ids_filename=ids_filename,
        issue_types=issue_types,
        blocking_severities=["high"],
    )


def test_pipeline_with_profile_loads_ids(ifc_file_path):
    """__init__ com perfil que tem ids_filename existente seta ids_path automaticamente."""
    profile = _make_profile(["pset_missing"], ids_filename=_EXISTING_IDS_FILENAME)

    pipeline = QualityPipeline(ifc_file_path, _BUILDING_CTX, profile=profile)

    assert pipeline.ids_path is not None
    assert pipeline.ids_path.endswith(_EXISTING_IDS_FILENAME)


def test_pipeline_compute_readiness_ready(ifc_file_path):
    """compute_readiness() retorna 'ready' quando perfil não tem issues relevantes."""
    # Perfil só checa relation_broken; o modelo de teste só tem space_unnamed → 0 falhas
    profile = _make_profile(["relation_broken"])
    pipeline = QualityPipeline(ifc_file_path, _BUILDING_CTX, profile=profile)
    pipeline.diagnose()

    score = pipeline.compute_readiness()

    assert score.profile_id == "test_profile"
    assert score.blocking_issues == 0
    assert score.score_percent == pytest.approx(100.0)
    assert score.status == "ready"


def test_pipeline_compute_readiness_not_ready(ifc_file_path):
    """compute_readiness() retorna 'not_ready' quando falhas cobrem todas as verificações."""
    profile = _make_profile(["space_unnamed", "pset_missing"])
    pipeline = QualityPipeline(ifc_file_path, _BUILDING_CTX, profile=profile)
    pipeline.diagnose()

    # Injeta issue high para garantir blocking_issues >= 1 e pct=0%
    pipeline.report.issues.append(  # type: ignore[union-attr]
        Issue(
            element_guid="B" * 22,
            element_class="IfcWall",
            issue_type="pset_missing",
            severity="high",
            description="Propriedade crítica ausente",
        )
    )

    score = pipeline.compute_readiness()

    assert score.failed >= 1
    assert score.blocking_issues >= 1
    assert score.status == "not_ready"


def test_pipeline_without_profile_still_works(ifc_file_path):
    """diagnose() e generate_suggestions() funcionam normalmente sem perfil."""
    pipeline = QualityPipeline(ifc_file_path, _BUILDING_CTX)
    pipeline.diagnose()
    pipeline.suggestion_gen.generate_batch = _mock_batch

    pipeline.generate_suggestions()

    assert len(pipeline.issues_suggestions) > 0
    with pytest.raises(ValueError, match="Nenhum perfil"):
        pipeline.compute_readiness()


def test_pipeline_suggestions_prioritize_profile_types(ifc_file_path):
    """generate_suggestions() com perfil coloca issue_types do perfil antes dos demais."""
    # Perfil prioriza pset_missing; modelo base gera space_unnamed
    profile = _make_profile(["pset_missing"])
    pipeline = QualityPipeline(ifc_file_path, _BUILDING_CTX, profile=profile)
    pipeline.diagnose()

    # Injeta pset_missing no final — sem perfil seria o último
    pset_issue = Issue(
        element_guid="A" * 22,
        element_class="IfcWall",
        issue_type="pset_missing",
        severity="high",
        description="Propriedade ausente",
    )
    pipeline.report.issues.append(pset_issue)  # type: ignore[union-attr]

    pipeline.suggestion_gen.generate_batch = _mock_batch
    pipeline.generate_suggestions()

    first_issue_type = pipeline.issues_suggestions[0][0].issue_type
    assert first_issue_type == "pset_missing"


def test_pipeline_export_includes_readiness(ifc_file_path, tmp_path):
    """export() inclui profile_id, profile_name e readiness_score nas métricas."""
    profile = _make_profile(["relation_broken"])  # 0 falhas → ready
    pipeline = QualityPipeline(ifc_file_path, _BUILDING_CTX, profile=profile)
    pipeline.diagnose()
    output_dir = str(tmp_path / "output")

    result = pipeline.export(output_dir)

    with open(result["metrics"], encoding="utf-8") as fh:
        metrics = json.load(fh)

    assert metrics["profile_id"] == "test_profile"
    assert metrics["profile_name"] == "Perfil de Teste"
    assert "readiness_score" in metrics
    assert metrics["readiness_score"] == pytest.approx(100.0)
    assert metrics["readiness_status"] == "ready"


# ---------------------------------------------------------------------------
# diagnose_and_start_suggestions
# ---------------------------------------------------------------------------

def _fake_generate(issue, ctx):
    """Gerador LLM falso: retorna SuggestionSet vazio para uma issue."""
    return SuggestionSet(issue_id=issue.id, suggestions=[])


def _wait_worker(pipeline, timeout: float = 5.0) -> None:
    """Aguarda o worker terminar, com timeout."""
    if pipeline.worker and pipeline.worker._thread:
        pipeline.worker._thread.join(timeout=timeout)


def test_diagnose_and_start_suggestions_returns_report(pipeline):
    """diagnose_and_start_suggestions() retorna DiagnosticReport e cria issue_store."""
    pipeline.suggestion_gen.generate = _fake_generate

    report = pipeline.diagnose_and_start_suggestions()
    pipeline.stop_worker()

    assert hasattr(report, "issues")
    assert hasattr(report, "model_name")
    assert pipeline.issue_store is not None
    assert pipeline.report is report


def test_worker_processes_remaining(pipeline):
    """Worker processa issues via LLM mock e as marca como ready após conclusão."""
    pipeline.suggestion_gen.generate = _fake_generate

    pipeline.diagnose_and_start_suggestions()
    _wait_worker(pipeline)

    progress = pipeline.get_suggestions_progress()
    done = progress["ready"] + progress["failed"]
    assert progress["queued"] == 0
    assert progress["processing"] == 0
    assert done == progress["total"]

    pipeline.stop_worker()


def test_get_suggestions_progress(pipeline):
    """get_suggestions_progress() retorna dict com todas as chaves esperadas."""
    pipeline.suggestion_gen.generate = _fake_generate
    pipeline.diagnose_and_start_suggestions()
    _wait_worker(pipeline)
    pipeline.stop_worker()

    progress = pipeline.get_suggestions_progress()

    expected_keys = {"total", "queued", "processing", "ready", "failed", "percent_complete"}
    assert expected_keys.issubset(progress.keys())
    assert isinstance(progress["total"], int)
    assert isinstance(progress["percent_complete"], float)


def test_get_suggestions_progress_before_diagnose(pipeline):
    """get_suggestions_progress() antes de diagnose retorna estrutura zerada."""
    progress = pipeline.get_suggestions_progress()

    assert progress["total"] == 0
    assert progress["percent_complete"] == 0.0


def test_get_available_issues_mixed_status(pipeline):
    """get_available_issues() retorna tuplas (Issue, SuggestionSet|None, status) para todas as issues."""
    pipeline.suggestion_gen.generate = _fake_generate
    pipeline.diagnose_and_start_suggestions()

    available = pipeline.get_available_issues()
    pipeline.stop_worker()

    assert isinstance(available, list)
    assert len(available) == len(pipeline.report.issues)
    for issue, sset, status in available:
        assert hasattr(issue, "issue_type")
        assert isinstance(status, str)
        # sset pode ser None (queued/processing) ou SuggestionSet (ready/failed)


def test_stop_worker(pipeline):
    """stop_worker() para o worker e limpa a referência."""
    pipeline.suggestion_gen.generate = _fake_generate
    pipeline.diagnose_and_start_suggestions()

    assert pipeline.worker is not None

    pipeline.stop_worker()

    assert pipeline.worker is None


def test_backward_compat_generate_suggestions(pipeline):
    """generate_suggestions() síncrono continua funcionando após adição dos métodos assíncronos."""
    pipeline.diagnose()
    pipeline.suggestion_gen.generate_batch = _mock_batch

    pairs = pipeline.generate_suggestions()

    assert isinstance(pairs, list)
    assert len(pairs) == len(pipeline.report.issues)
    assert all(hasattr(p[0], "issue_type") for p in pairs)
    assert all(hasattr(p[1], "suggestions") for p in pairs)
