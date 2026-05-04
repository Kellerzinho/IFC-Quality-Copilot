"""Registries centrais para entidades e categorias de dados IFC."""

from src.ifc_registry.registry import (
    DEFAULT_IFC_DATA_REGISTRY,
    IfcDataRegistry,
    IfcEntityDefinition,
    IfcNamedResource,
    create_default_ifc_data_registry,
)

__all__ = [
    "DEFAULT_IFC_DATA_REGISTRY",
    "IfcDataRegistry",
    "IfcEntityDefinition",
    "IfcNamedResource",
    "create_default_ifc_data_registry",
]
