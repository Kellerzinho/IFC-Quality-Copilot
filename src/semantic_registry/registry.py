"""Registro central das fontes oficiais e politica padrao do projeto."""

from __future__ import annotations

from src.semantic_registry.resolver import CanonicalURIResolver
from src.semantic_registry.source_policy import SourcePolicy, SourceRecord

OFFICIAL_SOURCE_RECORDS: list[SourceRecord] = [
    SourceRecord(
        name="buildingSMART Identifier",
        category="official",
        owner="buildingSMART",
        base_url="https://identifier.buildingsmart.org/",
        default_reference_kind="canonical_uri",
    ),
    SourceRecord(
        name="buildingSMART IFC Canonical URIs",
        category="official",
        owner="buildingSMART",
        base_url="https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3",
        default_reference_kind="canonical_uri",
    ),
    SourceRecord(
        name="buildingSMART IFC Docs",
        category="official",
        owner="buildingSMART",
        base_url="https://ifc43-docs.standards.buildingsmart.org/",
        default_reference_kind="documentation",
    ),
    SourceRecord(
        name="buildingSMART bSDD Search",
        category="official",
        owner="buildingSMART",
        base_url="https://search.bsdd.buildingsmart.org/",
        default_reference_kind="discovery",
    ),
    SourceRecord(
        name="buildingSMART bSDD GraphQL",
        category="official",
        owner="buildingSMART",
        base_url="https://api.bsdd.buildingsmart.org/",
        default_reference_kind="api",
    ),
    SourceRecord(
        name="buildingSMART IDS Repository",
        category="official",
        owner="buildingSMART",
        base_url="https://github.com/buildingSMART/IDS",
        default_reference_kind="repository",
    ),
    SourceRecord(
        name="IfcOpenShell Docs",
        category="official",
        owner="IfcOpenShell",
        base_url="https://docs.ifcopenshell.org/",
        default_reference_kind="documentation",
    ),
    SourceRecord(
        name="buildingSMART BCF API Repository",
        category="official",
        owner="buildingSMART",
        base_url="https://github.com/buildingSMART/BCF-API",
        default_reference_kind="repository",
    ),
    SourceRecord(
        name="buildingSMART BCF XML Repository",
        category="official",
        owner="buildingSMART",
        base_url="https://github.com/buildingSMART/BCF-XML",
        default_reference_kind="repository",
    ),
]

DEFAULT_SOURCE_POLICY = SourcePolicy(OFFICIAL_SOURCE_RECORDS)
DEFAULT_SEMANTIC_REGISTRY = CanonicalURIResolver(DEFAULT_SOURCE_POLICY)
