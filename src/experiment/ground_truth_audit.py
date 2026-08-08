"""Política determinística para auditar rótulos sem consultar LLM ou abrir IFC."""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from src.experiment.evaluator import GroundTruthItem
from src.experiment.ground_truth_validation import (
    CATEGORY_VALUES,
    FIRE_RATING_PATTERN,
    SLAB_SYSTEM_VALUES,
    WALL_SYSTEM_VALUES,
)
from src.ifc_analyzer.material_reader import MaterialReading
from src.models import Issue

_OUT_OF_SCOPE = "fora do escopo evidence-audited-v1"
_AUTHORIAL_NOTE = (
    "Referência/intencionalidade autoral previamente revisada; "
    "não representa desempenho físico medido."
)
_UNCERTAINTY_MARKERS = (
    "a confirmar",
    "atencao",
    "conferir",
    "incerta",
    "incerto",
    "pendente",
    "por confirmar",
    "provavel",
    "sem especificacao",
    "usual",
    "verificar",
)
_PENDING_EI_ALTERNATIVES = frozenset({"EI 60", "EI 90", "EI 120"})
_RATIFIED_LEGACY_SHA256 = "7d1b1dc8b4756e5a48cd28925d3dceb53a83ab401c31ae0fcf80914ddf85bccb"
_MATERIAL_NEGATION_PATTERN = re.compile(
    r"\b(?:sem|nao|nunca|jamais|ausente|ausencia|inexistente|desprovido|"
    r"falta|faltante|without|not|none|absent|missing|lacks|lacking|non)\b"
)


class AuditDecision(BaseModel):
    """Resultado exclusivo da auditoria: item aceito ou abstenção justificada."""

    expected_value: Any | None = None
    accepted_alternatives: list[Any] = Field(default_factory=list)
    notes: str | None = None
    skip_reason: str | None = None

    @model_validator(mode="after")
    def _require_exactly_one_branch(self) -> AuditDecision:
        is_item = self.expected_value is not None
        skip_reason = self.skip_reason
        has_skip_field = skip_reason is not None
        if is_item == has_skip_field:
            raise ValueError("audit decision must contain exactly one of item or skip")
        if skip_reason is not None and not skip_reason.strip():
            raise ValueError("audit skip reason cannot be blank")
        if skip_reason is not None and self.accepted_alternatives:
            raise ValueError("skipped audit decision cannot contain accepted alternatives")
        return self


class ThermalEvidence(BaseModel):
    """Valor térmico autoral agregado para uma única chave exata de tipo IFC."""

    value: float
    donor_guids: tuple[str, ...]
    unit: str
    conflicted: bool

    @field_validator("value", mode="before")
    @classmethod
    def _reject_boolean_value(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("thermal evidence value cannot be boolean")
        return value


def _skip(reason: str) -> AuditDecision:
    return AuditDecision(skip_reason=reason)


def audit_legacy_item(
    issue: Issue,
    legacy: GroundTruthItem,
    *,
    legacy_source_sha256: str,
) -> AuditDecision:
    """Preserva apenas a parte ratificada e semanticamente válida do GT do prédio."""
    if legacy_source_sha256 != _RATIFIED_LEGACY_SHA256:
        return _skip("item sem prova do snapshot legado congelado")

    return _audit_frozen_item(issue, legacy)


def audit_canonical_item(
    issue: Issue,
    canonical: GroundTruthItem,
    *,
    canonical_source_sha256: str,
    expected_canonical_sha256: str,
) -> AuditDecision:
    """Reaudita um item canônico somente quando seus bytes estão congelados."""
    if canonical_source_sha256.lower() != expected_canonical_sha256.lower():
        return _skip("item sem prova do snapshot canônico congelado")

    return _audit_frozen_item(issue, canonical)


def _audit_frozen_item(issue: Issue, frozen: GroundTruthItem) -> AuditDecision:
    """Aplica a mesma política semântica a qualquer snapshot com identidade provada."""

    property_name = _read_check_property(issue)
    if property_name is None:
        return _skip("check_property ausente, não textual ou incompatível com issue_type")
    issue_key = (issue.element_guid, issue.issue_type, property_name)
    if frozen.natural_key != issue_key:
        return _skip("chave natural legada diverge literalmente da issue")
    if frozen.issue_id is not None and frozen.issue_id != issue.id:
        return _skip("issue_id legado diverge literalmente da issue")
    if not frozen.verified:
        return _skip("item legado não verificado")
    if _contains_uncertainty(frozen.notes):
        return _skip("nota legada contém marcador textual de incerteza")

    if _is_unratified_thermal_reference(issue, property_name, frozen.expected_value):
        return _skip("referência térmica genérica explicitamente não ratificada")

    alternatives = list(frozen.accepted_alternatives)
    if property_name == "FireRating" and frozen.expected_value == "REI 60":
        alternatives = [value for value in alternatives if value not in _PENDING_EI_ALTERNATIVES]

    if not _is_supported_legacy_value(issue, property_name, frozen.expected_value):
        return _skip("valor legado fora do conjunto semântico ratificado")
    alternatives = [
        value
        for value in alternatives
        if _is_supported_legacy_value(issue, property_name, value)
    ]

    notes = frozen.notes
    if property_name in {"FireRating", "LoadBearing", "IsLoadBearing"} or (
        issue.issue_type == "system_unclassified"
    ):
        notes = _append_once(notes, _AUTHORIAL_NOTE)
    return AuditDecision(
        expected_value=frozen.expected_value,
        accepted_alternatives=alternatives,
        notes=notes,
    )


def derive_casa_decision(
    issue: Issue,
    *,
    element_type_key: tuple[str, str],
    element_type_name: str,
    element_long_name: str | None,
    authored_thermal_by_type: Mapping[tuple[str, str], ThermalEvidence],
    material_reading: MaterialReading,
) -> AuditDecision:
    """Deriva rótulo da casa somente quando a evidência autoral é inequívoca."""
    property_name = _read_check_property(issue)
    if property_name is None:
        return _skip(_OUT_OF_SCOPE)

    if issue.issue_type == "pset_missing":
        if property_name == "ThermalTransmittance":
            return _thermal_decision(
                issue,
                element_type_key,
                element_type_name,
                authored_thermal_by_type,
            )
        if property_name == "FireRating":
            return _skip("sem declaração autoral de desempenho ao fogo")
        if property_name in {"LoadBearing", "IsLoadBearing"}:
            return _skip("sem declaração autoral de intencionalidade portante")
        if property_name == "Category" and issue.element_class == "IfcSpace":
            return _category_decision(element_long_name)
    if issue.issue_type == "system_unclassified" and property_name == "":
        return _material_system_decision(
            issue.element_class,
            element_type_name,
            element_long_name,
            material_reading,
        )
    return _skip(_OUT_OF_SCOPE)


def _thermal_decision(
    issue: Issue,
    element_type_key: tuple[str, str],
    element_type_name: str,
    authored_thermal_by_type: Mapping[tuple[str, str], ThermalEvidence],
) -> AuditDecision:
    if element_type_key[0] != issue.element_class:
        return _skip("chave de tipo incompatível com a classe IFC do elemento")
    lookup_key = element_type_key
    if not element_type_key[1]:
        lookup_key = (element_type_key[0], element_type_name)
    evidence = authored_thermal_by_type.get(lookup_key)
    if evidence is None:
        return _skip("sem valor térmico autoral em instância do mesmo tipo")
    if evidence.conflicted:
        return _skip("conflito térmico superior a 1% entre doadores do mesmo tipo")
    if (
        isinstance(evidence.value, bool)
        or not math.isfinite(evidence.value)
        or evidence.value <= 0
    ):
        return _skip("valor térmico autoral inválido")

    normalised_donors = {guid.strip() for guid in evidence.donor_guids if guid.strip()}
    normalised_donors.discard(issue.element_guid.strip())
    donor_guids = sorted(normalised_donors)
    if not donor_guids:
        return _skip("sem GUID de instância doadora do mesmo tipo")
    if not evidence.unit.strip():
        return _skip("unidade térmica autoral ausente")

    return AuditDecision(
        expected_value=evidence.value,
        notes=(
            "Valor autoral propagado por chave exata de tipo; "
            f"unidade: {evidence.unit.strip()}; GUIDs doadores: {', '.join(donor_guids)}."
        ),
    )


def _category_decision(element_long_name: str | None) -> AuditDecision:
    if element_long_name is None:
        return _skip("LongName ausente ou não inequívoco para Category")
    category = _CATEGORY_BY_LONG_NAME.get(_normalise(element_long_name))
    if category is None or category not in CATEGORY_VALUES:
        return _skip("LongName ausente ou não inequívoco para Category")
    return AuditDecision(
        expected_value=category,
        notes="Category derivada exclusivamente do LongName.",
    )


def _material_system_decision(
    element_class: str,
    element_type_name: str,
    element_long_name: str | None,
    material_reading: MaterialReading,
) -> AuditDecision:
    evidence_parts = [
        element_type_name,
        element_long_name or "",
        material_reading.material_name or "",
        *(str(layer.get("name") or "") for layer in material_reading.layers),
    ]
    evidence = _normalise(" | ".join(evidence_parts))
    if _has_material_negation(evidence):
        return _skip("evidência material contém negação ou contradição explícita")

    if element_class in {"IfcWall", "IfcWallStandardCase"}:
        candidates = _wall_candidates(evidence)
        vocabulary = WALL_SYSTEM_VALUES
    elif _is_slab_class(element_class):
        candidates = _slab_candidates(evidence)
        vocabulary = SLAB_SYSTEM_VALUES
    else:
        return _skip("classe IFC sem vocabulário material auditado")

    candidates &= vocabulary
    if len(candidates) != 1:
        return _skip("evidência material não identifica um único rótulo literal")
    return AuditDecision(
        expected_value=next(iter(candidates)),
        notes="Sistema derivado de nome, classe IFC e leitura unificada de materiais/camadas.",
    )


def _wall_candidates(evidence: str) -> set[str]:
    candidates: set[str] = set()
    if _has_any(evidence, "drywall", "steel frame", "gesso acartonado"):
        candidates.add("Drywall / Steel frame")
    if "bloco ceramico" in evidence and "vedacao" in evidence:
        candidates.add("Alvenaria de vedação em bloco cerâmico")
    if "bloco ceramico" in evidence and "estrutural" in evidence:
        candidates.add("Alvenaria estrutural em bloco cerâmico")
    if "concreto armado" in evidence and _has_any(
        evidence, "moldado in loco", "moldado no local"
    ):
        candidates.add("Concreto armado moldado in loco")
    if "concreto" in evidence and _has_any(evidence, "pre moldado", "premoldado"):
        candidates.add("Concreto pré-moldado")
    if "bloco de concreto" in evidence:
        candidates.add("Alvenaria em bloco de concreto")
    if "estrutura metalica" in evidence:
        candidates.add("Estrutura metálica")
    if _has_any(evidence, "painel de eps", "painel eps"):
        candidates.add("Painel de EPS")
    return candidates


def _slab_candidates(evidence: str) -> set[str]:
    candidates: set[str] = set()
    if "laje macica" in evidence and "concreto armado" in evidence:
        candidates.add("Laje maciça de concreto armado")
    if "laje nervurada" in evidence and _has_any(evidence, "vigota", "eps", "ceramica"):
        candidates.add("Laje nervurada (vigotas + EPS/cerâmica)")
    if _has_any(evidence, "laje pre moldada trelicada", "laje premoldada trelicada"):
        candidates.add("Laje pré-moldada treliçada")
    if "laje alveolar" in evidence and _has_any(evidence, "pre moldada", "premoldada"):
        candidates.add("Laje alveolar pré-moldada")
    if _has_any(evidence, "laje de madeira", "estrutura em madeira"):
        candidates.add("Laje de madeira (estrutura em madeira)")
    if "laje steel frame" in evidence:
        candidates.add("Laje steel frame")
    if _has_any(evidence, "piso ceramico", "porcelanato"):
        candidates.add("Piso cerâmico / porcelanato")
    if _has_any(evidence, "parquet", "taco", "piso de madeira"):
        candidates.add("Piso de madeira (parquet / taco / deck)")
    if _has_any(evidence, "piso de pedra", "marmore", "granito", "ardosia"):
        candidates.add("Piso de pedra (mármore / granito / ardósia)")
    if "concreto polido" in evidence:
        candidates.add("Piso de concreto polido")
    if _has_any(evidence, "grama natural", "grama artificial"):
        candidates.add("Grama natural ou artificial")
    if "cimento queimado" in evidence:
        candidates.add("Piso de cimento queimado")
    if _has_any(evidence, "deck de madeira externo", "deck externo de madeira"):
        candidates.add("Deck de madeira externo")
    if "carpete" in evidence:
        candidates.add("Carpete")
    if _has_any(evidence, "piso vinilico", "piso laminado"):
        candidates.add("Piso vinílico / laminado")
    return candidates


def _is_supported_legacy_value(issue: Issue, property_name: str, value: Any) -> bool:
    if issue.issue_type == "system_unclassified" and property_name == "":
        vocabulary = _system_vocabulary(issue.element_class)
        return vocabulary is not None and isinstance(value, str) and value in vocabulary
    if issue.issue_type != "pset_missing":
        return False
    if property_name == "ThermalTransmittance":
        return (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(value)
            and value > 0
        )
    if property_name in {"LoadBearing", "IsLoadBearing"}:
        return type(value) is bool
    if property_name == "Category":
        return isinstance(value, str) and value in CATEGORY_VALUES
    if property_name == "FireRating":
        return isinstance(value, str) and FIRE_RATING_PATTERN.fullmatch(value) is not None
    return False


def _is_unratified_thermal_reference(issue: Issue, property_name: str, value: Any) -> bool:
    if property_name != "ThermalTransmittance" or isinstance(value, bool):
        return False
    if issue.element_class == "IfcWindow" and value == 5.7:
        return True
    return issue.element_class == "IfcRoof" and value == 4.6


def _contains_uncertainty(notes: str | None) -> bool:
    if not notes:
        return False
    normalised = _normalise(notes)
    return any(marker in normalised for marker in _UNCERTAINTY_MARKERS)


def _read_check_property(issue: Issue) -> str | None:
    if "check_property" not in issue.context:
        return None
    value = issue.context["check_property"]
    if not isinstance(value, str):
        return None
    if issue.issue_type == "system_unclassified":
        return value if value == "" else None
    return value if value else None


def _append_once(notes: str | None, addition: str) -> str:
    existing = (notes or "").strip()
    if "nao representa desempenho fisico medido" in _normalise(existing):
        return existing
    return f"{existing} {addition}".strip()


def _normalise(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    without_separators = re.sub(r"[-_/]+", " ", without_accents)
    return re.sub(r"\s+", " ", without_separators).strip()


def _has_any(value: str, *needles: str) -> bool:
    return any(needle in value for needle in needles)


def _is_slab_class(element_class: str) -> bool:
    return element_class in {"IfcSlab", "IfcSlabStandardCase"}


def _system_vocabulary(element_class: str) -> frozenset[str] | None:
    if element_class in {"IfcWall", "IfcWallStandardCase"}:
        return WALL_SYSTEM_VALUES
    if _is_slab_class(element_class):
        return SLAB_SYSTEM_VALUES
    return None


def _has_material_negation(evidence: str) -> bool:
    return _MATERIAL_NEGATION_PATTERN.search(evidence) is not None


def _category_aliases(category: str, *aliases: str) -> dict[str, str]:
    return {_normalise(alias): category for alias in (category, *aliases)}


_CATEGORY_BY_LONG_NAME = {
    **_category_aliases("BEDROOM", "quarto", "dormitório"),
    **_category_aliases("LIVING_ROOM", "sala de estar"),
    **_category_aliases("KITCHEN", "cozinha"),
    **_category_aliases("BATHROOM", "banheiro"),
    **_category_aliases("WC", "lavabo", "sanitário"),
    **_category_aliases("CIRCULATION", "circulação", "corredor"),
    **_category_aliases("SERVICE_AREA", "área de serviço", "lavanderia"),
    **_category_aliases("OFFICE", "escritório"),
    **_category_aliases("MEETING_ROOM", "sala de reunião"),
    **_category_aliases("LOBBY", "recepção"),
    **_category_aliases("STORAGE", "depósito", "almoxarifado"),
    **_category_aliases("BALCONY", "varanda", "sacada"),
    **_category_aliases("GARAGE", "garagem"),
    **_category_aliases("TECHNICAL_AREA", "área técnica", "casa de máquinas"),
}
