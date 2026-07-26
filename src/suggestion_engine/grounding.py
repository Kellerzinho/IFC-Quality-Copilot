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
    # Contexto rico do elemento (Fase A.1) — mesmos sinais da assinatura de cache
    material_layers: list[dict] = Field(default_factory=list)
    material_name: str | None = None
    thickness_m: float | None = None
    predefined_type: str | None = None
    is_external: bool | None = None
    floor: str | None = None
    existing_psets: list[str] = Field(default_factory=list)

    @property
    def has_official_candidates(self) -> bool:
        return bool(self.official_candidates)

    @property
    def is_grounded(self) -> bool:
        """True quando há ao menos uma fonte de grounding confiável."""
        return bool(self.grounding_sources)


def _coerce_float(value: object) -> float | None:
    """Converte valor arbitrário do contexto em float, retornando None se inviável."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", "."))
        except ValueError:
            return None
    return None


def _coerce_bool(value: object) -> bool | None:
    """Converte valor arbitrário do contexto em bool, retornando None se ambíguo."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "sim", "yes", "1"}:
            return True
        if normalized in {"false", "nao", "não", "no", "0"}:
            return False
    return None


def _coerce_material_layers(value: object) -> list[dict]:
    """Extrai lista de camadas de material (dicts) do contexto da issue."""
    if not isinstance(value, list):
        return []
    layers: list[dict] = []
    for item in value:
        if isinstance(item, dict):
            layers.append(item)
        elif item is not None:
            layers.append({"name": str(item)})
    return layers


def _coerce_pset_names(value: object) -> list[str]:
    """Extrai nomes de psets existentes do contexto (lista ou dict)."""
    if isinstance(value, dict):
        return [str(k) for k in value]
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return []


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
        # A classe oficial resolvida ja e grounding: existem propriedades do IFC
        # ausentes do bSDD (IfcSpace.Category), em que a classe resolve com URI
        # canonica e a propriedade nao. Ignorar isso registraria "sem bSDD" num
        # caso em que o vocabulario oficial foi consultado e usado.
        if (
            bsdd_context.classification_suggestions
            or bsdd_context.related_properties
            or bsdd_context.class_uri
        ):
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

    # Contexto rico do elemento (Fase A.1): sinais que já alimentam a assinatura
    # de cache passam a alimentar também o prompt grounded.
    material_layers = _coerce_material_layers(
        issue.context.get("materials") or issue.context.get("layers")
    )
    material_name_raw = issue.context.get("material_name")
    material_name = str(material_name_raw).strip() if material_name_raw else None
    thickness_m = _coerce_float(
        issue.context.get("thickness_m")
        if issue.context.get("thickness_m") is not None
        else issue.context.get("total_thickness")
    )
    predefined_type_raw = issue.context.get("predefined_type")
    predefined_type = str(predefined_type_raw).strip() if predefined_type_raw else None
    is_external = _coerce_bool(
        issue.context.get("is_external")
        if issue.context.get("is_external") is not None
        else issue.context.get("is_on_exterior")
    )
    floor_raw = issue.context.get("floor")
    floor = str(floor_raw).strip() if floor_raw else None
    existing_psets = _coerce_pset_names(issue.context.get("existing_psets"))

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
        material_layers=material_layers,
        material_name=material_name,
        thickness_m=thickness_m,
        predefined_type=predefined_type,
        is_external=is_external,
        floor=floor,
        existing_psets=existing_psets,
    )
