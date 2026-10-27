"""Resolução de binding com estados explícitos (M1-05); catálogo SINTÉTICO.

A resolução informa significado e uso cadastrados; não decide conformidade IDS,
não escolhe o primeiro candidato e não fabrica correspondência por semelhança.
"""

import pytest
from pydantic import ValidationError

from src.domain_catalog.content import CatalogContent
from src.domain_catalog.contracts import (
    BindingRequest,
    PredefinedTypeContext,
    ResolutionCandidate,
    ResolutionResult,
)
from src.domain_catalog.models import AliasScope, IFCBinding
from src.domain_catalog.resolver import resolve_binding
from tests.domain_catalog import factories as f
from tests.domain_catalog.factories import R

CONTENT = f.resolution_content()


def _resolve(content: CatalogContent = CONTENT, **request: object) -> ResolutionResult:
    data: dict[str, object] = {"ifc_schema": "IFC4", "facet": "property"}
    data.update(request)
    return resolve_binding(content, BindingRequest.model_validate(data))


def test_literal_path_with_known_class_is_exact() -> None:
    result = _resolve(set_name="SYN_Conjunto", field_name="SYN_Metodo", entity="IfcColumn")

    assert (result.status, result.binding_id, result.concept_id) == (
        "exact",
        R.B_METODO_COLUMN,
        R.METODO,
    )


def test_shared_concept_without_class_is_not_guessed() -> None:
    result = _resolve(set_name="SYN_Conjunto", field_name="SYN_Metodo")

    assert result.status == "ambiguous"
    assert (result.binding_id, result.concept_id) == (None, None)
    assert [c.binding_id for c in result.candidates] == [R.B_METODO_SLAB, R.B_METODO_COLUMN]
    assert {c.concept_id for c in result.candidates} == {R.METODO}


def test_same_field_name_in_different_sets_keeps_concepts_apart() -> None:
    without_set = _resolve(set_name=None, field_name="Status")
    with_set = _resolve(set_name="SYN_PsetB", field_name="Status", entity="IfcDoor")

    assert without_set.status == "ambiguous"
    assert {c.concept_id for c in without_set.candidates} == {R.STATUS_A, R.STATUS_B}
    assert (with_set.status, with_set.concept_id) == ("exact", R.STATUS_B)


def test_predefined_type_separates_homonyms() -> None:
    floor = _resolve(
        set_name="SYN_Conjunto",
        field_name="SYN_Acabamento",
        entity="IfcCovering",
        predefined_type=PredefinedTypeContext.determined("FLOORING", origin="occurrence"),
    )
    unknown = _resolve(set_name="SYN_Conjunto", field_name="SYN_Acabamento", entity="IfcCovering")

    assert (floor.status, floor.concept_id) == ("exact", R.ACAB_PISO)
    assert unknown.status == "ambiguous"
    assert {c.applicability for c in unknown.candidates} == {"indeterminate"}


def test_binding_for_other_classes_leaves_field_unmapped_in_context() -> None:
    result = _resolve(set_name="SYN_Conjunto", field_name="SYN_Metodo", entity="IfcBeam")

    assert result.status == "unmapped"
    assert {c.applicability for c in result.candidates} == {"not_applicable"}


def test_unknown_field_is_unmapped_without_candidates() -> None:
    result = _resolve(set_name="SYN_Conjunto", field_name="SYN_Inexistente", entity="IfcSlab")

    assert result.status == "unmapped"
    assert result.candidates == ()


@pytest.mark.parametrize("near_miss", ["syn_metodo", "SYN Metodo", "SYN_Método", "SYN_Metodo "])
def test_similar_field_names_do_not_resolve(near_miss: str) -> None:
    result = _resolve(set_name="SYN_Conjunto", field_name=near_miss, entity="IfcSlab")

    assert (result.status, result.candidates) == ("unmapped", ())


def test_set_name_is_compared_exactly() -> None:
    result = _resolve(set_name="syn_conjunto", field_name="SYN_Metodo", entity="IfcSlab")

    assert result.status == "unmapped"


def test_unknown_construction_system_is_not_resolved() -> None:
    result = _resolve(set_name="SYN_Conjunto", field_name="SYN_Bloco", entity="IfcWall")

    assert result.status == "ambiguous"
    assert result.binding_id is None
    assert any("construction_system" in reason for reason in result.reasons)


@pytest.mark.parametrize(("system", "status"), [("alvenaria", "exact"), ("drywall", "unmapped")])
def test_known_construction_system_decides_resolution(system: str, status: str) -> None:
    result = _resolve(
        set_name="SYN_Conjunto",
        field_name="SYN_Bloco",
        entity="IfcWall",
        facts={"construction_system": system},
    )

    assert result.status == status


def test_schema_not_declared_by_binding_is_unsupported() -> None:
    result = _resolve(
        ifc_schema="IFC2X3", set_name="SYN_Conjunto", field_name="SYN_SoIfc4", entity="IfcSlab"
    )

    assert (result.status, result.binding_id) == ("unsupported", None)
    assert [c.binding_id for c in result.candidates] == [R.B_SO_IFC4]
    assert result.candidates[0].schema_declared is False


def test_approved_historical_spelling_is_a_mapping_not_the_literal_path() -> None:
    result = _resolve(
        ifc_schema="IFC2X3", set_name="SYN_Qto", field_name="Heigth", entity="IfcWallStandardCase"
    )

    assert (result.status, result.binding_id, result.concept_id) == (
        "approved_mapping",
        R.B_ALTURA,
        R.ALTURA,
    )
    assert result.candidates[0].match == "alias"
    assert result.candidates[0].alias_id == R.ALIAS_HEIGTH
    assert any("caminho exigido" in limitation for limitation in result.limitations)


def test_alias_outside_its_scope_does_not_resolve() -> None:
    result = _resolve(set_name="SYN_Qto", field_name="Altura", entity="IfcWall")

    assert (result.status, result.candidates) == ("unmapped", ())


def test_unapproved_alias_is_reported_but_not_used() -> None:
    content = CONTENT.model_copy(update={"aliases": (*CONTENT.aliases, f.draft_alias())})

    result = _resolve(content, set_name="SYN_Qto", field_name="Hght", entity="IfcWall")

    assert result.status == "unmapped"
    assert [c.alias_id for c in result.candidates] == [R.ALIAS_RASCUNHO]
    assert any("não aprovado" in reason for reason in result.candidates[0].reasons)


def test_colliding_aliases_are_ambiguous() -> None:
    result = _resolve(set_name="SYN_Conjunto", field_name="Metodo", entity="IfcSlab")

    assert result.status == "ambiguous"
    assert {c.binding_id for c in result.candidates} == {R.B_METODO_SLAB, R.B_SO_IFC4}


def test_literal_path_takes_precedence_over_alias_with_same_term() -> None:
    literal = CONTENT.bindings[2].model_copy(
        update={"id": "urn:uuid:00000000-0000-4000-8000-000000001099", "field_name": "Metodo"}
    )
    content = CONTENT.model_copy(update={"bindings": (*CONTENT.bindings, literal)})

    result = _resolve(content, set_name="SYN_Conjunto", field_name="Metodo", entity="IfcSlab")

    assert (result.status, result.binding_id) == ("exact", literal.id)
    assert [c.match for c in result.candidates] == ["literal_path"]


def test_pending_carrier_resolves_with_explicit_limits_and_decision() -> None:
    result = _resolve(set_name="SYN_Conjunto", field_name="SYN_AreaPendente", entity="IfcSlab")

    assert (result.status, result.binding_id) == ("exact", R.B_AREA_PENDENTE)
    assert result.decision_ids == (R.DECISION_AREA,)
    assert any("pendente de reconciliação" in limitation for limitation in result.limitations)
    assert any("escrita desabilitada" in limitation for limitation in result.limitations)


def test_unspecified_scope_is_reported_as_no_write_destination() -> None:
    # Decisão de 13/10: o silêncio da fonte sobre ocorrência/tipo não escolhe destino.
    result = _resolve(set_name="SYN_Conjunto", field_name="SYN_AreaPendente", entity="IfcSlab")

    assert any("nem nos dois" in limitation for limitation in result.limitations)


def test_occurrence_or_type_scope_still_requires_an_explicit_destination() -> None:
    either = CONTENT.bindings[2].model_copy(update={"scope": "occurrence_or_type"})
    content = CONTENT.model_copy(
        update={"bindings": (*CONTENT.bindings[:2], either, *CONTENT.bindings[3:])}
    )

    result = _resolve(content, set_name="SYN_Conjunto", field_name="SYN_Metodo", entity="IfcSlab")

    assert result.status == "exact"
    assert any("destino explícito" in limitation for limitation in result.limitations)


def _undetermined_area() -> CatalogContent:
    """Uso pendente sintético com portador não determinado entre propriedade e quantidade."""
    bindings = tuple(
        b.model_copy(update={"carrier_kind": "property_or_quantity"})
        if b.id == R.B_AREA_PENDENTE
        else b
        for b in CONTENT.bindings
    )
    return CONTENT.model_copy(update={"bindings": bindings})


def test_undetermined_carrier_answers_the_property_facet_with_its_limit() -> None:
    # Decisão B do curador responsável (14/10): o desconhecido é declarado, sem eleger portador.
    result = _resolve(
        _undetermined_area(),
        set_name="SYN_Conjunto",
        field_name="SYN_AreaPendente",
        entity="IfcSlab",
    )

    assert (result.status, result.binding_id) == ("exact", R.B_AREA_PENDENTE)
    assert any("nenhum dos dois" in limitation for limitation in result.limitations)
    assert any("escrita desabilitada" in limitation for limitation in result.limitations)


@pytest.mark.parametrize("facet", ["attribute", "classification", "material"])
def test_undetermined_carrier_does_not_answer_other_facets(facet: str) -> None:
    result = _resolve(
        _undetermined_area(), facet=facet, field_name="SYN_AreaPendente", entity="IfcSlab"
    )

    assert (result.status, result.candidates) == ("unmapped", ())


def test_exact_result_lists_only_decisions_about_the_chosen_binding() -> None:
    about_column = CONTENT.reconciliation_decisions[0].model_copy(
        update={
            "id": "urn:uuid:00000000-0000-4000-8000-000000001081",
            "affected_binding_ids": (R.B_METODO_COLUMN,),
        }
    )
    content = CONTENT.model_copy(
        update={"reconciliation_decisions": (*CONTENT.reconciliation_decisions, about_column)}
    )

    slab = _resolve(content, set_name="SYN_Conjunto", field_name="SYN_Metodo", entity="IfcSlab")
    unknown = _resolve(content, set_name="SYN_Conjunto", field_name="SYN_Metodo")

    assert (slab.status, slab.decision_ids) == ("exact", ())
    assert (unknown.status, unknown.decision_ids) == ("ambiguous", (about_column.id,))


def test_draft_content_resolution_is_flagged_as_not_operational() -> None:
    draft = f.minimal_content(lifecycle="draft")

    result = _resolve(draft, set_name="SYN_Conjunto", field_name="SYN_Metodo", entity="IfcSlab")

    assert result.status == "exact"
    assert any("não operacional" in limitation for limitation in result.limitations)


def test_candidate_order_does_not_depend_on_catalog_order() -> None:
    reversed_content = CONTENT.model_copy(update={"bindings": tuple(reversed(CONTENT.bindings))})

    original = _resolve(set_name="SYN_Conjunto", field_name="SYN_Metodo")
    reordered = _resolve(reversed_content, set_name="SYN_Conjunto", field_name="SYN_Metodo")

    assert [c.binding_id for c in original.candidates] == [
        c.binding_id for c in reordered.candidates
    ]


def test_package_error_is_a_result_state_not_an_empty_answer() -> None:
    request = BindingRequest(ifc_schema="IFC4", facet="property", field_name="SYN_Metodo")

    result = ResolutionResult.package_error(request, "hash do manifesto divergente")

    assert (result.status, result.candidates, result.binding_id) == ("package_error", (), None)
    assert result.reasons == ("hash do manifesto divergente",)


# --- Revisão E1-06: os fatos da consulta não mudam depois da resolução -------------------


def _request_with_facts(facts: dict[str, str]) -> BindingRequest:
    return BindingRequest.model_validate(
        {"ifc_schema": "IFC4", "facet": "property", "field_name": "SYN_Bloco", "facts": facts}
    )


def test_facts_of_a_result_cannot_be_changed_after_resolution() -> None:
    result = _resolve(
        set_name="SYN_Conjunto",
        field_name="SYN_Bloco",
        entity="IfcWall",
        facts={"construction_system": "alvenaria"},
    )
    before = result.model_dump(mode="json")

    with pytest.raises(TypeError):
        result.request.facts["construction_system"] = "drywall"  # type: ignore[index]

    assert result.status == "exact"
    assert result.model_dump(mode="json") == before


def test_request_is_decoupled_from_the_mapping_given_by_the_caller() -> None:
    facts = {"construction_system": "alvenaria"}
    request = _request_with_facts(facts)

    facts["construction_system"] = "drywall"

    assert request.facts["construction_system"] == "alvenaria"


@pytest.mark.parametrize("method", ["update", "pop", "popitem", "clear", "setdefault"])
def test_facts_offer_no_mutating_method(method: str) -> None:
    assert not hasattr(_request_with_facts({"a": "1"}).facts, method)


def test_facts_keep_mapping_reads_and_the_json_object_form() -> None:
    request = _request_with_facts({"b": "2", "a": "1"})

    assert dict(request.facts) == {"a": "1", "b": "2"}
    assert (request.facts.get("a"), "b" in request.facts, len(request.facts)) == ("1", True, 2)
    assert request.model_dump(mode="json")["facts"] == {"a": "1", "b": "2"}
    assert BindingRequest.model_validate_json(request.model_dump_json()) == request


def test_equal_requests_hash_equally_and_cross_process_boundaries() -> None:
    # Workers do M6 rodam em processo separado: o DTO precisa ser serializável.
    import copy
    import pickle

    request = _request_with_facts({"construction_system": "alvenaria"})
    twin = _request_with_facts({"construction_system": "alvenaria"})

    assert hash(request) == hash(twin)
    assert pickle.loads(pickle.dumps(request)) == request
    assert copy.deepcopy(request) == request


# --- Revisão E1-01: schema separa usos elegíveis de informativos -------------------------


def _with_bindings(*extra: IFCBinding) -> CatalogContent:
    return CONTENT.model_copy(update={"bindings": (*CONTENT.bindings, *extra)})


def test_use_declared_only_for_another_schema_does_not_create_ambiguity() -> None:
    ifc2x3_only = CONTENT.bindings[2].model_copy(
        update={
            "id": "urn:uuid:00000000-0000-4000-8000-000000001099",
            "declared_schemas": ("IFC2X3",),
        }
    )

    result = _resolve(
        _with_bindings(ifc2x3_only),
        set_name="SYN_Conjunto",
        field_name="SYN_Metodo",
        entity="IfcSlab",
    )

    assert (result.status, result.binding_id) == ("exact", R.B_METODO_SLAB)
    excluded = next(c for c in result.candidates if c.binding_id == ifc2x3_only.id)
    assert excluded.schema_declared is False
    assert any("IFC4" in reason for reason in excluded.reasons)


def test_uses_declared_only_for_other_schemas_are_unsupported_not_ambiguous() -> None:
    result = _resolve(ifc_schema="IFC2X3", set_name="SYN_Conjunto", field_name="SYN_Metodo")

    assert (result.status, result.binding_id) == ("unsupported", None)
    assert [c.binding_id for c in result.candidates] == [R.B_METODO_SLAB, R.B_METODO_COLUMN]


def test_eligible_indeterminate_use_is_kept_when_the_other_use_is_for_another_schema() -> None:
    other_schema = CONTENT.bindings[6].model_copy(
        update={
            "id": "urn:uuid:00000000-0000-4000-8000-000000001098",
            "applicability_rule_id": R.RULE_WALL,
            "declared_schemas": ("IFC2X3",),
        }
    )

    result = _resolve(
        _with_bindings(other_schema),
        set_name="SYN_Conjunto",
        field_name="SYN_Bloco",
        entity="IfcWall",
    )

    assert (result.status, result.binding_id) == ("ambiguous", None)
    assert any("construction_system" in reason for reason in result.reasons)
    assert not any("usos possíveis" in reason for reason in result.reasons)


# --- Revisão E1-02: aliases do mesmo uso não multiplicam usos ---------------------------


def _metodo_aliases(**second: object) -> CatalogContent:
    """Os dois aliases ``Metodo`` apontam o mesmo binding de laje."""
    changed = CONTENT.aliases[3].model_copy(update={"target_binding_id": R.B_METODO_SLAB, **second})
    return CONTENT.model_copy(update={"aliases": (*CONTENT.aliases[:3], changed)})


def test_two_approved_aliases_of_the_same_use_resolve_to_that_use() -> None:
    content = _metodo_aliases(scope=AliasScope(entity_classes=("IfcSlab",)))

    result = _resolve(content, set_name="SYN_Conjunto", field_name="Metodo", entity="IfcSlab")

    assert (result.status, result.binding_id) == ("approved_mapping", R.B_METODO_SLAB)
    assert result.alias_ids == (R.ALIAS_METODO_1, R.ALIAS_METODO_2)
    assert [c.alias_id for c in result.candidates] == [R.ALIAS_METODO_1, R.ALIAS_METODO_2]


def test_unapproved_alias_of_the_chosen_use_stays_a_candidate_but_is_not_cited() -> None:
    content = _metodo_aliases(lifecycle="draft")

    result = _resolve(content, set_name="SYN_Conjunto", field_name="Metodo", entity="IfcSlab")

    assert (result.status, result.alias_ids) == ("approved_mapping", (R.ALIAS_METODO_1,))
    assert {c.alias_id for c in result.candidates} == {R.ALIAS_METODO_1, R.ALIAS_METODO_2}


# --- Revisão E1-05: IDs escolhidos só existem, juntos, em resolução única ---------------

_STATUSES = ("exact", "approved_mapping", "ambiguous", "unmapped", "unsupported", "package_error")
_RESOLVED = {"exact", "approved_mapping"}
_ALIAS_ID = "urn:uuid:00000000-0000-4000-8000-0000000000a7"


def _candidate(match: str = "literal_path", alias_id: str | None = None) -> ResolutionCandidate:
    return ResolutionCandidate.model_validate(
        {
            "binding_id": f.BINDING_ID,
            "concept_id": f.CONCEPT_ID,
            "concept_code": "SYN_METODO",
            "match": match,
            "alias_id": alias_id,
            "applicability": "applicable",
            "schema_declared": True,
            "carrier_status": "approved",
            "lifecycle": "approved",
            "write_enabled": False,
        }
    )


def _result(status: str, **fields: object) -> ResolutionResult:
    data: dict[str, object] = {
        "status": status,
        "request": {"ifc_schema": "IFC4", "facet": "property", "field_name": "SYN_Metodo"},
    }
    if status == "approved_mapping":
        data.update(candidates=[_candidate("alias", _ALIAS_ID)], alias_ids=[_ALIAS_ID])
    elif status == "exact":
        data.update(candidates=[_candidate()])
    data.update(fields)
    return ResolutionResult.model_validate(data)


@pytest.mark.parametrize("status", _STATUSES)
@pytest.mark.parametrize(
    "chosen",
    [{}, {"binding_id": f.BINDING_ID}, {"concept_id": f.CONCEPT_ID}],
    ids=["nenhum", "so-binding", "so-conceito"],
)
def test_partial_or_absent_choice_is_valid_only_for_unresolved_states(
    status: str, chosen: dict[str, str]
) -> None:
    if status in _RESOLVED or chosen:
        with pytest.raises(ValidationError):
            _result(status, **chosen)
    else:
        assert _result(status).binding_id is None


@pytest.mark.parametrize("status", _STATUSES)
def test_complete_choice_is_valid_only_for_unique_resolution(status: str) -> None:
    both = {"binding_id": f.BINDING_ID, "concept_id": f.CONCEPT_ID}
    if status in _RESOLVED:
        assert _result(status, **both).binding_id == f.BINDING_ID
    else:
        with pytest.raises(ValidationError):
            _result(status, **both)


def _contract_refusal(status: str, **fields: object) -> str:
    """Mensagem da recusa, exigindo que venha do validador do contrato (não de campo extra)."""
    with pytest.raises(ValidationError) as exc:
        _result(status, **fields)
    (error,) = exc.value.errors()
    assert error["type"] == "value_error", error
    return str(error["msg"])


_BOTH = {"binding_id": f.BINDING_ID, "concept_id": f.CONCEPT_ID}


@pytest.mark.parametrize(
    "fields",
    [{"candidates": [], **_BOTH}, {**_BOTH, "concept_id": R.METODO}],
    ids=["sem-candidato", "outro-conceito"],
)
def test_chosen_use_must_be_one_of_the_candidates_with_its_concept(
    fields: dict[str, object],
) -> None:
    assert "candidato" in _contract_refusal("exact", **fields)


@pytest.mark.parametrize(
    ("status", "fields"),
    [
        ("exact", {"alias_ids": [_ALIAS_ID], **_BOTH}),
        ("approved_mapping", {"alias_ids": [], **_BOTH}),
        ("approved_mapping", {"alias_ids": [R.ALIAS_HEIGTH], **_BOTH}),
        ("ambiguous", {"alias_ids": [_ALIAS_ID]}),
    ],
    ids=["exato-com-alias", "mapeamento-sem-alias", "alias-alheio", "nao-resolvido-com-alias"],
)
def test_alias_ids_belong_only_to_an_approved_mapping_of_the_chosen_use(
    status: str, fields: dict[str, object]
) -> None:
    assert "alias" in _contract_refusal(status, **fields)
