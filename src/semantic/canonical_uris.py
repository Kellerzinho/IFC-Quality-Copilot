"""Compatibilidade legada para o resolver semantico central."""

from src.semantic_registry.resolver import (
    IFC_CANONICAL_BASE_URI,
    build_ifc_class_uri,
    build_ifc_property_uri,
    is_canonical_ifc_class_uri,
    is_canonical_ifc_property_uri,
    is_ifc_class_name,
    is_ifc_property_name,
    prefer_canonical_ifc_class_uri,
    prefer_canonical_ifc_property_uri,
)

__all__ = [
    "IFC_CANONICAL_BASE_URI",
    "build_ifc_class_uri",
    "build_ifc_property_uri",
    "is_canonical_ifc_class_uri",
    "is_canonical_ifc_property_uri",
    "is_ifc_class_name",
    "is_ifc_property_name",
    "prefer_canonical_ifc_class_uri",
    "prefer_canonical_ifc_property_uri",
]
