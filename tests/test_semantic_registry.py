"""Testes da camada central de resolucao semantica."""

from src.semantic_registry.registry import DEFAULT_SEMANTIC_REGISTRY


def test_resolve_ifc_class_returns_canonical_identifier() -> None:
    result = DEFAULT_SEMANTIC_REGISTRY.resolve_ifc_class("IfcWall")

    assert result is not None
    assert result.subject_type == "ifc_class"
    assert result.canonical_uri == "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/class/IfcWall"
    assert result.reference_kind == "canonical_uri"
    assert result.status == "resolved"


def test_resolve_ifc_property_returns_canonical_identifier() -> None:
    result = DEFAULT_SEMANTIC_REGISTRY.resolve_ifc_property("FireRating")

    assert result is not None
    assert result.subject_type == "ifc_property"
    assert result.canonical_uri == "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/prop/FireRating"
    assert result.reference_kind == "canonical_uri"


def test_resolve_pset_returns_documented_only_reference() -> None:
    result = DEFAULT_SEMANTIC_REGISTRY.resolve_pset("Pset_WallCommon")

    assert result is not None
    assert result.subject_type == "ifc_pset"
    assert result.canonical_uri is None
    assert result.reference_kind == "documentation"
    assert result.status == "documented_only"


def test_resolve_invalid_pset_returns_none() -> None:
    assert DEFAULT_SEMANTIC_REGISTRY.resolve_pset("WallCommon") is None
