"""Testes para os modelos Pydantic em src/models.py."""

import pytest
from pydantic import ValidationError

from src.models import (
    AuditEntry,
    DiagnosticReport,
    GeometryInfo,
    IFCElement,
    Issue,
    MaterialInfo,
    MaterialLayer,
    OperationalRule,
    ProfileRegistry,
    ReadinessProfile,
    ReadinessScore,
    Suggestion,
    SuggestionSet,
)

VALID_GUID = "3nJOFsJsX8QO2odKZbQnBj"  # 22 chars


class TestIFCElementCreate:
    def test_create_minimal_element(self):
        """Deve criar um IFCElement com apenas os campos obrigatórios."""
        element = IFCElement(guid=VALID_GUID, ifc_class="IfcWall")

        assert element.guid == VALID_GUID
        assert element.ifc_class == "IfcWall"
        assert element.name is None
        assert element.long_name is None
        assert element.description is None
        assert element.properties == {}
        assert element.relationships == []
        assert element.geometry_info is None
        assert element.floor is None
        assert element.material_info is None

    def test_create_full_element(self):
        """Deve criar um IFCElement com todos os campos preenchidos."""
        element = IFCElement(
            guid=VALID_GUID,
            ifc_class="IfcSpace",
            name="SALA 101",
            long_name="Sala de Reuniões",
            description="Sala principal",
            properties={"Pset_SpaceCommon": {"Category": "office", "GrossFloorArea": 25.0}},
            relationships=[{"type": "IfcRelSpaceBoundary", "related_guid": "1234567890123456789012"}],
            geometry_info=GeometryInfo(area_m2=25.0, height_m=2.8),
            floor="Pavimento 1",
            material_info=MaterialInfo(material_name="Concreto"),
        )

        assert element.name == "SALA 101"
        assert element.long_name == "Sala de Reuniões"
        assert element.floor == "Pavimento 1"

    def test_invalid_guid_raises(self):
        """Deve lançar ValidationError se o GUID não tiver 22 caracteres."""
        with pytest.raises(ValidationError, match="22 caracteres"):
            IFCElement(guid="curto", ifc_class="IfcWall")

    def test_guid_too_long_raises(self):
        """Deve lançar ValidationError se o GUID tiver mais de 22 caracteres."""
        with pytest.raises(ValidationError, match="22 caracteres"):
            IFCElement(guid="A" * 30, ifc_class="IfcWall")


class TestGetPsetValue:
    def test_get_pset_value_existing(self):
        """Deve retornar o valor correto quando pset e propriedade existem."""
        element = IFCElement(
            guid=VALID_GUID,
            ifc_class="IfcWall",
            properties={"Pset_WallCommon": {"IsExternal": True, "ThermalTransmittance": 2.5}},
        )

        assert element.get_pset_value("Pset_WallCommon", "IsExternal") is True
        assert element.get_pset_value("Pset_WallCommon", "ThermalTransmittance") == 2.5

    def test_get_pset_value_missing_pset(self):
        """Deve retornar None quando o Pset não existe."""
        element = IFCElement(guid=VALID_GUID, ifc_class="IfcWall")

        assert element.get_pset_value("Pset_WallCommon", "IsExternal") is None

    def test_get_pset_value_missing_prop(self):
        """Deve retornar None quando o Pset existe mas a propriedade não."""
        element = IFCElement(
            guid=VALID_GUID,
            ifc_class="IfcWall",
            properties={"Pset_WallCommon": {"IsExternal": True}},
        )

        assert element.get_pset_value("Pset_WallCommon", "ThermalTransmittance") is None

    def test_get_pset_value_none_stored(self):
        """Deve retornar None quando o valor da propriedade é explicitamente None."""
        element = IFCElement(
            guid=VALID_GUID,
            ifc_class="IfcWall",
            properties={"Pset_WallCommon": {"FireRating": None}},
        )

        assert element.get_pset_value("Pset_WallCommon", "FireRating") is None


class TestHasPset:
    def test_has_pset_present(self):
        """Deve retornar True quando o Pset existe."""
        element = IFCElement(
            guid=VALID_GUID,
            ifc_class="IfcWall",
            properties={"Pset_WallCommon": {"IsExternal": False}},
        )

        assert element.has_pset("Pset_WallCommon") is True

    def test_has_pset_absent(self):
        """Deve retornar False quando o Pset não existe."""
        element = IFCElement(guid=VALID_GUID, ifc_class="IfcWall")

        assert element.has_pset("Pset_WallCommon") is False

    def test_has_pset_empty_properties(self):
        """Deve retornar False quando properties está vazio."""
        element = IFCElement(guid=VALID_GUID, ifc_class="IfcSlab", properties={})

        assert element.has_pset("Pset_SlabCommon") is False


class TestShortGuid:
    def test_short_guid(self):
        """Deve retornar os primeiros 8 caracteres do GUID."""
        element = IFCElement(guid=VALID_GUID, ifc_class="IfcSpace")

        assert element.short_guid == VALID_GUID[:8]
        assert len(element.short_guid) == 8

    def test_short_guid_is_prefix(self):
        """O short_guid deve ser prefixo do guid completo."""
        element = IFCElement(guid=VALID_GUID, ifc_class="IfcDoor")

        assert VALID_GUID.startswith(element.short_guid)


def _make_issue(**kwargs) -> Issue:
    """Fábrica de Issue com valores padrão para os testes."""
    defaults = dict(
        element_guid=VALID_GUID,
        element_class="IfcSpace",
        issue_type="space_unnamed",
        severity="low",
        description="Espaço com nome genérico.",
    )
    defaults.update(kwargs)
    return Issue(**defaults)


class TestIssueCreate:
    def test_issue_auto_generates_id(self):
        """Deve gerar id automaticamente com 8 caracteres."""
        issue = _make_issue()

        assert issue.id is not None
        assert len(issue.id) == 8

    def test_issue_ids_are_unique(self):
        """Dois Issues criados sem id explícito devem ter ids diferentes."""
        a = _make_issue()
        b = _make_issue()

        assert a.id != b.id

    def test_issue_default_status_is_pending(self):
        """Status inicial deve ser 'pending'."""
        issue = _make_issue()

        assert issue.status == "pending"

    def test_issue_resolved_at_starts_none(self):
        """resolved_at deve ser None antes de qualquer resolução."""
        issue = _make_issue()

        assert issue.resolved_at is None


class TestIssueLLMContext:
    def test_issue_to_llm_context_space(self):
        """Deve formatar corretamente o contexto de um IfcSpace."""
        issue = _make_issue(
            element_class="IfcSpace",
            element_name="Room 3",
            context={"Área": "4.2 m²", "Contém": "WC, lavatório", "Adjacente a": "Dormitório Casal"},
        )
        result = issue.to_llm_context()

        assert result.startswith("IfcSpace #")
        assert "nome atual 'Room 3'" in result
        assert "Área: 4.2 m²" in result
        assert "Contém: WC, lavatório" in result
        assert "Adjacente a: Dormitório Casal" in result

    def test_issue_to_llm_context_pset(self):
        """Deve formatar corretamente o contexto de um problema de Pset ausente."""
        issue = _make_issue(
            element_class="IfcWall",
            element_name=None,
            issue_type="pset_missing",
            severity="high",
            context={"Pset ausente": "Pset_WallCommon", "Propriedade": "ThermalTransmittance"},
        )
        result = issue.to_llm_context()

        assert result.startswith("IfcWall #")
        assert "nome atual" not in result  # sem nome, linha de identificação só tem classe e guid
        assert "Pset ausente: Pset_WallCommon" in result
        assert "Propriedade: ThermalTransmittance" in result

    def test_issue_to_llm_context_empty_context(self):
        """Deve retornar apenas a linha de identificação quando context está vazio."""
        issue = _make_issue(element_name="Sala 01", context={})
        result = issue.to_llm_context()

        assert result.count("\n") == 0  # apenas a linha de cabeçalho


class TestIssueResolve:
    def test_issue_resolve_updates_status(self):
        """Deve atualizar status, resolved_at e resolution_value após resolução."""
        issue = _make_issue()
        issue.resolve(value="Sala de Reuniões", decision="accepted")

        assert issue.status == "accepted"
        assert issue.resolved_at is not None
        assert issue.resolution_value == "Sala de Reuniões"

    def test_issue_resolve_rejected_sets_none_value(self):
        """Deve aceitar None como resolution_value para decisões de rejeição."""
        issue = _make_issue()
        issue.resolve(value=None, decision="rejected")

        assert issue.status == "rejected"
        assert issue.resolution_value is None
        assert issue.resolved_at is not None

    def test_issue_resolve_edited(self):
        """Deve registrar valor editado manualmente pelo usuário."""
        issue = _make_issue()
        issue.resolve(value="Banheiro Social", decision="edited")

        assert issue.status == "edited"
        assert issue.resolution_value == "Banheiro Social"


class TestIssueSeverityOrder:
    def test_issue_severity_order(self):
        """high < medium < low em ordem numérica para ordenação correta."""
        high = _make_issue(severity="high")
        medium = _make_issue(severity="medium")
        low = _make_issue(severity="low")

        assert high.severity_order == 0
        assert medium.severity_order == 1
        assert low.severity_order == 2

    def test_severity_order_is_sortable(self):
        """Uma lista de Issues deve poder ser ordenada por severity_order."""
        issues = [
            _make_issue(severity="low"),
            _make_issue(severity="high"),
            _make_issue(severity="medium"),
        ]
        sorted_issues = sorted(issues, key=lambda i: i.severity_order)

        assert [i.severity for i in sorted_issues] == ["high", "medium", "low"]


class TestIssueTypeLabel:
    def test_issue_type_label(self):
        """Deve retornar o label em português correto para cada tipo."""
        cases = {
            "space_unnamed": "Espaço sem classificação funcional",
            "pset_missing": "Propriedade ausente",
            "relation_broken": "Relação espacial quebrada",
            "system_unclassified": "Sistema construtivo não classificado",
        }
        for issue_type, expected_label in cases.items():
            issue = _make_issue(issue_type=issue_type)  # type: ignore[arg-type]
            assert issue.type_label == expected_label


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_suggestion(**kwargs) -> Suggestion:
    """Fábrica de Suggestion com valores padrão para os testes."""
    defaults = dict(
        label="Lavabo Suíte",
        value="Lavabo Suíte",
        justification="4.2m² com WC e lavatório adjacente a dormitório",
        confidence="alta",
        source="heuristic",
    )
    defaults.update(kwargs)
    return Suggestion(**defaults)


def _make_audit_entry(**kwargs) -> AuditEntry:
    """Fábrica de AuditEntry com valores padrão para os testes."""
    defaults = dict(
        element_guid=VALID_GUID,
        element_class="IfcSpace",
        action="renomear_espaco",
        field="LongName",
        old_value="Room 3",
        new_value="Lavabo Suíte",
        decision="accepted",
        confidence="alta",
        source="heuristic",
    )
    defaults.update(kwargs)
    return AuditEntry(**defaults)


# ---------------------------------------------------------------------------
# Suggestion
# ---------------------------------------------------------------------------

class TestSuggestionConfidenceEmoji:
    def test_suggestion_confidence_emoji(self):
        """Cada nível de confiança deve retornar o emoji correto."""
        assert _make_suggestion(confidence="alta").confidence_emoji == "🟢"
        assert _make_suggestion(confidence="media").confidence_emoji == "🟡"
        assert _make_suggestion(confidence="baixa").confidence_emoji == "🔴"

    def test_confidence_order_values(self):
        """alta < media < baixa em ordem numérica."""
        assert _make_suggestion(confidence="alta").confidence_order == 0
        assert _make_suggestion(confidence="media").confidence_order == 1
        assert _make_suggestion(confidence="baixa").confidence_order == 2


# ---------------------------------------------------------------------------
# SuggestionSet
# ---------------------------------------------------------------------------

class TestSuggestionSetTopSuggestion:
    def test_suggestion_set_top_suggestion(self):
        """top_suggestion deve retornar a sugestão de maior confiança."""
        suggestion_set = SuggestionSet(
            issue_id="abc12345",
            suggestions=[
                _make_suggestion(label="Opção C", confidence="baixa"),
                _make_suggestion(label="Opção A", confidence="alta"),
                _make_suggestion(label="Opção B", confidence="media"),
            ],
        )

        assert suggestion_set.top_suggestion is not None
        assert suggestion_set.top_suggestion.label == "Opção A"
        assert suggestion_set.top_suggestion.confidence == "alta"

    def test_top_suggestion_with_tie_returns_first_sorted(self):
        """Com empate de confiança, retorna o primeiro após sorted (estável)."""
        suggestion_set = SuggestionSet(
            issue_id="abc12345",
            suggestions=[
                _make_suggestion(label="Primeira alta", confidence="alta"),
                _make_suggestion(label="Segunda alta", confidence="alta"),
            ],
        )

        assert suggestion_set.top_suggestion.label == "Primeira alta"  # type: ignore[union-attr]

    def test_suggestion_set_get_by_index(self):
        """get_by_index deve retornar a sugestão correta pelo índice."""
        s0 = _make_suggestion(label="Zero")
        s1 = _make_suggestion(label="Um")
        suggestion_set = SuggestionSet(issue_id="abc12345", suggestions=[s0, s1])

        assert suggestion_set.get_by_index(0) == s0
        assert suggestion_set.get_by_index(1) == s1
        assert suggestion_set.get_by_index(2) is None
        assert suggestion_set.get_by_index(-1) is None

    def test_suggestion_set_has_suggestions_true(self):
        """has_suggestions deve ser True quando há sugestões."""
        suggestion_set = SuggestionSet(
            issue_id="abc12345",
            suggestions=[_make_suggestion()],
        )

        assert suggestion_set.has_suggestions is True


class TestSuggestionSetEmpty:
    def test_suggestion_set_empty(self):
        """SuggestionSet vazio deve ter has_suggestions False e top_suggestion None."""
        suggestion_set = SuggestionSet(issue_id="abc12345")

        assert suggestion_set.has_suggestions is False
        assert suggestion_set.top_suggestion is None

    def test_suggestion_set_with_error(self):
        """Deve aceitar campo error sem sugestões."""
        suggestion_set = SuggestionSet(
            issue_id="abc12345",
            error="Timeout ao chamar Ollama",
        )

        assert suggestion_set.error == "Timeout ao chamar Ollama"
        assert suggestion_set.has_suggestions is False


# ---------------------------------------------------------------------------
# AuditEntry
# ---------------------------------------------------------------------------

class TestAuditEntryToCsvRow:
    def test_audit_entry_to_csv_row(self):
        """to_csv_row deve retornar dict com todas as chaves esperadas e valores string."""
        entry = _make_audit_entry(
            normative_ref="NBR 15575-4 Tab. C.2",
            session_id="sess-001",
        )
        row = entry.to_csv_row()

        expected_keys = {
            "timestamp", "session_id", "element_guid", "element_class",
            "action", "field", "old_value", "new_value", "decision",
            "confidence", "normative_ref", "source", "user",
        }
        assert set(row.keys()) == expected_keys
        assert all(isinstance(v, str) for v in row.values())
        assert row["normative_ref"] == "NBR 15575-4 Tab. C.2"
        assert row["session_id"] == "sess-001"
        assert row["decision"] == "accepted"

    def test_audit_entry_csv_row_none_fields_become_empty_string(self):
        """Campos None (normative_ref, session_id) devem virar string vazia no CSV."""
        entry = _make_audit_entry()
        row = entry.to_csv_row()

        assert row["normative_ref"] == ""
        assert row["session_id"] == ""

    def test_audit_entry_timestamp_is_iso_format(self):
        """timestamp no CSV deve estar em formato ISO 8601."""
        from datetime import datetime

        entry = _make_audit_entry()
        row = entry.to_csv_row()

        # Deve ser parseable como datetime ISO
        parsed = datetime.fromisoformat(row["timestamp"])
        assert isinstance(parsed, datetime)


# ---------------------------------------------------------------------------
# Helpers — DiagnosticReport / OperationalRule
# ---------------------------------------------------------------------------

def _make_report(issues: list[Issue] | None = None) -> DiagnosticReport:
    """Fábrica de DiagnosticReport com valores padrão."""
    return DiagnosticReport(
        model_name="Modelo Teste",
        model_path="/tmp/modelo.ifc",
        total_elements=50,
        total_spaces=5,
        total_walls=20,
        total_doors=8,
        total_windows=10,
        total_slabs=4,
        issues=issues or [],
    )


def _make_rule(**kwargs) -> OperationalRule:
    """Fábrica de OperationalRule com valores padrão."""
    defaults = dict(
        source_spec="NBR 15575",
        filter_entity="IfcWall",
        check_pset="Pset_WallCommon",
        check_property="ThermalTransmittance",
        check_type="is_numeric",
    )
    defaults.update(kwargs)
    return OperationalRule(**defaults)


# ---------------------------------------------------------------------------
# DiagnosticReport
# ---------------------------------------------------------------------------

class TestDiagnosticReportIssuesByType:
    def test_diagnostic_report_issues_by_type(self):
        """issues_by_type deve contar corretamente cada tipo de issue."""
        issues = [
            _make_issue(issue_type="space_unnamed"),
            _make_issue(issue_type="space_unnamed"),
            _make_issue(issue_type="pset_missing"),
        ]
        report = _make_report(issues=issues)

        assert report.issues_by_type["space_unnamed"] == 2
        assert report.issues_by_type["pset_missing"] == 1
        assert "relation_broken" not in report.issues_by_type

    def test_issues_by_severity(self):
        """issues_by_severity deve contar corretamente cada nível de severidade."""
        issues = [
            _make_issue(severity="high"),
            _make_issue(severity="high"),
            _make_issue(severity="low"),
        ]
        report = _make_report(issues=issues)

        assert report.issues_by_severity["high"] == 2
        assert report.issues_by_severity["low"] == 1
        assert "medium" not in report.issues_by_severity

    def test_total_issues(self):
        """total_issues deve refletir o tamanho da lista."""
        report = _make_report(issues=[_make_issue(), _make_issue(), _make_issue()])

        assert report.total_issues == 3

    def test_total_issues_empty(self):
        """total_issues deve ser 0 quando não há issues."""
        assert _make_report().total_issues == 0


class TestDiagnosticReportSortedIssues:
    def test_diagnostic_report_sorted_issues(self):
        """sorted_issues deve ordenar com high primeiro e low por último."""
        issues = [
            _make_issue(severity="low"),
            _make_issue(severity="high"),
            _make_issue(severity="medium"),
            _make_issue(severity="high"),
        ]
        report = _make_report(issues=issues)
        severities = [i.severity for i in report.sorted_issues]

        assert severities[0] == "high"
        assert severities[1] == "high"
        assert severities[2] == "medium"
        assert severities[3] == "low"

    def test_sorted_issues_does_not_mutate_original(self):
        """sorted_issues não deve alterar a ordem da lista original."""
        issues = [_make_issue(severity="low"), _make_issue(severity="high")]
        report = _make_report(issues=issues)
        _ = report.sorted_issues

        assert report.issues[0].severity == "low"  # ordem original preservada


class TestDiagnosticReportFilterIssues:
    def test_diagnostic_report_filter_issues(self):
        """filter_issues deve retornar apenas issues que correspondem aos filtros."""
        issues = [
            _make_issue(issue_type="pset_missing", severity="high"),
            _make_issue(issue_type="space_unnamed", severity="low"),
            _make_issue(issue_type="pset_missing", severity="medium"),
        ]
        report = _make_report(issues=issues)

        result = report.filter_issues(issue_type="pset_missing")
        assert len(result) == 2
        assert all(i.issue_type == "pset_missing" for i in result)

    def test_filter_by_severity(self):
        """filter_issues deve filtrar por severidade."""
        issues = [
            _make_issue(severity="high"),
            _make_issue(severity="low"),
            _make_issue(severity="high"),
        ]
        report = _make_report(issues=issues)

        result = report.filter_issues(severity="high")
        assert len(result) == 2

    def test_filter_by_status(self):
        """filter_issues deve filtrar por status."""
        i1 = _make_issue()
        i2 = _make_issue()
        i2.resolve(value=None, decision="rejected")
        report = _make_report(issues=[i1, i2])

        pending = report.filter_issues(status="pending")
        rejected = report.filter_issues(status="rejected")

        assert len(pending) == 1
        assert len(rejected) == 1

    def test_filter_combined(self):
        """filter_issues deve suportar múltiplos filtros simultâneos."""
        issues = [
            _make_issue(issue_type="pset_missing", severity="high"),
            _make_issue(issue_type="pset_missing", severity="low"),
            _make_issue(issue_type="space_unnamed", severity="high"),
        ]
        report = _make_report(issues=issues)

        result = report.filter_issues(issue_type="pset_missing", severity="high")
        assert len(result) == 1

    def test_filter_no_match_returns_empty(self):
        """filter_issues deve retornar lista vazia quando nada corresponde."""
        report = _make_report(issues=[_make_issue(issue_type="space_unnamed")])

        result = report.filter_issues(issue_type="relation_broken")
        assert result == []


# ---------------------------------------------------------------------------
# OperationalRule
# ---------------------------------------------------------------------------

class TestOperationalRuleDescribe:
    def test_operational_rule_describe(self):
        """describe deve gerar texto legível com entidade, condições e propriedade."""
        rule = _make_rule(
            filter_entity="IfcWall",
            filter_conditions=[
                {"pset": "Pset_WallCommon", "prop": "IsExternal", "operator": "=", "value": "True"}
            ],
            check_pset="Pset_WallCommon",
            check_property="ThermalTransmittance",
            check_type="is_numeric",
        )
        description = rule.describe()

        assert "IfcWall" in description
        assert "Pset_WallCommon.IsExternal = True" in description
        assert "ThermalTransmittance" in description
        assert "is_numeric" in description

    def test_operational_rule_describe_no_conditions(self):
        """describe sem filter_conditions não deve conter cláusula WHERE."""
        rule = _make_rule(filter_conditions=[])
        description = rule.describe()

        assert "WHERE" not in description
        assert "IfcWall" in description

    def test_operational_rule_auto_generates_id(self):
        """id deve ser gerado automaticamente com 8 caracteres."""
        rule = _make_rule()

        assert len(rule.id) == 8

    def test_operational_rule_describe_multiple_conditions(self):
        """describe com múltiplas condições deve separá-las com AND."""
        rule = _make_rule(
            filter_conditions=[
                {"pset": "Pset_WallCommon", "prop": "IsExternal", "operator": "=", "value": "True"},
                {"pset": "Pset_WallCommon", "prop": "IsLoadBearing", "operator": "=", "value": "True"},
            ],
        )
        description = rule.describe()

        assert " AND " in description


# ---------------------------------------------------------------------------
# ReadinessProfile / ReadinessScore / ProfileRegistry
# ---------------------------------------------------------------------------

def _make_profile(**kwargs) -> ReadinessProfile:
    """Fábrica de ReadinessProfile com valores padrão para os testes."""
    defaults = dict(
        id="budget_readiness",
        name="Orçamento-readiness",
        description="Verifica se o modelo contém dados suficientes para orçamento.",
        ids_filename="budget.ids",
        required_extractors=["quantities", "materials"],
        rule_pack="budget_rules",
        prompt_pack="budget_prompts",
        issue_types=["pset_missing"],
        blocking_severities=["high"],
    )
    defaults.update(kwargs)
    return ReadinessProfile(**defaults)


class TestReadinessProfileCreation:
    def test_readiness_profile_creation(self):
        """Deve criar ReadinessProfile com todos os campos corretamente."""
        profile = _make_profile()

        assert profile.id == "budget_readiness"
        assert profile.name == "Orçamento-readiness"
        assert profile.version == "1.0"
        assert profile.ids_filename == "budget.ids"
        assert profile.required_extractors == ["quantities", "materials"]
        assert profile.rule_pack == "budget_rules"
        assert profile.prompt_pack == "budget_prompts"
        assert profile.issue_types == ["pset_missing"]
        assert profile.blocking_severities == ["high"]


class TestReadinessProfileIsCustom:
    def test_profile_is_custom_false_when_ids_filename_set(self):
        """is_custom deve ser False quando ids_filename está definido."""
        profile = _make_profile(ids_filename="budget.ids")

        assert profile.is_custom is False

    def test_profile_is_custom_true_when_ids_filename_none(self):
        """is_custom deve ser True quando ids_filename é None."""
        profile = _make_profile(ids_filename=None)

        assert profile.is_custom is True


class TestReadinessScoreComputeReady:
    def test_readiness_score_compute_ready(self):
        """Score deve ser 'ready' quando sem blocking issues e >= 90% passed."""
        profile = _make_profile(blocking_severities=["high"])
        issues: list[Issue] = []
        score = ReadinessScore.compute(profile=profile, issues=issues, total_checks=10)

        assert score.profile_id == "budget_readiness"
        assert score.profile_name == "Orçamento-readiness"
        assert score.total_checks == 10
        assert score.passed == 10
        assert score.failed == 0
        assert score.blocking_issues == 0
        assert score.score_percent == 100.0
        assert score.status == "ready"


class TestReadinessScoreComputeNotReady:
    def test_readiness_score_compute_not_ready(self):
        """Score deve ser 'not_ready' quando score_percent < 50%."""
        profile = _make_profile(blocking_severities=["high"])
        issues = [
            _make_issue(severity="high"),
            _make_issue(severity="high"),
            _make_issue(severity="high"),
            _make_issue(severity="medium"),
            _make_issue(severity="low"),
            _make_issue(severity="low"),
        ]  # 6 issues em 10 checks → 40% passed
        score = ReadinessScore.compute(profile=profile, issues=issues, total_checks=10)

        assert score.failed == 6
        assert score.passed == 4
        assert score.score_percent == 40.0
        assert score.blocking_issues == 3
        assert score.status == "not_ready"


class TestReadinessScoreComputePartial:
    def test_readiness_score_compute_partial(self):
        """Score deve ser 'partially_ready' quando 50% <= score_percent < 90%."""
        profile = _make_profile(blocking_severities=["high"])
        issues = [
            _make_issue(severity="medium"),
            _make_issue(severity="low"),
            _make_issue(severity="low"),
        ]  # 3 issues em 10 checks → 70% passed, 0 blocking
        score = ReadinessScore.compute(profile=profile, issues=issues, total_checks=10)

        assert score.passed == 7
        assert score.failed == 3
        assert score.blocking_issues == 0
        assert score.score_percent == 70.0
        assert score.status == "partially_ready"


class TestProfileRegistry:
    def test_profile_registry_register_and_get(self):
        """register deve adicionar perfil e get deve recuperá-lo pelo id."""
        registry = ProfileRegistry()
        profile = _make_profile()

        registry.register(profile)

        retrieved = registry.get("budget_readiness")
        assert retrieved is not None
        assert retrieved.id == "budget_readiness"
        assert retrieved.name == "Orçamento-readiness"

    def test_profile_registry_get_missing_returns_none(self):
        """get deve retornar None para ids não registrados."""
        registry = ProfileRegistry()

        assert registry.get("nonexistent") is None

    def test_profile_registry_list_profiles(self):
        """list_profiles deve retornar todos os perfis registrados."""
        registry = ProfileRegistry()
        p1 = _make_profile(id="budget_readiness", name="Budget")
        p2 = _make_profile(id="energy_readiness", name="Energy")

        registry.register(p1)
        registry.register(p2)

        profiles = registry.list_profiles()
        assert len(profiles) == 2
        ids = {p.id for p in profiles}
        assert ids == {"budget_readiness", "energy_readiness"}
