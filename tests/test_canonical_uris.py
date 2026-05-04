"""Testes para URIs canonicas IFC em identifier.buildingsmart.org."""

from src.semantic.canonical_uris import (
    build_ifc_class_uri,
    build_ifc_property_uri,
    is_canonical_ifc_class_uri,
    is_canonical_ifc_property_uri,
    prefer_canonical_ifc_class_uri,
    prefer_canonical_ifc_property_uri,
)


def test_build_ifc_class_uri() -> None:
    assert build_ifc_class_uri("IfcWall") == (
        "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/class/IfcWall"
    )


def test_build_ifc_property_uri() -> None:
    assert build_ifc_property_uri("ThermalTransmittance") == (
        "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/prop/ThermalTransmittance"
    )


def test_prefer_canonical_ifc_class_uri_over_external_uri() -> None:
    assert prefer_canonical_ifc_class_uri("IfcDoor", "https://example.org/class/ifcdoor") == (
        "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/class/IfcDoor"
    )


def test_prefer_canonical_ifc_property_uri_over_external_uri() -> None:
    assert prefer_canonical_ifc_property_uri("FireRating", "https://example.org/prop/firerating") == (
        "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/prop/FireRating"
    )


def test_invalid_names_do_not_invent_canonical_uris() -> None:
    assert build_ifc_class_uri("Wall") is None
    assert build_ifc_property_uri("Fire Rating") is None


def test_canonical_uri_detectors() -> None:
    assert is_canonical_ifc_class_uri(
        "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/class/IfcWall"
    )
    assert is_canonical_ifc_property_uri(
        "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/prop/FireRating"
    )
