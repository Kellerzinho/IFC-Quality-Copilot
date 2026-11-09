"""Amostra Daiane da E1 em RASCUNHO (M1-04, amostra).

Dados REAIS da fonte (camada fiel do Apêndice A via matriz M3) e julgamentos
semânticos PROPOSTOS, pendentes da revisão de Felipe: nada aqui está aprovado. Os
testes conferem que cada proposta se apoia nos literais de cada uso e que a amostra
não vira release.
"""

import json
from pathlib import Path

import pytest

from src.domain_catalog.content import CatalogContent, validate_content
from src.domain_catalog.contracts import BindingRequest, PredefinedTypeContext, ResolutionResult
from src.domain_catalog.drafts import DraftBaseMismatchError, DraftFormatError
from src.domain_catalog.errors import CatalogValidationError
from src.domain_catalog.importers.daiane import (
    E1_DRAFT_PATH,
    MATRIX_PATH,
    DaianeImport,
    coverage_rows,
    import_appendix_a,
    load_daiane_draft,
    load_matrix,
)
from src.domain_catalog.models import IFCBinding, SourceAssertion
from src.domain_catalog.operations import DEFAULT_OPERATION_REGISTRY
from src.domain_catalog.resolver import resolve_binding
from tests.domain_catalog import factories as f


@pytest.fixture(scope="module")
def imported() -> DaianeImport:
    return import_appendix_a(load_matrix(MATRIX_PATH))


@pytest.fixture(scope="module")
def draft(imported: DaianeImport) -> CatalogContent:
    return load_daiane_draft(E1_DRAFT_PATH, imported)


@pytest.fixture(scope="module")
def source(imported: DaianeImport) -> dict[str, SourceAssertion]:
    return {assertion.id: assertion for assertion in imported.assertions}


def _uses(draft: CatalogContent, field: str) -> list[IFCBinding]:
    return sorted(
        (b for b in draft.bindings if b.field_name == field),
        key=lambda b: b.source_assertion_ids,
    )


def _codes(draft: CatalogContent, value_set_id: str | None) -> set[object]:
    value_set = next(vs for vs in draft.value_sets if vs.id == value_set_id)
    return {value.code for value in value_set.values}


def _resolve(draft: CatalogContent, **request: object) -> ResolutionResult:
    data: dict[str, object] = {"ifc_schema": "IFC4", "facet": "property"}
    data.update(request)
    return resolve_binding(draft, BindingRequest.model_validate(data))


def _pt(value: str, origin: str = "occurrence") -> PredefinedTypeContext:
    """PredefinedType efetivo, como o M2 informaria (contexto sintético sobre dados reais)."""
    return PredefinedTypeContext.determined(value, origin=origin)  # type: ignore[arg-type]


@pytest.mark.external_data
def test_draft_is_valid_for_curation_and_never_publishable(draft: CatalogContent) -> None:
    validate_content(draft, for_release=False)

    with pytest.raises(CatalogValidationError) as exc:
        f.build_synthetic_release(draft)

    assert {issue.code for issue in exc.value.issues} == {"lifecycle_not_publishable"}
    proposals = (
        *draft.concepts,
        *draft.value_sets,
        *draft.applicability_rules,
        *draft.evidence_policies,
        *draft.bindings,
        *draft.profile_memberships,
    )
    assert {entity.lifecycle for entity in proposals} == {"draft"}


@pytest.mark.external_data
def test_source_backed_proposals_cite_real_appendix_a_rows(draft: CatalogContent) -> None:
    # Revisão E1-11: o alcance é o das propostas apoiadas em fonte, não "toda proposta".
    proposals = [
        *draft.concepts,
        *draft.applicability_rules,
        *draft.bindings,
        *draft.value_sets,
        *draft.profile_memberships,
        *draft.reconciliation_decisions,
    ]

    for entity in proposals:
        assert entity.source_assertion_ids, entity.id
        assert all(a.startswith("dai2025:A") for a in entity.source_assertion_ids)
    assert {a.source_artifact_id for a in draft.source_assertions} == {"dai2025:dissertacao"}


@pytest.mark.external_data
def test_evidence_policies_are_project_proposals_without_source_rows(
    draft: CatalogContent,
) -> None:
    # As duas políticas não citam assertiva: são propostas de projeto, sem citação inventada.
    assert len(draft.evidence_policies) == 2
    assert all(policy.source_assertion_ids == () for policy in draft.evidence_policies)


@pytest.mark.external_data
def test_sample_counts_are_35_draft_entities_and_one_pending_decision(
    draft: CatalogContent,
) -> None:
    with_lifecycle = [e for _, e in draft.iter_entities() if hasattr(e, "lifecycle")]

    assert len(with_lifecycle) == 35
    assert {e.lifecycle for e in with_lifecycle} == {"draft"}  # type: ignore[attr-defined]
    assert [d.status for d in draft.reconciliation_decisions] == ["pending"]


@pytest.mark.external_data
def test_bindings_keep_the_source_literals(
    draft: CatalogContent, source: dict[str, SourceAssertion]
) -> None:
    for binding in draft.bindings:
        (assertion_id,) = binding.source_assertion_ids
        row = source[assertion_id]
        assert binding.set_name == row.set_literal == "EB_Orçamento"
        assert binding.field_name == row.target_identifier_literal
        assert binding.declared_schemas == ("IFC4",)
        assert binding.write_enabled is False


@pytest.mark.external_data
def test_tipo_concretagem_is_one_concept_whose_domain_matches_each_use(
    draft: CatalogContent, source: dict[str, SourceAssertion]
) -> None:
    uses = _uses(draft, "Tipo_Concretagem")
    (concept_id,) = {b.concept_id for b in uses}
    concept = next(c for c in draft.concepts if c.id == concept_id)

    assert [b.source_assertion_ids for b in uses] == [
        ("dai2025:A7-010",),
        ("dai2025:A8-008",),
        ("dai2025:A9-009",),
    ]
    for binding in uses:
        row = source[binding.source_assertion_ids[0]]
        assert _codes(draft, concept.value_set_id) == set(row.domain_literal)
        assert row.datatype_literal == "Texto (IfcLabel)"
        assert binding.ifc_type == "IfcLabel"


@pytest.mark.external_data
def test_tipo_revestimento_uses_are_distinct_concepts_with_their_own_domains(
    draft: CatalogContent, source: dict[str, SourceAssertion]
) -> None:
    uses = _uses(draft, "Tipo_Revestimento")
    concepts = {c.id: c for c in draft.concepts}

    assert [b.source_assertion_ids[0] for b in uses] == [
        "dai2025:A2-013",
        "dai2025:A5-009",
        "dai2025:A6-009",
    ]
    assert len({b.concept_id for b in uses}) == 3
    for binding in uses:
        row = source[binding.source_assertion_ids[0]]
        value_set_id = concepts[binding.concept_id].value_set_id
        assert _codes(draft, value_set_id) == set(row.domain_literal)


@pytest.mark.external_data
def test_no_alias_joins_the_three_revestimento_concepts_by_name(draft: CatalogContent) -> None:
    # Decisão de 13/10: sem alias global que una porta, piso e parede pelo nome.
    revestimento = {b.id for b in _uses(draft, "Tipo_Revestimento")} | {
        b.concept_id for b in _uses(draft, "Tipo_Revestimento")
    }

    assert not [
        alias
        for alias in draft.aliases
        if {alias.target_binding_id, alias.target_concept_id} & revestimento
    ]


@pytest.mark.external_data
def test_area_forma_stays_pending_with_write_disabled(
    draft: CatalogContent, source: dict[str, SourceAssertion]
) -> None:
    uses = _uses(draft, "Area_Forma")
    (decision,) = draft.reconciliation_decisions

    assert len(uses) == 3
    for binding in uses:
        row = source[binding.source_assertion_ids[0]]
        # Decisão B de Felipe (14/10): portador declarado como não determinado.
        assert binding.carrier_kind == "property_or_quantity"
        assert binding.carrier_status == "pending_reconciliation"
        assert (binding.ifc_type, binding.write_enabled) == (None, False)
        assert binding.source_original_type == row.datatype_literal == "Área (IfcQuantityArea)"
    assert decision.status == "pending"
    assert set(decision.affected_binding_ids) == {b.id for b in uses}
    assert set(decision.source_assertion_ids) == {
        "dai2025:A7-013",
        "dai2025:A8-011",
        "dai2025:A9-012",
    }


@pytest.mark.external_data
def test_area_forma_decision_keeps_both_carriers_open_until_evidence(
    draft: CatalogContent,
) -> None:
    # Revisão E1-08: IFCAREAMEASURE é também o tipo de IfcQuantityArea.AreaValue; o
    # registro pendente apresenta as duas formas de portador, sem eleger nenhuma.
    (decision,) = draft.reconciliation_decisions
    text = f"{decision.summary} {decision.proposal}"

    assert (decision.status, decision.justification) == ("pending", None)
    assert "IfcQuantityArea.AreaValue" in decision.summary
    for carrier in ("IfcElementQuantity", "IfcPropertySet"):
        assert carrier in text, carrier


@pytest.mark.external_data
def test_resolution_reuses_the_concept_only_with_class_context(draft: CatalogContent) -> None:
    column = _resolve(
        draft,
        set_name="EB_Orçamento",
        field_name="Tipo_Concretagem",
        entity="IfcColumn",
        predefined_type=_pt("COLUMN"),
    )
    unknown = _resolve(draft, set_name="EB_Orçamento", field_name="Tipo_Concretagem")

    assert column.status == "exact"
    assert any("não operacional" in limitation for limitation in column.limitations)
    assert unknown.status == "ambiguous"
    assert len(unknown.candidates) == 3
    assert len({c.concept_id for c in unknown.candidates}) == 1


@pytest.mark.external_data
def test_tipo_revestimento_depends_on_class_and_predefined_type(draft: CatalogContent) -> None:
    def resolve(**context: object) -> ResolutionResult:
        return _resolve(draft, set_name="EB_Orçamento", field_name="Tipo_Revestimento", **context)

    nothing = resolve()
    door = resolve(entity="IfcDoor", predefined_type=_pt("DOOR"))
    floor = resolve(entity="IfcCovering", predefined_type=_pt("FLOORING"))
    covering = resolve(entity="IfcCovering")

    assert nothing.status == "ambiguous"
    assert len({c.concept_id for c in nothing.candidates}) == 3
    assert door.status == floor.status == "exact"
    assert door.concept_id != floor.concept_id
    assert covering.status == "ambiguous"


# --- Decisão de 13/10 sobre aplicabilidade, exercitada na amostra real ----------------


def _covering(draft: CatalogContent, predefined: PredefinedTypeContext) -> ResolutionResult:
    return _resolve(
        draft,
        set_name="EB_Orçamento",
        field_name="Tipo_Revestimento",
        entity="IfcCovering",
        predefined_type=predefined,
    )


@pytest.mark.external_data
def test_flooring_declared_by_the_type_object_selects_the_floor_use(
    draft: CatalogContent,
) -> None:
    result = _covering(draft, _pt("FLOORING", origin="type"))
    concepts = {c.id: c for c in draft.concepts}

    assert result.status == "exact"
    assert concepts[str(result.concept_id)].code == "EBO.TIPO_REVESTIMENTO_PISO"


@pytest.mark.external_data
def test_covering_without_consulting_the_type_object_is_not_guessed(
    draft: CatalogContent,
) -> None:
    pending = PredefinedTypeContext(
        status="undetermined", reason="ocorrência sem PredefinedType; tipo associado não consultado"
    )

    result = _covering(draft, pending)

    assert (result.status, result.binding_id) == ("ambiguous", None)
    covering_uses = [c for c in result.candidates if c.applicability == "indeterminate"]
    assert len(covering_uses) == 2
    assert all(any("tipo associado não consultado" in r for r in c.reasons) for c in covering_uses)


@pytest.mark.external_data
def test_covering_with_conflicting_levels_is_not_assigned_to_either_use(
    draft: CatalogContent,
) -> None:
    conflict = PredefinedTypeContext.model_validate(
        {
            "status": "determined",
            "effective_origin": "type",
            "readings": [
                {"origin": "type", "value": "FLOORING"},
                {"origin": "occurrence", "value": "CLADDING"},
            ],
        }
    )

    result = _covering(draft, conflict)

    assert (result.status, result.binding_id) == ("ambiguous", None)


@pytest.mark.external_data
def test_slab_with_no_predefined_type_at_either_level_is_outside_the_sample(
    draft: CatalogContent,
) -> None:
    result = _resolve(
        draft,
        set_name="EB_Orçamento",
        field_name="Tipo_Concretagem",
        entity="IfcSlab",
        predefined_type=PredefinedTypeContext(status="absent"),
    )

    assert result.status == "unmapped"
    assert {c.applicability for c in result.candidates} == {"not_applicable"}


@pytest.mark.external_data
def test_area_forma_resolves_with_pending_limits(draft: CatalogContent) -> None:
    result = _resolve(
        draft,
        set_name="EB_Orçamento",
        field_name="Area_Forma",
        entity="IfcSlab",
        predefined_type=_pt("FLOOR"),
    )

    assert result.status == "exact"
    assert len(result.decision_ids) == 1
    assert any("pendente de reconciliação" in limitation for limitation in result.limitations)
    assert any("escrita desabilitada" in limitation for limitation in result.limitations)


@pytest.mark.external_data
def test_real_field_outside_the_sample_is_unmapped(draft: CatalogContent) -> None:
    result = _resolve(
        draft,
        set_name="EB_Orçamento",
        field_name="Tipo_Fechadura",
        entity="IfcDoor",
        predefined_type=_pt("DOOR"),
    )

    assert (result.status, result.candidates) == ("unmapped", ())


@pytest.mark.external_data
def test_set_name_without_cedilla_does_not_resolve(draft: CatalogContent) -> None:
    result = _resolve(
        draft,
        set_name="EB_Orcamento",
        field_name="Tipo_Concretagem",
        entity="IfcSlab",
        predefined_type=_pt("FLOOR"),
    )

    assert result.status == "unmapped"


@pytest.mark.external_data
def test_policies_reference_operations_not_yet_available(draft: CatalogContent) -> None:
    assert draft.evidence_policies
    for policy in draft.evidence_policies:
        capability = DEFAULT_OPERATION_REGISTRY.capability(policy.operation_id)
        assert capability.status == "unsupported"


@pytest.mark.external_data
def test_draft_based_on_another_matrix_revision_is_refused(
    tmp_path: Path, imported: DaianeImport
) -> None:
    data = json.loads(E1_DRAFT_PATH.read_text(encoding="utf-8"))
    data["based_on"]["matrix_sha256"] = "0" * 64
    stale = tmp_path / "rascunho.json"
    stale.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(DraftBaseMismatchError):
        load_daiane_draft(stale, imported)


@pytest.mark.external_data
def test_coverage_marks_only_sample_rows_as_draft(
    imported: DaianeImport, draft: CatalogContent
) -> None:
    rows = {row["source_entry_id"]: row for row in coverage_rows(imported, draft)}
    sample = {a for b in draft.bindings for a in b.source_assertion_ids}

    assert len(sample) == 9
    assert {rows[a]["catalog_status"] for a in sample} == {"rascunho"}
    assert rows["dai2025:A2-015"]["catalog_status"] == "nao_cadastrado"
    assert sum(row["catalog_status"] == "rascunho" for row in rows.values()) == 9


def _altered_draft(tmp_path: Path, change: str) -> Path:
    data = json.loads(E1_DRAFT_PATH.read_text(encoding="utf-8"))
    if change == "own_sources":
        data["entities"]["source_assertions"] = []
    elif change == "missing_row":
        data["entities"]["bindings"][0]["source_assertion_ids"] = ["dai2025:A7-999"]
    path = tmp_path / "rascunho.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.mark.external_data
def test_draft_cannot_carry_its_own_source_rows(tmp_path: Path, imported: DaianeImport) -> None:
    with pytest.raises(DraftFormatError, match="source_assertions"):
        load_daiane_draft(_altered_draft(tmp_path, "own_sources"), imported)


@pytest.mark.external_data
def test_draft_citing_a_row_absent_from_the_source_is_refused(
    tmp_path: Path, imported: DaianeImport
) -> None:
    with pytest.raises(CatalogValidationError) as exc:
        load_daiane_draft(_altered_draft(tmp_path, "missing_row"), imported)

    assert {issue.code for issue in exc.value.issues} == {"orphan_reference"}
