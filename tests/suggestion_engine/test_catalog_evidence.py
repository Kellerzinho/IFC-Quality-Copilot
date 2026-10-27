"""Avaliação de evidência (A18): completude, ausência, nulo, vazio, parcial, erro e conflito."""

from pathlib import Path

import pytest

pytest.importorskip("ifctester", reason="extra e3 não instalado (ifctester==0.8.5)")

from src.ifc_analyzer.observations import SearchReport, SelectorCoverage
from src.operations.contracts import canonical_sha256
from src.suggestion_engine.catalog_context import build_field_context
from src.suggestion_engine.catalog_contracts import RECIPE, EvidenceAssessment
from src.suggestion_engine.catalog_evidence import assess_evidence
from src.suggestion_engine.catalog_operations import execute_catalog_operation
from tests.suggestion_engine import m3_helpers as m
from tests.validation import ifc_builders as ib


def _assess(tmp_path: Path, model, catalog=None) -> EvidenceAssessment:
    c = m.case(tmp_path, catalog or m.content(), model)
    context = build_field_context(c.snapshot, c.row(), c.reader, c.observations, RECIPE)
    return assess_evidence(context, c.bundle)


def _model(*sets: tuple[str, str, object, str]):
    model = ib.model()
    m.slab(model, *sets)
    return model


def test_complete_search_without_value_is_insufficient_and_applies_on_missing(
    tmp_path: Path,
) -> None:
    abstain = _assess(tmp_path / "a", _model())
    human = _assess(tmp_path / "b", _model(), m.content(on_missing="request_human"))

    assert (abstain.status, abstain.reasons[0], abstain.action) == (
        "insufficient",
        "no_evidence",
        "none",
    )
    assert (human.status, human.action) == ("insufficient", "request_human")


@pytest.mark.parametrize(
    ("value", "ifc_type", "reason"),
    [(None, None, "null_value"), ("", "IfcLabel", "empty_value")],
)
def test_null_and_empty_are_distinct_insufficiencies(
    tmp_path: Path, value: object, ifc_type: str | None, reason: str
) -> None:
    assessment = _assess(tmp_path, _model(("SYN_Legado", "Metodo", value, ifc_type)))  # type: ignore[arg-type]
    assert (assessment.status, assessment.reasons[0]) == ("insufficient", reason)


class _CoverageReader:
    """Dublê que só altera a cobertura do relatório real (injeção de falha de busca)."""

    def __init__(self, real: object, status: str) -> None:
        self.real = real
        self.status = status

    def read(self, plan):
        report = self.real.read(plan)  # type: ignore[attr-defined]
        coverage = [
            {**cov.model_dump(mode="json"), "status": self.status, "reason": "injetado"}
            if cov.scope == "type"
            else cov.model_dump(mode="json")
            for cov in report.coverage
        ]
        body = {**report.model_dump(mode="json", exclude={"report_sha256"}), "coverage": coverage}
        return SearchReport.model_validate({**body, "report_sha256": canonical_sha256(body)})


def test_multiple_types_are_refused_formally_before_m3(tmp_path: Path) -> None:
    model = ib.model()
    element = m.slab(model)
    ib.typed(model, element, "IfcSlabType")
    ib.typed(model, element, "IfcSlabType")
    assessment = _assess(tmp_path, model, m.content(on_missing="request_human"))
    assert (assessment.status, assessment.reasons[0]) == ("unavailable", "formal_not_verified")


@pytest.mark.parametrize("status", ["partial", "not_searched"])
def test_incomplete_search_is_not_absence_and_skips_on_missing(tmp_path: Path, status: str) -> None:
    c = m.case(tmp_path, m.content(on_missing="request_human"), _model())
    reader = _CoverageReader(c.observations, status)
    context = build_field_context(c.snapshot, c.row(), c.reader, reader, RECIPE)
    assessment = assess_evidence(context, c.bundle)
    assert (assessment.status, assessment.reasons[0], assessment.action) == (
        "partial",
        "incomplete_search",
        "none",
    )


def test_conflict_applies_on_conflict_and_keeps_all_sources(tmp_path: Path) -> None:
    model = ib.model()
    element = m.slab(model, ("SYN_Legado", "Metodo", "A", "IfcLabel"))
    slab_type = ib.typed(model, element, "IfcSlabType")
    ib.pset(model, slab_type, "SYN_Legado", [ib.single(model, "Metodo", "IfcLabel", "B")])
    assessment = _assess(tmp_path, model, m.content(on_conflict="request_review"))

    assert (assessment.status, assessment.reasons[0], assessment.action) == (
        "conflicting",
        "evidence_conflict",
        "request_review",
    )
    assert len(assessment.admissible_observation_ids) == 2
    assert assessment.conflicts


def test_duplicated_source_is_ambiguous_not_first_choice(tmp_path: Path) -> None:
    model = ib.model()
    m.slab(
        model, ("SYN_Legado", "Metodo", "A", "IfcLabel"), ("SYN_Legado", "Metodo", "A", "IfcLabel")
    )
    assessment = _assess(tmp_path, model)
    assert (assessment.status, assessment.reasons[0]) == (
        "conflicting",
        "duplicate_source_ambiguity",
    )


def test_search_error_is_technical_failure(tmp_path: Path) -> None:
    c = m.case(tmp_path, m.content(), _model(("SYN_Legado", "Metodo", "A", "IfcLabel")))

    class FailingReader:
        """Dublê que só injeta cobertura de erro sobre o leitor real."""

        def read(self, plan):
            real = c.observations.read(plan)
            coverage = tuple(
                SelectorCoverage(
                    **{**cov.model_dump(), "status": "error", "reason": "falha simulada"}
                )
                for cov in real.coverage
            )
            body = {
                **real.model_dump(mode="json", exclude={"report_sha256"}),
                "coverage": [cov.model_dump(mode="json") for cov in coverage],
            }
            return SearchReport.model_validate({**body, "report_sha256": canonical_sha256(body)})

    context = build_field_context(c.snapshot, c.row(), c.reader, FailingReader(), RECIPE)
    assessment = assess_evidence(context, c.bundle)
    result = execute_catalog_operation(context, assessment, c.bundle)
    assert (assessment.status, assessment.reasons[0]) == ("unavailable", "search_error")
    assert (result.status, result.reason) == ("failed", "search_error")


def test_sufficient_evidence_names_policy_and_exact_operation(tmp_path: Path) -> None:
    assessment = _assess(tmp_path, _model(("SYN_Legado", "Metodo", "A", "IfcLabel")))
    assert assessment.status == "sufficient"
    assert (assessment.policy_id, assessment.operation_id, assessment.operation_version) == (
        m.POLICY,
        "recover_exact_property",
        "1.0.0",
    )
    assert assessment.reasons == ()


def test_technical_error_outranks_capability_and_keeps_secondary_reasons(tmp_path: Path) -> None:
    """E3-09: erro de busca + precondição desconhecida → técnico primeiro, ambos preservados."""
    c = m.case(
        tmp_path,
        m.content(preconditions=("unknown",)),
        _model(("SYN_Legado", "Metodo", "A", "IfcLabel")),
    )
    context = build_field_context(
        c.snapshot, c.row(), c.reader, _CoverageReader(c.observations, "error"), RECIPE
    )
    assessment = assess_evidence(context, c.bundle)
    result = execute_catalog_operation(context, assessment, c.bundle)
    assert assessment.status == "unavailable"
    assert assessment.reasons == ("search_error", "unsupported_precondition")
    assert (result.status, result.reason) == ("failed", "search_error")
    assert result.reasons == ("search_error", "unsupported_precondition")


def test_combined_states_follow_the_single_priority_order(tmp_path: Path) -> None:
    """E3-09: conflito + busca parcial → conflito primeiro e incompletude preservada."""
    model = ib.model()
    slab = m.slab(model, ("SYN_Legado", "Metodo", "A", "IfcLabel"))
    slab_type = ib.typed(model, slab, "IfcSlabType")
    ib.pset(model, slab_type, "SYN_Legado", [ib.single(model, "Metodo", "IfcLabel", "B")])
    c = m.case(tmp_path, m.content(on_conflict="request_review"), model)
    context = build_field_context(
        c.snapshot, c.row(), c.reader, _CoverageReader(c.observations, "partial"), RECIPE
    )
    assessment = assess_evidence(context, c.bundle)
    assert assessment.status == "conflicting"
    assert assessment.reasons == ("evidence_conflict", "incomplete_search")
    assert assessment.action == "request_review"
