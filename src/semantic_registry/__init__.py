"""Camada central de politica de fontes e resolucao semantica canonica."""

from src.semantic_registry.registry import (
    DEFAULT_SEMANTIC_REGISTRY,
    DEFAULT_SOURCE_POLICY,
    OFFICIAL_SOURCE_RECORDS,
)
from src.semantic_registry.resolver import (
    IFC_CANONICAL_BASE_URI,
    SemanticReference,
    build_ifc_class_uri,
    build_ifc_property_uri,
    is_canonical_ifc_class_uri,
    is_canonical_ifc_property_uri,
    is_ifc_class_name,
    is_ifc_property_name,
    is_pset_name,
    prefer_canonical_ifc_class_uri,
    prefer_canonical_ifc_property_uri,
)
from src.semantic_registry.source_policy import SourceRecord, URLClassification

__all__ = [
    "DEFAULT_SEMANTIC_REGISTRY",
    "DEFAULT_SOURCE_POLICY",
    "IFC_CANONICAL_BASE_URI",
    "OFFICIAL_SOURCE_RECORDS",
    "SemanticReference",
    "SourceRecord",
    "URLClassification",
    "build_ifc_class_uri",
    "build_ifc_property_uri",
    "is_canonical_ifc_class_uri",
    "is_canonical_ifc_property_uri",
    "is_ifc_class_name",
    "is_ifc_property_name",
    "is_pset_name",
    "prefer_canonical_ifc_class_uri",
    "prefer_canonical_ifc_property_uri",
]
