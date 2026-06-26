"""Grounding compacto por issue antes da chamada LLM.

Centraliza o que IDS, bSDD e contexto da issue dizem em um payload pequeno
e estruturado para o prompt. O LLM escolhe entre candidatos oficiais
quando existem; quando não há grounding confiável, abstém-se via
review_required.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.models import BSDDContext, IDSContext, Issue


class GroundedIssueContext(BaseModel):
    """Contexto compacto para alimentar o prompt LLM por issue."""

    issue_id: str
    issue_type: str
    ifc_class: str
    global_id: str
    element_name: str | None = None
    canonical_pset: str | None = None
    canonical_property: str | None = None
    expected_datatype: str | None = None
    expected_unit: str | None = None
    expected_value: str | None = None
    current_value: str | None = None
    official_candidates: list[str] = Field(default_factory=list)
    controlled_aliases: list[str] = Field(default_factory=list)
    relevant_constraints: list[str] = Field(default_factory=list)
    requirement_summary: str | None = None
    requirement_id: str | None = None
    grounding_sources: list[str] = Field(default_factory=list)

    @property
    def has_official_candidates(self) -> bool:
        return bool(self.official_candidates)

    @property
    def is_grounded(self) -> bool:
        """True quando há ao menos uma fonte de grounding confiável."""
        return bool(self.grounding_sources)


def _truncate(text: str | None, max_chars: int = 120) -> str | None:
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def prepare_llm_grounding(
    issue: Issue,
    ids_context: IDSContext | None = None,
    bsdd_context: BSDDContext | None = None,
) -> GroundedIssueContext:
    """Monta GroundedIssueContext a partir da issue + IDS + bSDD."""
    sources: list[str] = []

    canonical_pset = (
        (ids_context.expected_pset if ids_context else None)
        or issue.context.get("check_pset")
        or issue.context.get("pset_name")
    )
    canonical_property = (
        (ids_context.expected_property if ids_context else None)
        or issue.context.get("check_property")
    )

    expected_datatype: str | None = None
    expected_unit: str | None = (ids_context.expected_unit if ids_context else None) or issue.context.get("expected_unit")
    expected_value: str | None = None
    if ids_context and ids_context.expected_value is not None:
        expected_value = str(ids_context.expected_value)

    relevant_constraints: list[str] = []
    if ids_context is not None:
        sources.append("ids")
        if ids_context.check_type:
            relevant_constraints.append(f"check_type={ids_context.check_type}")
        if ids_context.severity:
            relevant_constraints.append(f"severity={ids_context.severity}")

    official_candidates: list[str] = []
    controlled_aliases: list[str] = []
    if bsdd_context is not None:
        if bsdd_context.classification_suggestions or bsdd_context.related_properties:
            sources.append("bsdd")
        # Para issue_type=space_unnamed/system_unclassified: candidatos = nomes de classes
        for cls in bsdd_context.classification_suggestions:
            if cls.name and cls.name not in official_candidates:
                official_candidates.append(cls.name)
        # Para pset_missing: candidatos = allowed_values da propriedade alvo
        if canonical_property:
            target_norm = canonical_property.strip().casefold()
            for prop in bsdd_context.related_properties:
                if prop.name.strip().casefold() != target_norm:
                    continue
                if prop.data_type and not expected_datatype:
                    expected_datatype = prop.data_type
                if prop.unit and not expected_unit:
                    expected_unit = prop.unit
                for value in prop.allowed_values or []:
                    if value and value not in official_candidates:
                        official_candidates.append(str(value))

    # current_value = valor atual da propriedade no IFC, se contexto informou
    current_value = issue.context.get("current_value")
    current_value_str = str(current_value) if current_value is not None else None

    return GroundedIssueContext(
        issue_id=issue.id,
        issue_type=issue.issue_type,
        ifc_class=issue.element_class,
        global_id=issue.element_guid,
        element_name=issue.element_name,
        canonical_pset=canonical_pset,
        canonical_property=canonical_property,
        expected_datatype=expected_datatype,
        expected_unit=expected_unit,
        expected_value=expected_value,
        current_value=current_value_str,
        official_candidates=official_candidates,
        controlled_aliases=controlled_aliases,
        relevant_constraints=relevant_constraints,
        requirement_summary=_truncate(ids_context.requirement_description) if ids_context else None,
        requirement_id=ids_context.requirement_id if ids_context else None,
        grounding_sources=sources,
    )
