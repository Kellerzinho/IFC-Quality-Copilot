"""Entidades do catálogo: tipos, estados e invariantes (M1-03).

Fixtures sintéticas (``factories``); nenhum caso aqui representa dado real de Daiane.
"""

import json

import pytest
from pydantic import ValidationError

from src.domain_catalog.canonical import canonical_json_bytes
from src.domain_catalog.content import CatalogContent, validate_content
from src.domain_catalog.errors import CatalogValidationError
from src.domain_catalog.models import (
    AliasMapping,
    AliasScope,
    AllowedValue,
    AllowedValueSet,
    ApplicabilityRule,
    ConceptDefinition,
    IFCBinding,
    LocalizedText,
    UnitDefinition,
)
from tests.domain_catalog import factories as f


def _issue_codes(exc: pytest.ExceptionInfo[CatalogValidationError]) -> set[str]:
    return {issue.code for issue in exc.value.issues}


# --- Valores permitidos: código não muda de tipo ----------------------------


def test_code_value_set_rejects_integer_code() -> None:
    with pytest.raises(ValidationError, match="value_type"):
        AllowedValueSet(
            id=f.VALUE_SET_ID,
            value_type="code",
            values=(AllowedValue(code="1"), AllowedValue(code=2)),
            lifecycle="draft",
        )


def test_integer_value_set_rejects_numeric_looking_text() -> None:
    with pytest.raises(ValidationError, match="value_type"):
        AllowedValueSet(
            id=f.VALUE_SET_ID,
            value_type="integer",
            values=(AllowedValue(code="1"),),
            lifecycle="draft",
        )


@pytest.mark.parametrize(("value_type", "code"), [("boolean", 1), ("integer", True)])
def test_boolean_and_integer_codes_are_not_interchangeable(value_type: str, code: object) -> None:
    with pytest.raises(ValidationError, match="value_type"):
        AllowedValueSet(
            id=f.VALUE_SET_ID,
            value_type=value_type,
            values=(AllowedValue(code=code),),
            lifecycle="draft",
        )


def test_numeric_looking_codes_stay_text_after_json_round_trip() -> None:
    raw = json.dumps(
        {
            "id": f.VALUE_SET_ID,
            "value_type": "code",
            "values": [{"code": "1", "labels": []}, {"code": "18", "labels": []}],
            "ordered": False,
            "restricts_value_set_id": None,
            "source_assertion_ids": [],
            "lifecycle": "draft",
        }
    )

    loaded = AllowedValueSet.model_validate_json(raw)

    assert [value.code for value in loaded.values] == ["1", "18"]
    assert all(type(value.code) is str for value in loaded.values)


def test_duplicate_codes_in_a_value_set_are_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicad"):
        AllowedValueSet(
            id=f.VALUE_SET_ID,
            value_type="code",
            values=(AllowedValue(code="A"), AllowedValue(code="A")),
            lifecycle="draft",
        )


@pytest.mark.parametrize(("value_type", "codes"), [("integer", (0, 1)), ("boolean", (False, True))])
def test_zero_and_false_survive_canonical_serialization(
    value_type: str, codes: tuple[object, ...]
) -> None:
    value_set = AllowedValueSet(
        id=f.VALUE_SET_ID,
        value_type=value_type,
        values=tuple(AllowedValue(code=code) for code in codes),
        lifecycle="draft",
    )

    data = canonical_json_bytes(value_set.model_dump(mode="json"))
    again = AllowedValueSet.model_validate_json(data)

    assert [value.code for value in again.values] == list(codes)
    assert [type(value.code) for value in again.values] == [type(code) for code in codes]


# --- Conceito, unidade e dimensão --------------------------------------------


def test_unit_requires_a_physical_dimension_on_the_concept() -> None:
    with pytest.raises(ValidationError, match="dimens"):
        ConceptDefinition(
            id=f.CONCEPT_ID,
            code="SYN_SEM_DIMENSAO",
            labels=f.pt("Sem dimensão"),
            logical_type="decimal",
            dimension=None,
            unit_id=f.UNIT_ID,
            lifecycle="draft",
        )


def test_area_concept_rejects_length_unit() -> None:
    area = ConceptDefinition(
        id=f.CONCEPT_ID,
        code="SYN_AREA",
        labels=f.pt("Área sintética"),
        logical_type="decimal",
        dimension="area",
        unit_id=f.UNIT_ID,
        lifecycle="draft",
    )
    content = CatalogContent(units=(f.length_unit(),), concepts=(area,))

    with pytest.raises(CatalogValidationError) as exc:
        validate_content(content, for_release=False)

    assert _issue_codes(exc) == {"unit_dimension_mismatch"}
    assert exc.value.issues[0].entity_id == f.CONCEPT_ID
    assert exc.value.issues[0].field == "unit_id"


def test_text_concept_cannot_declare_physical_dimension() -> None:
    with pytest.raises(ValidationError, match="dimens"):
        ConceptDefinition(
            id=f.CONCEPT_ID,
            code="SYN_TEXTO",
            labels=f.pt("Texto"),
            logical_type="string",
            dimension="length",
            lifecycle="draft",
        )


def test_approved_concept_requires_definition() -> None:
    with pytest.raises(ValidationError, match="defini"):
        ConceptDefinition(
            id=f.CONCEPT_ID,
            code="SYN_SEM_DEFINICAO",
            labels=f.pt("Sem definição"),
            logical_type="code",
            lifecycle="approved",
        )


def test_draft_concept_may_wait_for_definition() -> None:
    draft = ConceptDefinition(
        id=f.CONCEPT_ID,
        code="SYN_RASCUNHO",
        labels=f.pt("Rascunho"),
        logical_type="code",
        lifecycle="draft",
    )

    assert draft.definition == ()


def test_concept_requires_explicit_logical_type() -> None:
    with pytest.raises(ValidationError, match="logical_type"):
        ConceptDefinition(
            id=f.CONCEPT_ID,
            code="IS_EXTERNAL",
            labels=f.pt("IsExternal"),
            lifecycle="draft",
        )


def test_local_ids_are_uuid_urns_not_readable_codes() -> None:
    with pytest.raises(ValidationError, match="id"):
        ConceptDefinition(
            id="Tipo_Concretagem",
            code="SYN_X",
            labels=f.pt("X"),
            logical_type="code",
            lifecycle="draft",
        )


def test_labels_cannot_repeat_a_language() -> None:
    with pytest.raises(ValidationError, match="idioma"):
        ConceptDefinition(
            id=f.CONCEPT_ID,
            code="SYN_X",
            labels=(
                LocalizedText(lang="pt-BR", text="Um"),
                LocalizedText(lang="pt-BR", text="Dois"),
            ),
            logical_type="code",
            lifecycle="draft",
        )


def test_unit_definition_requires_dimension() -> None:
    with pytest.raises(ValidationError, match="dimension"):
        UnitDefinition(id=f.UNIT_ID, symbol="m2", lifecycle="draft")


# --- Bindings: portador declarado, nunca inferido do nome ------------------------


def _binding(**changes: object) -> IFCBinding:
    data = f.binding().model_dump()
    data.update(changes)
    return IFCBinding.model_validate(data)


def test_property_binding_requires_declared_set_kind() -> None:
    with pytest.raises(ValidationError, match="set_kind"):
        _binding(set_name="Pset_SlabCommon", set_kind=None)


def test_property_binding_requires_set_name() -> None:
    with pytest.raises(ValidationError, match="set_name"):
        _binding(set_name=None)


def test_attribute_binding_has_no_set() -> None:
    with pytest.raises(ValidationError, match="set_name"):
        _binding(carrier_kind="attribute", field_name="Name", set_kind=None, ifc_type="IfcLabel")


def test_pending_carrier_cannot_enable_write() -> None:
    with pytest.raises(ValidationError, match="write_enabled"):
        _binding(carrier_status="pending_reconciliation", ifc_type=None, write_enabled=True)


def test_write_requires_approved_binding() -> None:
    with pytest.raises(ValidationError, match="write_enabled"):
        _binding(lifecycle="draft", write_enabled=True)


def test_unspecified_scope_never_enables_writing() -> None:
    # Decisão de 13/10: escopo que a fonte não esclarece não autoriza escrever na
    # ocorrência, no tipo, nem nos dois; a escrita futura exige destino explícito.
    with pytest.raises(ValidationError, match="escopo"):
        _binding(scope="unspecified", write_enabled=True)


@pytest.mark.parametrize("scope", ["occurrence", "type", "occurrence_or_type"])
def test_declared_scope_with_everything_approved_may_enable_writing(scope: str) -> None:
    assert _binding(scope=scope, write_enabled=True).write_enabled is True


@pytest.mark.parametrize(
    ("carrier_kind", "ifc_type"),
    [("property", "IfcQuantityArea"), ("quantity", "IfcAreaMeasure")],
)
def test_quantity_entity_and_property_measure_are_not_interchangeable(
    carrier_kind: str, ifc_type: str
) -> None:
    with pytest.raises(ValidationError, match="ifc_type"):
        _binding(carrier_kind=carrier_kind, ifc_type=ifc_type)


def test_unknown_ifc_type_is_rejected() -> None:
    with pytest.raises(ValidationError, match="ifc_type"):
        _binding(ifc_type="IfcInventedMeasure")


# --- Portador ainda não determinado (política B) ---

_UNDETERMINED = {
    "carrier_kind": "property_or_quantity",
    "carrier_status": "pending_reconciliation",
    "ifc_type": None,
}


def test_undetermined_carrier_is_declared_without_electing_a_side() -> None:
    binding = _binding(**_UNDETERMINED)

    assert (binding.carrier_kind, binding.ifc_type, binding.write_enabled) == (
        "property_or_quantity",
        None,
        False,
    )


def test_undetermined_carrier_cannot_be_an_approved_carrier() -> None:
    with pytest.raises(ValidationError, match="pending_reconciliation"):
        _binding(**{**_UNDETERMINED, "carrier_status": "approved"})


@pytest.mark.parametrize("ifc_type", ["IfcAreaMeasure", "IfcQuantityArea"])
def test_undetermined_carrier_cannot_carry_a_value_type(ifc_type: str) -> None:
    # Medida de propriedade ou entidade de quantidade elegeria o portador.
    with pytest.raises(ValidationError, match="ifc_type nulo"):
        _binding(**{**_UNDETERMINED, "ifc_type": ifc_type})


def test_undetermined_carrier_never_enables_writing() -> None:
    with pytest.raises(ValidationError, match="write_enabled"):
        _binding(**_UNDETERMINED, write_enabled=True)


@pytest.mark.parametrize("missing", ["set_name", "set_kind"])
def test_undetermined_carrier_still_names_its_set(missing: str) -> None:
    with pytest.raises(ValidationError, match=missing):
        _binding(**_UNDETERMINED, **{missing: None})


def test_binding_requires_declared_schema() -> None:
    with pytest.raises(ValidationError, match="declared_schemas"):
        _binding(declared_schemas=())


def test_binding_ifc_type_must_match_concept_type() -> None:
    content = f.minimal_content()
    wrong = content.model_copy(update={"bindings": (_binding(ifc_type="IfcLengthMeasure"),)})

    with pytest.raises(CatalogValidationError) as exc:
        validate_content(wrong, for_release=False)

    assert _issue_codes(exc) == {"ifc_type_incompatible"}


# --- Aplicabilidade e aliases -------------------------------------------------


def test_applicability_rule_requires_explicit_subtype_policy() -> None:
    with pytest.raises(ValidationError, match="include_subtypes"):
        ApplicabilityRule(id=f.RULE_ID, entity_classes=("IfcWall",), lifecycle="draft")


def test_applicability_rule_rejects_non_ifc_class_names() -> None:
    with pytest.raises(ValidationError, match="entity_classes"):
        ApplicabilityRule(
            id=f.RULE_ID, entity_classes=("Parede",), include_subtypes=False, lifecycle="draft"
        )


def test_resolution_alias_must_be_scoped() -> None:
    with pytest.raises(ValidationError, match="escopo"):
        AliasMapping(
            id="urn:uuid:00000000-0000-4000-8000-0000000000a1",
            term="Heigth",
            purpose="historical_spelling",
            scope=AliasScope(),
            target_binding_id=f.BINDING_ID,
            lifecycle="draft",
        )


def test_search_alias_may_be_global() -> None:
    alias = AliasMapping(
        id="urn:uuid:00000000-0000-4000-8000-0000000000a1",
        term="metodo",
        purpose="search",
        scope=AliasScope(),
        target_concept_id=f.CONCEPT_ID,
        lifecycle="draft",
    )

    assert alias.scope.set_names is None


def test_alias_targets_exactly_one_entity() -> None:
    with pytest.raises(ValidationError, match="alvo"):
        AliasMapping(
            id="urn:uuid:00000000-0000-4000-8000-0000000000a1",
            term="metodo",
            purpose="search",
            scope=AliasScope(),
            target_concept_id=f.CONCEPT_ID,
            target_binding_id=f.BINDING_ID,
            lifecycle="draft",
        )


# --- Conteúdo: identidade, referências e estado de publicação --------------------


def test_minimal_synthetic_content_is_publishable() -> None:
    validate_content(f.minimal_content(), for_release=True)


def test_duplicate_ids_are_rejected_across_entity_kinds() -> None:
    clash = f.length_unit().model_copy(update={"id": f.CONCEPT_ID})
    content = f.minimal_content().model_copy(update={"units": (clash,)})

    with pytest.raises(CatalogValidationError) as exc:
        validate_content(content, for_release=False)

    assert _issue_codes(exc) == {"duplicate_id"}


def test_orphan_reference_is_rejected() -> None:
    content = f.minimal_content().model_copy(update={"concepts": ()})

    with pytest.raises(CatalogValidationError) as exc:
        validate_content(content, for_release=False)

    orphan = [issue for issue in exc.value.issues if issue.code == "orphan_reference"]
    assert [(issue.entity_id, issue.field) for issue in orphan] == [(f.BINDING_ID, "concept_id")]


def test_orphan_source_assertion_is_rejected() -> None:
    content = f.minimal_content().model_copy(update={"source_assertions": ()})

    with pytest.raises(CatalogValidationError) as exc:
        validate_content(content, for_release=False)

    assert _issue_codes(exc) == {"orphan_reference"}


def test_relabeling_keeps_identity_and_changing_id_breaks_references() -> None:
    data = f.minimal_content().model_dump(mode="json")
    data["concepts"][0]["labels"] = [{"lang": "pt-BR", "text": "Rótulo revisado"}]

    relabeled = CatalogContent.model_validate(data)
    validate_content(relabeled, for_release=True)
    assert relabeled.bindings[0].concept_id == relabeled.concepts[0].id == f.CONCEPT_ID

    data["concepts"][0]["id"] = "urn:uuid:00000000-0000-4000-8000-0000000000ff"
    with pytest.raises(CatalogValidationError) as exc:
        validate_content(CatalogContent.model_validate(data), for_release=True)
    assert _issue_codes(exc) == {"orphan_reference"}


def test_draft_content_is_valid_for_curation_but_not_for_release() -> None:
    draft = f.minimal_content(lifecycle="draft")

    validate_content(draft, for_release=False)
    with pytest.raises(CatalogValidationError) as exc:
        validate_content(draft, for_release=True)

    assert _issue_codes(exc) == {"lifecycle_not_publishable"}
    assert len(exc.value.issues) == 4


def test_value_set_restriction_cannot_extend_parent() -> None:
    restriction = AllowedValueSet(
        id="urn:uuid:00000000-0000-4000-8000-0000000000b1",
        value_type="code",
        values=(AllowedValue(code="A"), AllowedValue(code="C")),
        restricts_value_set_id=f.VALUE_SET_ID,
        lifecycle="approved",
    )
    content = f.minimal_content()
    content = content.model_copy(update={"value_sets": (*content.value_sets, restriction)})

    with pytest.raises(CatalogValidationError) as exc:
        validate_content(content, for_release=True)

    assert _issue_codes(exc) == {"restriction_not_subset"}


def test_validation_error_lists_every_issue_with_field() -> None:
    content = f.minimal_content(lifecycle="draft").model_copy(update={"concepts": ()})

    with pytest.raises(CatalogValidationError) as exc:
        validate_content(content, for_release=True)

    assert all(issue.message for issue in exc.value.issues)
    assert ("orphan_reference", "concept_id") in {
        (issue.code, issue.field) for issue in exc.value.issues
    }
    assert "lifecycle_not_publishable" in _issue_codes(exc)


def test_every_reference_field_is_checked_for_orphans() -> None:
    from src.domain_catalog.content import ENTITY_KINDS, REFERENCES

    not_entity_references = {"operation_id", "profile_id"}
    checked = {(kind, field) for kind, field, _ in REFERENCES}
    for kind in ENTITY_KINDS:
        model = CatalogContent.model_fields[kind].annotation.__args__[0]  # type: ignore[union-attr]
        for field in model.model_fields:
            if field.endswith(("_id", "_ids")) and field not in not_entity_references:
                assert (kind, field) in checked, f"{kind}.{field} sem verificação de órfão"
