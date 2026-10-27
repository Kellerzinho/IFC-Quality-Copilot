"""Duas operações M3 concretas, bundle explícito e guardas (A15–A17, A19–A21).

Recuperação exata por alias aprovado e normalização NFC+trim estrita, com
contrafactuais. Catálogo/IFC/IDS SINTÉTICOS avaliados pelo backend real.
"""

from pathlib import Path

import pytest

pytest.importorskip("ifctester", reason="extra e3 não instalado (ifctester==0.8.5)")

from src.domain_catalog.operations import DEFAULT_OPERATION_REGISTRY
from src.ifc_analyzer.observations import TextValue
from src.suggestion_engine.catalog_context import build_field_context
from src.suggestion_engine.catalog_contracts import RECIPE, FieldEnrichmentResult
from src.suggestion_engine.catalog_evidence import assess_evidence
from src.suggestion_engine.catalog_operations import (
    BundleError,
    E3OperationBundle,
    build_e3_operation_bundle,
    execute_catalog_operation,
)
from tests.suggestion_engine import m3_helpers as m
from tests.validation import ids_builders as x
from tests.validation import ifc_builders as ib


def _enrich(tmp_path: Path, catalog, model, requirement: str = m.TARGET) -> FieldEnrichmentResult:
    c = m.case(tmp_path, catalog, model, requirement)
    context = build_field_context(c.snapshot, c.row(), c.reader, c.observations, RECIPE)
    assessment = assess_evidence(context, c.bundle)
    return execute_catalog_operation(context, assessment, c.bundle)


def _legacy_model(value: str = "A", ifc_type: str = "IfcLabel"):
    model = ib.model()
    m.slab(model, ("SYN_Legado", "Metodo", value, ifc_type))
    return model


def test_default_registry_stays_empty_and_bundle_is_explicit() -> None:
    bundle = build_e3_operation_bundle()

    assert DEFAULT_OPERATION_REGISTRY.operation_ids == ()
    assert bundle.registry.operation_ids == ("normalize_code_nfc_trim", "recover_exact_property")
    assert set(bundle.handlers) == {
        ("normalize_code_nfc_trim", "1.0.0"),
        ("recover_exact_property", "1.0.0"),
    }
    assert len(bundle.manifest_sha256) == 64
    assert bundle.manifest_sha256 == build_e3_operation_bundle().manifest_sha256


def test_bundle_factory_refuses_spec_handler_mismatch() -> None:
    bundle = build_e3_operation_bundle()
    handlers = dict(bundle.handlers)
    handlers.pop(("normalize_code_nfc_trim", "1.0.0"))
    with pytest.raises(BundleError):
        E3OperationBundle.create(bundle.specs, handlers)
    extra = {
        **bundle.handlers,
        ("recover_exact_property", "2.0.0"): bundle.handlers[("recover_exact_property", "1.0.0")],
    }
    with pytest.raises(BundleError):
        E3OperationBundle.create(bundle.specs, extra)


def test_exact_recovery_from_approved_alias_keeps_ids_non_compliant(tmp_path: Path) -> None:
    c = m.case(tmp_path, m.content(), _legacy_model())
    row = c.row()
    context = build_field_context(c.snapshot, row, c.reader, c.observations, RECIPE)
    result = execute_catalog_operation(context, assess_evidence(context, c.bundle), c.bundle)

    assert row.state == "non_compliant"
    assert result.status == "proposed"
    (alternative,) = result.alternatives
    assert alternative.value == TextValue(value="A")
    assert alternative.method == "exact_recovery"
    assert alternative.transformation is None
    assert alternative.candidate_validation.status == "satisfied"
    assert (alternative.target_set_name, alternative.target_field_name) == (
        "SYN_Conjunto",
        "SYN_Metodo",
    )
    assert alternative.target_scope == "occurrence"
    assert alternative.would_modify_type is False
    assert alternative.affected_elements == (row.element,)
    assert alternative.requires_human_review is True
    assert result.assessment is not None
    assert set(alternative.evidence_refs) == set(result.assessment.admissible_observation_ids)
    assert len(alternative.evidence_refs) == 1
    resolution = context.resolutions[0]
    assert resolution.resolution.alias_ids == (m.ALIAS,)


@pytest.mark.parametrize(
    "catalog",
    [
        lambda: m.content(aliases=()),
        lambda: m.content(aliases=(m.alias(sets=("SYN_Outro",)),)),
        lambda: m.content(aliases=(m.alias(entity_classes=("IfcWall",)),)),
        lambda: m.content(aliases=(m.alias(purpose="search", sets=None),)),
    ],
)
def test_removing_or_rescoping_the_alias_blocks_recovery(tmp_path: Path, catalog) -> None:
    result = _enrich(tmp_path, catalog(), _legacy_model())
    assert result.status == "abstained"
    assert result.reason == "no_evidence"
    assert result.alternatives == ()


def test_alias_resolving_to_another_binding_is_not_evidence(tmp_path: Path) -> None:
    other_concept = m.f.concept().model_copy(
        update={"id": m.OTHER_CONCEPT, "code": "SYN_OUTRO", "value_set_id": None}
    )
    other = m.IFCBinding.model_validate(
        {
            **m.f.binding().model_dump(),
            "id": m.OTHER_BINDING,
            "concept_id": m.OTHER_CONCEPT,
            "set_name": "SYN_Legado",
            "field_name": "Metodo",
        }
    )
    catalog = m.content(extra_bindings=(other,), extra_concepts=(other_concept,))
    result = _enrich(tmp_path, catalog, _legacy_model())
    assert result.status == "abstained"
    assert ("observed_mapping_mismatch" in result.reasons) or result.reason == "no_evidence"
    assert result.assessment is not None
    assert result.assessment.rejected


@pytest.mark.parametrize(
    ("raw", "codes", "status", "reason", "value"),
    [
        ("  Café\t", ("Café", "Outro"), "proposed", None, "Café"),
        ("  Café\t", ("Café", "Outro"), "abstained", "no_matching_code", None),
        (" Café", ("Café",), "abstained", "no_matching_code", None),
        ("café", ("Café",), "abstained", "no_matching_code", None),
        ("Café\t", ("Café\t", "Café"), "abstained", "ambiguous_normalization", None),
        ("Café", ("Café",), "proposed", None, "Café"),
        ("ﬁ", ("fi",), "abstained", "no_matching_code", None),
    ],
)
def test_normalization_is_strict_nfc_and_ascii_whitespace_trim(
    tmp_path: Path,
    raw: str,
    codes: tuple[str, ...],
    status: str,
    reason: str | None,
    value: str | None,
) -> None:
    catalog = m.content(
        operation="normalize_code_nfc_trim",
        codes=codes,
        preconditions=("textual_enum", "unique_exact_code"),
    )
    model = ib.model()
    m.slab(model, ("SYN_Legado", "Metodo", raw, "IfcLabel"))
    result = _enrich(
        tmp_path, catalog, model, x.prop("SYN_Conjunto", "SYN_Metodo", value=x.enum(*codes))
    )

    assert (result.status, result.reason) == (status, reason)
    if value is not None:
        (alternative,) = result.alternatives
        assert alternative.value == TextValue(value=value)
        if raw == value:
            assert (alternative.method, alternative.transformation) == ("exact_recovery", None)
        else:
            assert alternative.method == "code_standardization"
            assert alternative.transformation == "normalize_code_nfc_trim@1.0.0"


def test_formal_states_other_than_non_compliant_are_routed_without_suggestion(
    tmp_path: Path,
) -> None:
    catalog = m.content(operation="normalize_code_nfc_trim", codes=("Café",))
    model = ib.model()
    m.slab(model, ("SYN_Conjunto", "SYN_Metodo", "Café", "IfcLabel"))
    compliant = _enrich(
        tmp_path / "a", catalog, model, x.prop("SYN_Conjunto", "SYN_Metodo", value=x.enum("Café"))
    )
    assert (compliant.status, compliant.reason) == ("not_requested", "already_satisfied")
    measure = _enrich(
        tmp_path / "b",
        catalog,
        model,
        x.prop("SYN_Conjunto", "SYN_Metodo", data_type="IFCLENGTHMEASURE"),
    )
    assert (measure.status, measure.reason) == ("unsupported", "formal_not_verified")


def test_enum_or_expected_value_is_never_evidence(tmp_path: Path) -> None:
    catalog = m.content(operation="normalize_code_nfc_trim", codes=("A", "B"))
    model = ib.model()
    m.slab(model)
    result = _enrich(
        tmp_path, catalog, model, x.prop("SYN_Conjunto", "SYN_Metodo", value=x.enum("A", "B"))
    )
    assert (result.status, result.reason) == ("abstained", "no_evidence")


def test_conflicts_are_checked_before_normalizing(tmp_path: Path) -> None:
    catalog = m.content(operation="normalize_code_nfc_trim", codes=("Café",))
    model = ib.model()
    element = m.slab(model, ("SYN_Conjunto", "SYN_Metodo", "  Café", "IfcLabel"))
    wall_type = ib.typed(model, element, "IfcSlabType")
    ib.pset(model, wall_type, "SYN_Conjunto", [ib.single(model, "SYN_Metodo", "IfcLabel", "Café ")])
    result = _enrich(
        tmp_path, catalog, model, x.prop("SYN_Conjunto", "SYN_Metodo", value=x.enum("Café"))
    )
    assert (result.status, result.reason) == ("abstained", "evidence_conflict")


def test_equal_values_from_identifiable_sources_keep_all_refs(tmp_path: Path) -> None:
    model = ib.model()
    element = m.slab(model, ("SYN_Legado", "Metodo", "A", "IfcLabel"))
    slab_type = ib.typed(model, element, "IfcSlabType")
    ib.pset(model, slab_type, "SYN_Legado", [ib.single(model, "Metodo", "IfcLabel", "A")])
    result = _enrich(tmp_path, m.content(), model)
    assert result.status == "proposed"
    assert len(result.alternatives[0].evidence_refs) == 2


def test_bool_int_and_text_observations_never_merge(tmp_path: Path) -> None:
    model = ib.model()
    element = m.slab(model, ("SYN_Legado", "Metodo", "1", "IfcLabel"))
    slab_type = ib.typed(model, element, "IfcSlabType")
    ib.pset(model, slab_type, "SYN_Legado", [ib.single(model, "Metodo", "IfcInteger", 1)])
    result = _enrich(tmp_path, m.content(), model)
    assert (result.status, result.reason) == ("abstained", "evidence_conflict")


@pytest.mark.parametrize(
    ("data_type", "status", "reason"),
    [
        ("IFCINTEGER", "unsupported", "unsupported_candidate_validation"),
        ("IFCLABEL", "abstained", "candidate_type_mismatch"),
    ],
)
def test_integer_observation_reaches_unsupported_candidate_validation(
    tmp_path: Path, data_type: str, status: str, reason: str
) -> None:
    result = _enrich(
        tmp_path,
        m.content(),
        _legacy_model(1, "IfcInteger"),  # type: ignore[arg-type]
        x.prop("SYN_Conjunto", "SYN_Metodo", data_type=data_type),
    )
    assert (result.status, result.reason) == (status, reason)


def test_candidate_outside_restriction_is_never_proposed(tmp_path: Path) -> None:
    result = _enrich(
        tmp_path,
        m.content(),
        _legacy_model("Z"),
        x.prop("SYN_Conjunto", "SYN_Metodo", value=x.enum("A", "B")),
    )
    assert (result.status, result.reason) == ("abstained", "candidate_violates_requirement")
    assert result.alternatives == ()


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"operation": "operacao_inexistente"}, "operation_unavailable"),
        ({"version": "2.0.0"}, "operation_version_mismatch"),
        ({"version": None}, "operation_unpinned"),
        ({"preconditions": ("precondicao_desconhecida",)}, "unsupported_precondition"),
        ({"preconditions": ("textual_enum",)}, "unsupported_precondition"),
        ({"preconditions": ("same_snapshot ",)}, "unsupported_precondition"),
        ({"channels": ("P", "Q")}, "unsupported_channel"),
        ({"scope": "type"}, "unsupported_target_scope"),
        ({"scope": "unspecified"}, "unsupported_target_scope"),
        ({"carrier_status": "pending_reconciliation"}, "pending_carrier"),
        ({"policy": False}, "policy_missing"),
    ],
)
def test_capability_policy_and_target_guards_refuse_before_any_handler(
    tmp_path: Path, changes: dict[str, object], reason: str
) -> None:
    result = _enrich(tmp_path, m.content(**changes), _legacy_model())  # type: ignore[arg-type]
    assert result.status == "unsupported"
    assert result.reason == reason
    assert result.alternatives == ()


def test_accepted_preconditions_are_exact_strings(tmp_path: Path) -> None:
    accepted = (
        "same_snapshot",
        "literal_property_single_value",
        "complete_search",
        "strict_typed_value",
        "compatible_unit",
        "no_conflict",
        "occurrence_target",
    )
    result = _enrich(tmp_path, m.content(preconditions=accepted), _legacy_model())
    assert result.status == "proposed"


@pytest.mark.parametrize("set_name", ["SYN_Conjunto", "SYN_Legado"])
def test_observation_with_other_ifc_type_is_never_proposed(tmp_path: Path, set_name: str) -> None:
    model = ib.model()
    m.slab(
        model, (set_name, "Metodo" if set_name == "SYN_Legado" else "SYN_Metodo", "A", "IfcText")
    )
    result = _enrich(tmp_path, m.content(), model)

    assert (result.status, result.reason) == ("abstained", "candidate_type_mismatch")
    assert result.alternatives == ()


def test_normalization_never_claims_satisfied_for_a_non_compliant_row(tmp_path: Path) -> None:
    catalog = m.content(
        operation="normalize_code_nfc_trim",
        codes=("Café", "Outro"),
        preconditions=("textual_enum", "unique_exact_code"),
    )
    model = ib.model()
    m.slab(model, ("SYN_Conjunto", "SYN_Metodo", "Café", "IfcLabel"))
    result = _enrich(
        tmp_path,
        catalog,
        model,
        x.prop("SYN_Conjunto", "SYN_Metodo", value=x.enum("CAFE", "OUTRO")),
    )

    assert (result.status, result.reason) == ("abstained", "candidate_violates_requirement")


def test_xml_comment_requirement_is_never_satisfied_by_the_truncated_prefix(
    tmp_path: Path,
) -> None:
    """E3-03 no caminho de proposta: exigência ``AB<!-- -->C`` é ``ABC``; ``AB`` não é proposto."""
    requirement = x.prop(
        "SYN_Conjunto", "SYN_Metodo", value="<simpleValue>AB<!-- comentário -->C</simpleValue>"
    )
    truncated = _enrich(tmp_path / "ab", m.content(), _legacy_model("AB"), requirement)
    assert truncated.status != "proposed"
    assert truncated.reason == "candidate_violates_requirement"
    full = _enrich(tmp_path / "abc", m.content(), _legacy_model("ABC"), requirement)
    assert (full.status, full.alternatives[0].value) == ("proposed", TextValue(value="ABC"))


def test_alternative_targets_the_literal_ids_path_not_the_filled_canonical(
    tmp_path: Path,
) -> None:
    """E3-04: IDS pede o alias literal ausente; o canônico preenchido não é o destino."""
    model = ib.model()
    m.slab(model, ("SYN_Conjunto", "SYN_Metodo", "A", "IfcLabel"))
    result = _enrich(tmp_path, m.content(), model, x.prop("SYN_Legado", "Metodo"))

    assert (result.field.target_set_name, result.field.target_field_name) == (
        "SYN_Legado",
        "Metodo",
    )
    assert result.status == "proposed"
    (alternative,) = result.alternatives
    assert (alternative.target_set_name, alternative.target_field_name) == ("SYN_Legado", "Metodo")
    assert alternative.target_binding_id == result.field.binding_id
    assert alternative.value == TextValue(value="A")


def test_result_refuses_alternative_for_a_target_other_than_the_field(tmp_path: Path) -> None:
    """E3-04: DTO recusa alternativa cujo destino difere do alvo literal do campo."""
    from pydantic import ValidationError

    result = _enrich(tmp_path, m.content(), _legacy_model())
    assert result.status == "proposed"
    forged = result.alternatives[0].model_copy(update={"target_set_name": "SYN_Outro"})
    with pytest.raises(ValidationError, match="alvo literal"):
        FieldEnrichmentResult.model_validate(
            {**result.model_dump(mode="json"), "alternatives": [forged.model_dump(mode="json")]}
        )


def _swapped_handlers(bundle: E3OperationBundle) -> dict:
    handlers = dict(bundle.handlers)
    handlers[("recover_exact_property", "1.0.0")] = handlers[("normalize_code_nfc_trim", "1.0.0")]
    return handlers


def test_bundle_factory_refuses_another_handler_under_the_same_key() -> None:
    """E3-05: chave de recuperação exata com o handler de normalização é recusada."""
    bundle = build_e3_operation_bundle()
    with pytest.raises(BundleError, match="handler"):
        E3OperationBundle.create(bundle.specs, _swapped_handlers(bundle))


def test_bundle_direct_construction_cannot_bypass_the_factory() -> None:
    """E3-05: o dataclass valida o conteúdo efetivo mesmo sem ``create``."""
    bundle = build_e3_operation_bundle()
    with pytest.raises(BundleError):
        E3OperationBundle(
            specs=bundle.specs,
            handlers=_swapped_handlers(bundle),
            registry=bundle.registry,
            manifest=bundle.manifest,
            manifest_sha256=bundle.manifest_sha256,
        )


def test_bundle_handlers_are_frozen_and_manifest_names_each_implementation() -> None:
    """E3-05: mapa fechado imutável; manifesto identifica a implementação de cada chave."""
    bundle = build_e3_operation_bundle()
    with pytest.raises(TypeError):
        bundle.handlers[("recover_exact_property", "1.0.0")] = None  # type: ignore[index]
    assert bundle.manifest["implementations"] == {
        "normalize_code_nfc_trim@1.0.0": (
            "src.suggestion_engine.catalog_operations:normalize_code_nfc_trim"
        ),
        "recover_exact_property@1.0.0": (
            "src.suggestion_engine.catalog_operations:recover_exact_property"
        ),
    }


@pytest.mark.parametrize(("lifecycle", "proposed"), [("approved", True), ("deprecated", False)])
def test_normalization_requires_an_approved_effective_enum(
    tmp_path: Path, lifecycle: str, proposed: bool
) -> None:
    """E3-08: enum ``deprecated`` não autoriza normalização; ``approved`` é o controle."""
    catalog = m.content(operation="normalize_code_nfc_trim", codes=("A",))
    value_set = catalog.value_sets[0].model_copy(update={"lifecycle": lifecycle})
    catalog = catalog.model_copy(update={"value_sets": (value_set,)})
    result = _enrich(tmp_path, catalog, _legacy_model(" A "))
    if proposed:
        assert (result.status, result.alternatives[0].value) == ("proposed", TextValue(value="A"))
    else:
        assert (result.status, result.reason) == ("abstained", "unapproved_content")
        assert result.alternatives == ()
