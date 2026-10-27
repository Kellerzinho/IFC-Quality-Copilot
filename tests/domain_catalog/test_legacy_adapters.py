"""Projeção contextual sobre pacotes exclusivamente sintéticos."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

import pytest

from src.domain_catalog.content import CatalogContent
from src.domain_catalog.contracts import BindingRequest
from src.domain_catalog.models import AllowedValue, AllowedValueSet, ConceptDefinition, IFCBinding
from src.domain_catalog.reader import CatalogReader, open_catalog
from tests.domain_catalog import factories as f

if TYPE_CHECKING:
    from src.domain_catalog.adapters import ScopedLocalCatalogAdapter


def request(**changes: object) -> BindingRequest:
    """Requisito sintético explícito, sem inferência de entidade ou conjunto."""
    data: dict[str, object] = dict(
        ifc_schema="IFC4",
        facet="property",
        set_name="SYN_Conjunto",
        field_name="SYN_Metodo",
        entity="IfcSlab",
    )
    data.update(changes)
    return BindingRequest.model_validate(data)


@pytest.fixture
def reader(tmp_path: Path) -> CatalogReader:
    """Abre pacote sintético real, com manifesto e hashes verificados."""
    ref, folder = f.write_synthetic_release(tmp_path, f.minimal_content())
    return open_catalog(ref, folder)


def test_scope_rejects_reader_from_another_release(reader: CatalogReader) -> None:
    from src.domain_catalog.adapters import build_catalog_projection
    from src.domain_catalog.errors import CatalogProjectionError
    from src.domain_catalog.projection_contracts import ProjectionScope

    other = reader.ref.model_copy(update={"manifest_sha256": "f" * 64})
    with pytest.raises(CatalogProjectionError) as caught:
        build_catalog_projection(reader, ProjectionScope(catalog=other, request=request()))
    assert caught.value.reason == "release_mismatch"
    assert caught.value.catalog == other
    assert caught.value.resolution is None


@pytest.mark.parametrize("missing", ["entity", "set_name"])
def test_property_projection_requires_entity_and_set(reader: CatalogReader, missing: str) -> None:
    from src.domain_catalog.adapters import build_catalog_projection
    from src.domain_catalog.errors import CatalogProjectionError
    from src.domain_catalog.projection_contracts import ProjectionScope

    scope = ProjectionScope(catalog=reader.ref, request=request(**{missing: None}))
    with pytest.raises(CatalogProjectionError) as caught:
        build_catalog_projection(reader, scope)
    assert getattr(scope.request, missing) is None
    assert caught.value.reason == "insufficient_context"
    assert caught.value.resolution is None


def test_projection_keeps_resolution_request_and_release(reader: CatalogReader) -> None:
    from src.domain_catalog.adapters import build_catalog_projection
    from src.domain_catalog.projection_contracts import ProjectionScope

    scope = ProjectionScope(catalog=reader.ref, request=request())
    result = build_catalog_projection(reader, scope)
    assert result.scope == scope
    assert result.resolution == reader.resolve_binding(scope.request)
    assert result.resolution.catalog is not None
    assert result.resolution.catalog.catalog_id == f.SYN_CATALOG_ID
    assert result.resolution.request.ifc_schema == "IFC4"
    assert result.binding.id == f.BINDING_ID
    assert result.concept.id == f.CONCEPT_ID
    assert result.source_assertions[0].id == f.SYN_ASSERTION_ID
    assert result.source_artifacts[0].id == f.SYN_SOURCE_ID


def test_unresolved_projection_retains_candidates_and_reasons(tmp_path: Path) -> None:
    from src.domain_catalog.adapters import build_catalog_projection
    from src.domain_catalog.errors import CatalogProjectionError
    from src.domain_catalog.projection_contracts import ProjectionScope

    ref, folder = f.write_synthetic_release(tmp_path)
    reader = open_catalog(ref, folder)
    req = request(field_name="Metodo")
    expected = reader.resolve_binding(req)
    with pytest.raises(CatalogProjectionError) as caught:
        build_catalog_projection(reader, ProjectionScope(catalog=ref, request=req))
    assert caught.value.reason == "unresolved_binding"
    assert caught.value.resolution == expected
    assert expected.status == "ambiguous"
    assert len(expected.candidates) == 2
    assert expected.reasons


def adapter_for(reader: CatalogReader, **changes: object) -> ScopedLocalCatalogAdapter:
    """Adaptador opt-in do uso sintético exato."""
    from src.domain_catalog.adapters import ScopedLocalCatalogAdapter
    from src.domain_catalog.projection_contracts import ProjectionScope

    return ScopedLocalCatalogAdapter(
        reader, ProjectionScope(catalog=reader.ref, request=request(**changes))
    )


def open_content(tmp_path: Path, content: CatalogContent) -> CatalogReader:
    """Grava e reabre pacote sintético com validações de conteúdo ativas."""
    ref, folder = f.write_synthetic_release(tmp_path, content)
    return open_catalog(ref, folder)


def typed_content(code: str | int | bool) -> CatalogContent:
    """Uma opção tipada; cada caso distingue 1, True e texto 1."""
    kind: Literal["boolean", "integer", "code"] = (
        "boolean" if type(code) is bool else "integer" if type(code) is int else "code"
    )
    ifc = {"boolean": "IfcBoolean", "integer": "IfcInteger", "code": "IfcLabel"}[kind]
    return f.minimal_content().model_copy(
        update={
            "value_sets": (
                AllowedValueSet(
                    id=f.VALUE_SET_ID,
                    value_type=kind,
                    values=(AllowedValue(code=code),),
                    lifecycle="approved",
                ),
            ),
            "concepts": (
                ConceptDefinition.model_validate(
                    {**f.concept().model_dump(), "logical_type": kind}
                ),
            ),
            "bindings": (IFCBinding.model_validate({**f.binding().model_dump(), "ifc_type": ifc}),),
        }
    )


def test_all_six_methods_share_the_exact_binding(reader: CatalogReader) -> None:
    from src.foundation.contracts import SemanticCatalog

    adapter = adapter_for(reader)
    assert isinstance(adapter, SemanticCatalog)
    classes = adapter.search_classes_text("ifcslab")
    assert len(classes) == 1
    class_uri = classes[0].class_uri
    assert class_uri is not None
    metadata = adapter.get_class_metadata(class_uri)
    assert metadata == classes[0]
    assert metadata.canonical_uri is None
    assert metadata.source_origin == "local_snapshot"
    assert metadata.status == "resolved"
    assert metadata.dictionary_uri == f.SYN_CATALOG_ID
    assert metadata.dictionary_name == "Catálogo sintético de teste"
    assert (
        metadata.description
        == "Agrupamento local de usos do catálogo para IfcSlab; não é definição oficial IFC/bSDD."
    )
    plain = adapter.search_class("IfcSlab")
    assert plain[0]["uri"] == metadata.class_uri
    prop = adapter.resolve_property(f.BINDING_ID)
    assert prop.property_uri == f.BINDING_ID
    assert prop.display_name == prop.code == "SYN_Metodo"
    assert prop.canonical_uri is None
    assert prop.source_origin == "local_snapshot"
    assert metadata.class_uri is not None
    legacy = adapter.get_class_properties(metadata.class_uri)
    assert len(legacy) == 1
    assert legacy[0].uri == f.BINDING_ID
    assert legacy[0].name == legacy[0].code == "SYN_Metodo"
    assert legacy[0].data_type == "IfcLabel"
    assert (
        legacy[0].allowed_values
        == prop.allowed_values
        == adapter.get_property_values(f.BINDING_ID)
        == ["A", "B"]
    )
    assert adapter.search_class("") == plain
    assert adapter.search_class("Slab") == []


def test_local_names_and_urns_are_not_canonicalized(tmp_path: Path) -> None:
    import hashlib

    from src.domain_catalog.canonical import canonical_json_bytes

    content = f.minimal_content().model_copy(
        update={"bindings": (f.binding().model_copy(update={"field_name": "Tipo_Revestimento_Á"}),)}
    )
    adapter = adapter_for(open_content(tmp_path, content), field_name="Tipo_Revestimento_Á")
    scope = adapter.projection().scope
    expected = (
        "urn:ifc-quality-copilot:local-class:"
        + hashlib.sha256(canonical_json_bytes(scope.model_dump(mode="json"))).hexdigest()
    )
    assert adapter.search_class("")[0]["uri"] == expected
    prop = adapter.get_class_properties(expected)[0]
    assert prop.name == prop.code == "Tipo_Revestimento_Á"
    assert prop.uri == f.BINDING_ID


def test_local_value_restriction_does_not_leak_global_options(tmp_path: Path) -> None:
    local_id = "urn:uuid:00000000-0000-4000-8000-000000000099"
    local = f.value_set().model_copy(
        update={
            "id": local_id,
            "restricts_value_set_id": f.VALUE_SET_ID,
            "values": (AllowedValue(code="B"),),
        }
    )
    content = f.minimal_content().model_copy(
        update={
            "value_sets": (f.value_set(), local),
            "bindings": (f.binding().model_copy(update={"value_set_id": local_id}),),
        }
    )
    adapter = adapter_for(open_content(tmp_path, content))
    assert adapter.get_property_values(f.BINDING_ID) == ["B"]
    assert adapter.projection().effective_value_set == local


def test_same_name_in_another_set_is_not_selected(tmp_path: Path) -> None:
    other = f.binding().model_copy(
        update={"id": "urn:uuid:00000000-0000-4000-8000-000000000098", "set_name": "SYN_Outro"}
    )
    reader = open_content(
        tmp_path, f.minimal_content().model_copy(update={"bindings": (f.binding(), other)})
    )
    assert adapter_for(reader).projection().binding.id == f.BINDING_ID
    assert adapter_for(reader, set_name="SYN_Outro").projection().binding.id == other.id


@pytest.mark.parametrize(
    ("changes", "status"),
    [
        ({"field_name": "Metodo"}, "ambiguous"),
        ({"field_name": "SYN_Bloco", "entity": "IfcWall"}, "ambiguous"),
        ({"ifc_schema": "IFC2X3"}, "unsupported"),
    ],
)
def test_ambiguous_and_indeterminate_uses_are_not_first_match(
    tmp_path: Path, changes: dict[str, str], status: str
) -> None:
    from src.domain_catalog.errors import CatalogProjectionError

    adapter = adapter_for(open_content(tmp_path, f.resolution_content()), **changes)
    with pytest.raises(CatalogProjectionError) as caught:
        adapter.get_property_values(f.R.B_METODO_SLAB)
    assert caught.value.reason == "unresolved_binding"
    assert caught.value.resolution is not None
    assert caught.value.resolution.status == status
    assert caught.value.resolution.candidates


@pytest.mark.parametrize("code", [1, True, "1"])
def test_non_text_codes_refuse_legacy_value_projection(
    tmp_path: Path, code: str | int | bool
) -> None:
    from src.domain_catalog.errors import CatalogProjectionError

    adapter = adapter_for(open_content(tmp_path, typed_content(code)))
    value_set = adapter.projection().effective_value_set
    assert value_set is not None
    assert type(value_set.values[0].code) is type(code)
    if type(code) is str:
        assert adapter.get_property_values(f.BINDING_ID) == ["1"]
    else:
        for action in (
            lambda: adapter.get_property_values(f.BINDING_ID),
            lambda: adapter.resolve_property(f.BINDING_ID),
            lambda: adapter.get_class_properties(adapter.search_class("")[0]["uri"]),
        ):
            with pytest.raises(CatalogProjectionError, match="unrepresentable_enum"):
                action()


@pytest.mark.parametrize(
    ("field", "entity", "set_name"),
    [("SYN_AreaPendente", "IfcSlab", "SYN_Conjunto"), ("Height", "IfcWall", "SYN_Qto")],
)
def test_pending_or_quantity_carrier_refuses_property_projection(
    tmp_path: Path, field: str, entity: str, set_name: str
) -> None:
    from src.domain_catalog.errors import CatalogProjectionError

    adapter = adapter_for(
        open_content(tmp_path, f.resolution_content()),
        field_name=field,
        entity=entity,
        set_name=set_name,
    )
    rich = adapter.projection()
    with pytest.raises(CatalogProjectionError, match="unsupported_carrier"):
        adapter.get_property_values(rich.binding.id)
    assert rich.resolution.binding_id == rich.binding.id


def test_foreign_binding_and_class_references_are_rejected(reader: CatalogReader) -> None:
    from src.domain_catalog.errors import CatalogProjectionError

    adapter = adapter_for(reader)
    for action in (
        lambda: adapter.resolve_property(f.CONCEPT_ID),
        lambda: adapter.get_property_values(f.CONCEPT_ID),
        lambda: adapter.get_class_metadata("IfcSlab"),
        lambda: adapter.get_class_properties("IfcSlab"),
    ):
        with pytest.raises(CatalogProjectionError, match="foreign_reference"):
            action()
    with pytest.raises(CatalogProjectionError, match="unsupported_domain"):
        adapter.search_class("", domain="OTHER")


def test_all_enum_values_and_labels_remain_in_rich_projection(tmp_path: Path) -> None:
    values = tuple(AllowedValue(code=f"Á{i}", labels=f.pt(f"Rótulo {i}")) for i in range(20))
    content = f.minimal_content().model_copy(
        update={
            "value_sets": (f.value_set().model_copy(update={"values": values, "ordered": True}),)
        }
    )
    adapter = adapter_for(open_content(tmp_path, content))
    assert adapter.get_property_values(f.BINDING_ID) == [f"Á{i}" for i in range(20)]
    rich = adapter.projection()
    assert rich.effective_value_set is not None
    assert rich.effective_value_set.values == values
    assert rich.effective_value_set.ordered is True
    assert any("legad" in line for line in rich.limitations)


def test_language_fallback_and_absence_are_explicit(reader: CatalogReader, tmp_path: Path) -> None:
    from src.domain_catalog.adapters import ScopedLocalCatalogAdapter
    from src.domain_catalog.projection_contracts import ProjectionScope

    adapter = ScopedLocalCatalogAdapter(
        reader, ProjectionScope(catalog=reader.ref, request=request(), language="en")
    )
    assert adapter.resolve_property(f.BINDING_ID).description == f.concept().definition[0].text
    assert any("pt-BR" in line and "en" in line for line in adapter.projection().limitations)
    from src.domain_catalog.models import LocalizedText

    content = f.minimal_content().model_copy(
        update={
            "concepts": (
                f.concept().model_copy(
                    update={"definition": (LocalizedText(lang="fr", text="Définition"),)}
                ),
            )
        }
    )
    other = adapter_for(open_content(tmp_path / "other", content))
    assert other.resolve_property(f.BINDING_ID).description is None
    assert any("definição ausente" in line for line in other.projection().limitations)


def test_approved_alias_preserves_all_aliases_and_both_paths(tmp_path: Path) -> None:
    content = f.resolution_content()
    aliases = tuple(
        a.model_copy(update={"target_binding_id": f.R.B_METODO_SLAB})
        if a.id == f.R.ALIAS_METODO_2
        else a
        for a in content.aliases
    )
    adapter = adapter_for(
        open_content(tmp_path, content.model_copy(update={"aliases": aliases})), field_name="Metodo"
    )
    projection = adapter.projection()
    assert projection.resolution.status == "approved_mapping"
    assert set(projection.resolution.alias_ids) == {f.R.ALIAS_METODO_1, f.R.ALIAS_METODO_2}
    assert projection.scope.request.field_name == "Metodo"
    assert projection.binding.field_name == "SYN_Metodo"
    assert adapter.resolve_property(f.R.B_METODO_SLAB).display_name == "SYN_Metodo"


def test_unit_policy_and_unspecified_scope_do_not_enable_operations(tmp_path: Path) -> None:
    from src.domain_catalog.models import EvidencePolicy

    policy_id = "urn:uuid:00000000-0000-4000-8000-000000000097"
    policy = EvidencePolicy(
        id=policy_id,
        operation_id="synthetic.read",
        operation_version="1",
        admissible_channels=("P",),
        on_missing="abstain",
        on_conflict="abstain",
        lifecycle="approved",
        source_assertion_ids=(f.SYN_ASSERTION_ID,),
    )
    concept = f.concept().model_copy(
        update={
            "logical_type": "decimal",
            "dimension": "length",
            "unit_id": f.UNIT_ID,
            "value_set_id": None,
        }
    )
    binding = f.binding().model_copy(
        update={
            "ifc_type": "IfcLengthMeasure",
            "scope": "unspecified",
            "evidence_policy_id": policy_id,
        }
    )
    content = f.minimal_content().model_copy(
        update={
            "concepts": (concept,),
            "bindings": (binding,),
            "units": (f.length_unit(),),
            "evidence_policies": (policy,),
            "value_sets": (),
        }
    )
    adapter = adapter_for(open_content(tmp_path, content))
    assert adapter.resolve_property(f.BINDING_ID).unit == "m"
    assert adapter.resolve_property(f.BINDING_ID).allowed_values is None
    assert adapter.get_property_values(f.BINDING_ID) == []
    projection = adapter.projection()
    assert projection.evidence_policy == policy
    assert projection.capability is not None
    assert projection.capability.status == "unsupported"
    assert projection.binding.scope == "unspecified"
    assert projection.binding.write_enabled is False
    assert any("Operação indisponível" in text for text in projection.limitations)


def test_projection_rejects_swapped_scope_or_selected_binding(reader: CatalogReader) -> None:
    from pydantic import ValidationError

    from src.domain_catalog.projection_contracts import CatalogProjection

    projection = adapter_for(reader).projection()
    data = projection.model_dump()
    data["scope"]["catalog"]["manifest_sha256"] = "f" * 64
    with pytest.raises(ValidationError, match="release"):
        CatalogProjection.model_validate(data)
    data = projection.model_dump()
    data["binding"]["id"] = f.CONCEPT_ID
    with pytest.raises(ValidationError, match="escolhidos"):
        CatalogProjection.model_validate(data)
