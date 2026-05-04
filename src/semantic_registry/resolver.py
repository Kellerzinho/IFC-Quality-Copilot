"""Resolvedor central para referencias semanticas IFC e politica de URIs."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.semantic_registry.source_policy import SourcePolicy

IFC_CANONICAL_BASE_URI = "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3"

_IFC_CLASS_RE = re.compile(r"^Ifc[A-Z][A-Za-z0-9_]*$")
_IFC_PROPERTY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_PSET_RE = re.compile(r"^(?:Pset|Qto)_[A-Za-z0-9_]+$")


@dataclass(frozen=True)
class SemanticReference:
    """Representa a resolucao semantica de um nome interno para uma fonte canonica."""

    subject_type: str
    name: str
    canonical_uri: str | None
    source_url: str
    source_name: str
    source_category: str
    reference_kind: str
    status: str


def is_ifc_class_name(name: str | None) -> bool:
    return bool(name and _IFC_CLASS_RE.fullmatch(name.strip()))


def is_ifc_property_name(name: str | None) -> bool:
    return bool(name and _IFC_PROPERTY_RE.fullmatch(name.strip()))


def is_pset_name(name: str | None) -> bool:
    return bool(name and _PSET_RE.fullmatch(name.strip()))


def build_ifc_class_uri(class_name: str) -> str | None:
    normalized = class_name.strip()
    if not is_ifc_class_name(normalized):
        return None
    return f"{IFC_CANONICAL_BASE_URI}/class/{normalized}"


def build_ifc_property_uri(property_name: str) -> str | None:
    normalized = property_name.strip()
    if not is_ifc_property_name(normalized):
        return None
    return f"{IFC_CANONICAL_BASE_URI}/prop/{normalized}"


def is_canonical_ifc_class_uri(uri: str | None) -> bool:
    return bool(uri and uri.startswith(f"{IFC_CANONICAL_BASE_URI}/class/"))


def is_canonical_ifc_property_uri(uri: str | None) -> bool:
    return bool(uri and uri.startswith(f"{IFC_CANONICAL_BASE_URI}/prop/"))


def prefer_canonical_ifc_class_uri(class_name: str | None, current_uri: str | None = None) -> str | None:
    canonical_uri = build_ifc_class_uri(class_name or "")
    return canonical_uri or current_uri


def prefer_canonical_ifc_property_uri(
    property_name: str | None,
    current_uri: str | None = None,
) -> str | None:
    canonical_uri = build_ifc_property_uri(property_name or "")
    return canonical_uri or current_uri


class CanonicalURIResolver:
    """Camada unica responsavel por resolver significado semantico."""

    def __init__(self, source_policy: SourcePolicy) -> None:
        self.source_policy = source_policy

    def resolve_ifc_class(self, class_name: str) -> SemanticReference | None:
        canonical_uri = build_ifc_class_uri(class_name)
        if canonical_uri is None:
            return None
        classification = self.source_policy.classify(canonical_uri)
        return SemanticReference(
            subject_type="ifc_class",
            name=class_name.strip(),
            canonical_uri=canonical_uri,
            source_url=canonical_uri,
            source_name=classification.source_name or "buildingSMART IFC Canonical URIs",
            source_category=classification.category,
            reference_kind=classification.reference_kind,
            status="resolved",
        )

    def resolve_ifc_property(self, property_name: str) -> SemanticReference | None:
        canonical_uri = build_ifc_property_uri(property_name)
        if canonical_uri is None:
            return None
        classification = self.source_policy.classify(canonical_uri)
        return SemanticReference(
            subject_type="ifc_property",
            name=property_name.strip(),
            canonical_uri=canonical_uri,
            source_url=canonical_uri,
            source_name=classification.source_name or "buildingSMART IFC Canonical URIs",
            source_category=classification.category,
            reference_kind=classification.reference_kind,
            status="resolved",
        )

    def resolve_pset(self, pset_name: str) -> SemanticReference | None:
        normalized_name = pset_name.strip()
        if not is_pset_name(normalized_name):
            return None
        docs_url = "https://ifc43-docs.standards.buildingsmart.org/"
        classification = self.source_policy.classify(docs_url)
        return SemanticReference(
            subject_type="ifc_pset",
            name=normalized_name,
            canonical_uri=None,
            source_url=docs_url,
            source_name=classification.source_name or "buildingSMART IFC Docs",
            source_category=classification.category,
            reference_kind=classification.reference_kind,
            status="documented_only",
        )
