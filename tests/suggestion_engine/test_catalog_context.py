"""Contexto de evidência por campo: seletores literais, resolução observada e referências."""

import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

pytest.importorskip("ifctester", reason="extra e3 não instalado (ifctester==0.8.5)")

from src.ifc_analyzer.observations import IfcObservationReader
from src.suggestion_engine.catalog_context import build_field_context
from src.suggestion_engine.catalog_contracts import RECIPE, FieldEvidenceContext
from src.suggestion_engine.catalog_evidence import assess_evidence
from tests.suggestion_engine import m3_helpers as m
from tests.validation import ifc_builders as ib


def _legacy():
    model = ib.model()
    m.slab(model, ("SYN_Legado", "Metodo", "A", "IfcLabel"))
    return model


def test_selectors_use_ids_target_binding_and_only_approved_resolution_aliases(
    tmp_path: Path,
) -> None:
    aliases = (
        m.alias(),
        m.alias(
            "urn:uuid:00000000-0000-4000-8000-00000000e311",
            "MetodoAntigo",
            sets=("SYN_Legado", "SYN_Velho"),
        ),
        m.alias(
            "urn:uuid:00000000-0000-4000-8000-00000000e312",
            "SemConjunto",
            sets=None,
            entity_classes=("IfcSlab",),
        ),
        m.alias(
            "urn:uuid:00000000-0000-4000-8000-00000000e313", "Busca", sets=None, purpose="search"
        ),
        m.alias(
            "urn:uuid:00000000-0000-4000-8000-00000000e314", "Parede", entity_classes=("IfcWall",)
        ),
        m.alias(
            "urn:uuid:00000000-0000-4000-8000-00000000e315",
            "Traducao",
            sets=None,
            purpose="label_translation",
        ),
    )
    c = m.case(tmp_path, m.content(aliases=aliases), _legacy())
    context = build_field_context(c.snapshot, c.row(), c.reader, c.observations, RECIPE)

    assert context.search_plan is not None
    assert [(s.set_name, s.field_name) for s in context.search_plan.selectors] == [
        ("SYN_Conjunto", "SYN_Metodo"),
        ("SYN_Conjunto", "SemConjunto"),
        ("SYN_Legado", "Metodo"),
        ("SYN_Legado", "MetodoAntigo"),
        ("SYN_Velho", "MetodoAntigo"),
    ]
    target = context.search_plan.selectors[0]
    assert any(r.startswith("ids:") for r in target.reasons)
    assert f"binding:{m.f.BINDING_ID}" in target.reasons
    assert context.search_plan.admitted_scopes == ("occurrence", "type")
    assert context.origin == "local_snapshot"


def test_selector_limit_refuses_without_truncating(tmp_path: Path) -> None:
    many = tuple(
        m.alias(f"urn:uuid:00000000-0000-4000-8000-0000000{0x50000 + n:05x}", f"Termo{n}")
        for n in range(64)
    )
    c = m.case(tmp_path, m.content(aliases=many), _legacy())
    context = build_field_context(c.snapshot, c.row(), c.reader, c.observations, RECIPE)
    assert context.search_plan is None
    assert context.unavailable_reason == "context_limit_exceeded"


def test_observed_path_resolution_preserves_alias_and_request(tmp_path: Path) -> None:
    c = m.case(tmp_path, m.content(), _legacy())
    context = build_field_context(c.snapshot, c.row(), c.reader, c.observations, RECIPE)
    (resolved,) = context.resolutions
    assert resolved.admissible
    assert resolved.resolution.status == "approved_mapping"
    assert (resolved.request.set_name, resolved.request.field_name) == ("SYN_Legado", "Metodo")
    assert resolved.resolution.binding_id == m.f.BINDING_ID


def test_context_is_content_hashed_and_rejects_forged_payloads(tmp_path: Path) -> None:
    c = m.case(tmp_path, m.content(), _legacy())
    context = build_field_context(c.snapshot, c.row(), c.reader, c.observations, RECIPE)
    again = build_field_context(c.snapshot, c.row(), c.reader, c.observations, RECIPE)
    data = context.model_dump(mode="json")

    assert context.context_sha256 == again.context_sha256
    assert FieldEvidenceContext.model_validate(data) == context
    data["field"]["target_field_name"] = "Outro"
    with pytest.raises(ValidationError):
        FieldEvidenceContext.model_validate(data)


def test_foreign_observation_reader_or_row_is_refused(tmp_path: Path) -> None:
    c = m.case(tmp_path, m.content(), _legacy())
    other = IfcObservationReader(c.session, uuid.uuid4())
    context = build_field_context(c.snapshot, c.row(), c.reader, other, RECIPE)
    assessment = assess_evidence(context, c.bundle)
    assert (assessment.status, assessment.reasons[0]) == ("unavailable", "foreign_reference")

    other_case = m.case(tmp_path / "outro", m.content(), _legacy())
    foreign_row = other_case.row()
    context = build_field_context(c.snapshot, foreign_row, c.reader, c.observations, RECIPE)
    assessment = assess_evidence(context, c.bundle)
    assert (assessment.status, assessment.reasons[0]) == ("unavailable", "foreign_reference")


def _occurrence_and_type():
    model = ib.model()
    slab = m.slab(model, ("SYN_Legado", "Metodo", "A", "IfcLabel"))
    slab_type = ib.typed(model, slab, "IfcSlabType")
    ib.pset(model, slab_type, "SYN_Legado", [ib.single(model, "Metodo", "IfcLabel", "A")])
    return model


def test_observation_limit_is_the_total_per_field_across_channels(tmp_path: Path) -> None:
    """E3-07: 1 de ocorrência + 1 de tipo excedem a receita com 1 observação por campo."""
    from src.suggestion_engine.catalog_contracts import ContextRecipe, RecipeLimits

    c = m.case(tmp_path, m.content(), _occurrence_and_type())
    exact = ContextRecipe(limits=RecipeLimits(max_observations=2))
    within = build_field_context(c.snapshot, c.row(), c.reader, c.observations, exact)
    assert within.unavailable_reason is None
    assert within.search_report is not None
    assert len(within.search_report.observations) == 2

    over = ContextRecipe(limits=RecipeLimits(max_observations=1))
    refused = build_field_context(c.snapshot, c.row(), c.reader, c.observations, over)
    assert refused.unavailable_reason == "context_limit_exceeded"
    assert refused.search_report is None
    assert assess_evidence(refused, c.bundle).reasons[0] == "context_limit_exceeded"

    reader_limited = IfcObservationReader(
        c.session, c.snapshot.identity.analysis_id, max_observations=1
    )
    limited = build_field_context(c.snapshot, c.row(), c.reader, reader_limited, exact)
    assert limited.search_report is not None
    assert {cov.status for cov in limited.search_report.coverage} == {"unsupported"}
    assert assess_evidence(limited, c.bundle).reasons[0] == "context_limit_exceeded"


def test_recipe_is_derived_from_the_frozen_execution_limits(tmp_path: Path) -> None:
    """E3-07: a receita executada é a dos limites congelados na identidade da análise."""
    from src.suggestion_engine.catalog_contracts import recipe_for
    from src.validation.analysis_identity import ExecutionLimits

    limits = ExecutionLimits(
        max_selectors_per_field=3, max_observations_per_field=7, max_context_bytes=9999
    )
    recipe = recipe_for(limits)
    assert recipe.limits.model_dump() == {
        "max_selectors": 3,
        "max_observations": 7,
        "max_context_bytes": 9999,
    }
    assert recipe_for(ExecutionLimits()) == RECIPE
