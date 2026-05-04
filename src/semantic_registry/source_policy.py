"""Politica central de classificacao de fontes e links semanticos."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

SourceCategory = str
ReferenceKind = str


@dataclass(frozen=True)
class SourceRecord:
    """Define uma fonte registrada e sua politica basica."""

    name: str
    category: SourceCategory
    owner: str
    base_url: str
    default_reference_kind: ReferenceKind


@dataclass(frozen=True)
class URLClassification:
    """Resultado da classificacao de um link segundo a politica de fontes."""

    url: str
    normalized_url: str | None
    category: SourceCategory
    reference_kind: ReferenceKind
    source_name: str | None = None
    owner: str | None = None
    matched_base_url: str | None = None

    @property
    def is_official(self) -> bool:
        return self.category == "official"

    @property
    def is_trusted_secondary(self) -> bool:
        return self.category == "trusted_secondary"

    @property
    def is_forbidden(self) -> bool:
        return self.category == "forbidden"

    @property
    def is_invalid(self) -> bool:
        return self.reference_kind == "invalid"

    @property
    def is_documentation(self) -> bool:
        return self.reference_kind == "documentation"

    @property
    def is_canonical_uri(self) -> bool:
        return self.reference_kind == "canonical_uri"

    @property
    def is_secondary_link(self) -> bool:
        return self.category == "trusted_secondary" or self.reference_kind == "secondary_link"


class SourcePolicy:
    """Classifica links como oficiais, secundarios ou proibidos."""

    def __init__(self, sources: list[SourceRecord]) -> None:
        self._sources = sorted(sources, key=lambda item: len(item.base_url), reverse=True)

    @property
    def sources(self) -> list[SourceRecord]:
        return list(self._sources)

    def classify(self, url: str | None) -> URLClassification:
        """Classifica o link informado segundo a politica central."""
        if not url or not isinstance(url, str):
            return URLClassification(
                url=url or "",
                normalized_url=None,
                category="forbidden",
                reference_kind="invalid",
            )

        normalized_url = url.strip()
        parsed = urlparse(normalized_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return URLClassification(
                url=url,
                normalized_url=normalized_url,
                category="forbidden",
                reference_kind="invalid",
            )

        record = self._match_record(normalized_url)
        if record is not None:
            reference_kind = self._infer_reference_kind(normalized_url, record)
            return URLClassification(
                url=url,
                normalized_url=normalized_url,
                category=record.category,
                reference_kind=reference_kind,
                source_name=record.name,
                owner=record.owner,
                matched_base_url=record.base_url,
            )

        category = self._fallback_category(parsed.netloc.lower())
        reference_kind = "secondary_link" if category == "trusted_secondary" else "unregistered"
        return URLClassification(
            url=url,
            normalized_url=normalized_url,
            category=category,
            reference_kind=reference_kind,
        )

    def is_official(self, url: str | None) -> bool:
        return self.classify(url).is_official

    def is_forbidden(self, url: str | None) -> bool:
        return self.classify(url).is_forbidden

    def is_documentation_link(self, url: str | None) -> bool:
        return self.classify(url).is_documentation

    def is_secondary_link(self, url: str | None) -> bool:
        return self.classify(url).is_secondary_link

    def is_invalid_reference(self, url: str | None) -> bool:
        return self.classify(url).is_invalid

    def is_semantic_uri(self, url: str | None) -> bool:
        classification = self.classify(url)
        return classification.reference_kind in {"canonical_uri", "api_resource"}

    def _match_record(self, normalized_url: str) -> SourceRecord | None:
        for record in self._sources:
            if normalized_url.startswith(record.base_url):
                return record
        return None

    def _fallback_category(self, netloc: str) -> SourceCategory:
        if netloc in {"github.com", "raw.githubusercontent.com"}:
            return "forbidden"
        return "trusted_secondary"

    def _infer_reference_kind(self, normalized_url: str, record: SourceRecord) -> ReferenceKind:
        parsed = urlparse(normalized_url)
        path = parsed.path.lower()

        if "identifier.buildingsmart.org" in parsed.netloc.lower() and "/uri/" in path:
            return "canonical_uri"
        if record.default_reference_kind == "documentation" or path.endswith((".html", ".htm")):
            return "documentation"
        if record.default_reference_kind == "repository":
            return "repository"
        if record.default_reference_kind == "api":
            if "/graphql" in path or "/api/" in path:
                return "api_endpoint"
            return "api_resource"
        if record.default_reference_kind == "discovery":
            return "discovery"
        return record.default_reference_kind
