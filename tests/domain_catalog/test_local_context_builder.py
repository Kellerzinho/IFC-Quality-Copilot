"""Percurso E3.1 real com pacotes sintéticos; nenhuma inferência ou publicação real."""

from __future__ import annotations

import socket
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from src.domain_catalog.contracts import PredefinedTypeContext
from src.domain_catalog.errors import CatalogPackageError, CatalogProjectionError
from src.domain_catalog.reader import CatalogReader, open_catalog
from tests.domain_catalog import factories as f
from tests.domain_catalog.test_legacy_adapters import (
    adapter_for,
    open_content,
    request,
    typed_content,
)

if TYPE_CHECKING:
    from src.domain_catalog.context_builder import LocalCatalogContextBuilder


def builder(reader: CatalogReader) -> LocalCatalogContextBuilder:
    """Construtor local com referência explícita do reader real."""
    from src.domain_catalog.context_builder import LocalCatalogContextBuilder

    return LocalCatalogContextBuilder(reader, catalog=reader.ref)


def test_real_local_builder_emits_nonempty_pinned_context(tmp_path: Path) -> None:
    reader = open_content(tmp_path, f.minimal_content())
    result = builder(reader).build(request())
    assert result.status == "available"
    assert result.condition_id == "m1-local-context-v1"
    assert result.source_origin == "local_snapshot"
    assert result.error_reason is None
    assert result.scope.catalog == reader.ref
    assert result.scope.catalog.catalog_id == f.SYN_CATALOG_ID
    assert result.resolution is not None
    assert result.resolution.catalog == reader.ref
    assert result.resolution is not None
    assert result.resolution.request.ifc_schema == "IFC4"
    assert len(result.properties) == 1
    assert result.properties[0].uri == f.BINDING_ID
    assert result.properties[0].allowed_values == ("A", "B")
    assert result.projection is not None
    assert result.projection.binding.write_enabled is False
    assert result.projection is not None
    assert result.projection.capability is None
    assert result.projection is not None
    assert result.projection.source_assertions[0].id == f.SYN_ASSERTION_ID
    assert result.limitations


def test_unknown_property_preserves_unmapped_and_no_context(tmp_path: Path) -> None:
    reader = open_content(tmp_path, f.minimal_content())
    result = builder(reader).build(request(field_name="Unknown"))
    assert result.status == "unavailable"
    assert result.error_reason == "unresolved_binding"
    assert result.resolution is not None
    assert result.resolution.status == "unmapped"
    assert result.projection is None
    assert result.properties == ()


def test_ambiguity_keeps_candidates_and_blocks_context(tmp_path: Path) -> None:
    reader = open_content(tmp_path, f.resolution_content())
    result = builder(reader).build(request(field_name="Metodo"))
    assert result.status == "unavailable"
    assert result.resolution is not None
    assert result.resolution.status == "ambiguous"
    assert result.resolution is not None
    assert {c.binding_id for c in result.resolution.candidates} == {
        f.R.B_METODO_SLAB,
        f.R.B_SO_IFC4,
    }
    assert result.properties == ()


def test_effective_predefined_type_and_missing_fact_are_preserved(tmp_path: Path) -> None:
    reader = open_content(tmp_path, f.resolution_content())
    pt = PredefinedTypeContext.determined("FLOORING", "type")
    req = request(field_name="SYN_Acabamento", entity="IfcCovering", predefined_type=pt)
    result = builder(reader).build(req)
    assert result.status == "available"
    assert result.resolution is not None
    assert result.resolution.binding_id == f.R.B_ACAB_PISO
    assert result.scope.request.predefined_type is not None
    assert result.scope.request.predefined_type.effective_origin == "type"
    missing = builder(reader).build(request(field_name="SYN_Bloco", entity="IfcWall"))
    assert missing.status == "unavailable"
    assert missing.resolution is not None
    assert missing.resolution.candidates[0].applicability == "indeterminate"
    assert missing.resolution is not None
    assert missing.resolution.reasons
    assert dict(missing.scope.request.facts) == {}


@pytest.mark.parametrize("code", [1, True])
def test_typed_enum_remains_rich_but_legacy_context_is_unavailable(
    tmp_path: Path, code: int | bool
) -> None:
    reader = open_content(tmp_path, typed_content(code))
    result = builder(reader).build(request())
    assert result.status == "unavailable"
    assert result.error_reason == "unrepresentable_enum"
    assert result.resolution is not None
    assert result.resolution.status == "exact"
    assert result.projection is not None
    assert result.projection is not None
    assert result.projection.effective_value_set is not None
    assert type(result.projection.effective_value_set.values[0].code) is type(code)
    assert result.properties == ()


@pytest.mark.parametrize("missing", ["entity", "set_name"])
def test_incomplete_request_preserves_scope_without_fabricating_resolution(
    tmp_path: Path, missing: str
) -> None:
    reader = open_content(tmp_path, f.minimal_content())
    req = request(**{missing: None})
    result = builder(reader).build(req)
    assert result.scope.request == req
    assert result.status == "unavailable"
    assert result.error_reason == "insufficient_context"
    assert result.resolution is None
    assert result.projection is None
    assert result.properties == ()


def test_package_error_does_not_become_empty_context(tmp_path: Path) -> None:
    # Importar a API antes de abrir demonstra que a falha interrompe a composição.
    from src.domain_catalog.context_builder import LocalCatalogContextBuilder

    ref, folder = f.write_synthetic_release(tmp_path, f.minimal_content())
    (folder / "manifest.json").write_bytes(b"tampered")
    with pytest.raises(CatalogPackageError):
        LocalCatalogContextBuilder(open_catalog(ref, folder), catalog=ref).build(request())
    with pytest.raises(CatalogPackageError):
        LocalCatalogContextBuilder(open_catalog(ref, tmp_path / "missing"), catalog=ref).build(
            request()
        )


def test_two_refs_cannot_share_a_context(tmp_path: Path) -> None:
    from src.domain_catalog.context_builder import LocalCatalogContextBuilder

    first = open_content(tmp_path / "a", f.minimal_content())
    ref, folder = f.write_synthetic_release(tmp_path / "b", f.minimal_content(), version="1.0.1")
    second = open_catalog(ref, folder)
    with pytest.raises(CatalogProjectionError, match="release_mismatch"):
        LocalCatalogContextBuilder(first, catalog=ref)
    assert (
        builder(first).build(request()).scope.catalog
        != builder(second).build(request()).scope.catalog
    )
    assert (
        adapter_for(first).search_class("")[0]["uri"]
        != adapter_for(second).search_class("")[0]["uri"]
    )


def test_local_builder_never_calls_network_or_semantic_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    from src.bsdd.client import BSDDClient
    from src.bsdd.context_builder import BSDDContextBuilder
    from src.domain_catalog.context_builder import LocalCatalogContextBuilder
    from src.semantic_registry.resolver import CanonicalURIResolver

    reader = open_content(tmp_path, f.minimal_content())

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("chamada externa/legada proibida")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(httpx.Client, "request", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden)
    monkeypatch.setattr(BSDDClient, "__init__", forbidden)
    monkeypatch.setattr(BSDDContextBuilder, "__init__", forbidden)
    # O caminho opt-in pode importar módulos legados, mas não os pode executar.
    monkeypatch.setattr(CanonicalURIResolver, "resolve_ifc_class", forbidden)
    monkeypatch.setattr(CanonicalURIResolver, "resolve_ifc_property", forbidden)
    monkeypatch.setattr(CanonicalURIResolver, "resolve_pset", forbidden)
    result = LocalCatalogContextBuilder(reader, catalog=reader.ref).build(request())
    assert result.status == "available"
    assert result.properties[0].allowed_values == ("A", "B")


def test_context_is_deeply_immutable_and_legacy_returns_are_independent(tmp_path: Path) -> None:
    reader = open_content(tmp_path, f.minimal_content())
    context = builder(reader).build(request())
    with pytest.raises(ValidationError):
        context.properties[0].name = "Changed"
    assert context.projection is not None
    with pytest.raises(ValidationError):
        context.projection.binding.field_name = "Changed"
    with pytest.raises(TypeError):
        context.scope.request.facts["construction_system"] = "changed"  # type: ignore[index]
    adapter = adapter_for(reader)
    uri = adapter.search_class("")[0]["uri"]
    first = adapter.get_class_properties(uri)
    assert first[0].allowed_values is not None
    first[0].allowed_values.append("INJECTED")
    first[0].name = "Changed"
    adapter.get_property_values(f.BINDING_ID).append("INJECTED")
    assert adapter.get_class_properties(uri)[0].allowed_values == ["A", "B"]
    assert adapter.resolve_property(f.BINDING_ID).display_name == "SYN_Metodo"
    assert builder(reader).build(request()) == context


def test_context_rejects_incoherent_identity_or_status(tmp_path: Path) -> None:
    from src.domain_catalog.projection_contracts import LocalCatalogContext

    result = builder(open_content(tmp_path, f.minimal_content())).build(request())
    for changes in (
        {"error_reason": "unresolved_binding"},
        {"projection": None},
        {"resolution": None},
        {"properties": ()},
        {"status": "unavailable"},
    ):
        with pytest.raises(ValidationError):
            LocalCatalogContext.model_validate({**result.model_dump(), **changes})


def test_unexpected_failure_propagates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reader = open_content(tmp_path, f.minimal_content())
    local = builder(reader)

    def broken(*args: object) -> None:
        raise RuntimeError("technical failure")

    monkeypatch.setattr(reader, "resolve_binding", broken)
    with pytest.raises(RuntimeError, match="technical failure"):
        local.build(request())
