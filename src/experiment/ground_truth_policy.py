"""Contrato científico comum aos ground truths de cobertura integral."""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

POLICY_VERSION = "full-coverage-equivalent-v1"

Confidence = Literal["high", "medium", "low"]
SourceKind = Literal[
    "ifc_literal",
    "ifc_alias",
    "existing_gt",
    "equivalent_donor",
    "calculation",
    "normative_rule",
    "typology",
    "probable",
]

_NON_CONCRETE = {
    "unknown",
    "not applicable",
    "not_applicable",
    "pending review",
    "pending_review",
    "review required",
    "review_required",
}


def _normalised_value(value: Any) -> str:
    if isinstance(value, str):
        text = unicodedata.normalize("NFKD", value)
        text = "".join(char for char in text if not unicodedata.combining(char))
        return " ".join(text.casefold().split())
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class GroundTruthDecision(BaseModel):
    """Uma decisão concreta e auditável para uma classe de equivalência."""

    model_config = ConfigDict(extra="forbid", strict=True)

    expected_value: Any
    accepted_alternatives: list[Any] = Field(default_factory=list)
    confidence: Confidence
    source_kind: SourceKind
    notes: str
    legacy_reference: bool = False

    @field_validator("expected_value", mode="before")
    @classmethod
    def _require_concrete_value(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("concrete expected_value is required")
        if isinstance(value, str):
            normalised = _normalised_value(value)
            if not normalised or normalised in _NON_CONCRETE:
                raise ValueError("concrete expected_value is required")
        return value

    @field_validator("notes")
    @classmethod
    def _require_notes(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("notes must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def _validate_scientific_metadata(self) -> GroundTruthDecision:
        if self.confidence == "low" and not self.notes.startswith("Hipótese congelada:"):
            raise ValueError("low confidence notes must start with 'Hipótese congelada:'")

        expected = _normalised_value(self.expected_value)
        seen = {expected}
        for alternative in self.accepted_alternatives:
            if alternative is None:
                raise ValueError("accepted alternative must be concrete")
            normalised = _normalised_value(alternative)
            if not normalised or normalised in seen:
                raise ValueError("accepted alternative duplicates an accepted value")
            seen.add(normalised)
        return self


def assert_equivalence_ids_unique(
    pairs: Iterable[tuple[str, Mapping[str, object]]],
) -> None:
    """Falha se um ID truncado representar payloads canônicos diferentes."""
    seen: dict[str, str] = {}
    for equivalence_id, payload in pairs:
        if re.fullmatch(r"eq-[0-9a-f]{16}", equivalence_id) is None:
            raise ValueError(f"invalid equivalence_id: {equivalence_id}")
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        previous = seen.setdefault(equivalence_id, canonical)
        if previous != canonical:
            raise ValueError(f"equivalence_id collision: {equivalence_id}")
