"""Normalizacao e validacao forte de sugestoes antes da aplicacao."""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any

from src.models import BSDDContext, Issue, Suggestion
from src.semantic_registry.registry import DEFAULT_SOURCE_POLICY

_FLOAT_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")
_FIRE_RATING_RE = re.compile(r"\b(REI|EI|E|R)\s*[-:]?\s*(\d+)\b", re.IGNORECASE)
_FIRE_MIN_RE = re.compile(r"\b(\d+)\s*(?:min|mins|minute|minutes)\b", re.IGNORECASE)
_FIRE_HOUR_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*h\b", re.IGNORECASE)
_CANONICAL_FIRE_RE = re.compile(r"^(?:REI|EI|E|R)\s+\d+$")
_COMMON_FIRE_RATING_MINUTES = {15, 20, 30, 45, 60, 90, 120, 180, 240}
_WALL_SYSTEM_ALIASES: dict[str, str] = {
    "alvenaria de vedacao em bloco ceramico": "Alvenaria de veda\u00e7\u00e3o em bloco cer\u00e2mico",
    "alvenaria vedacao bloco ceramico": "Alvenaria de veda\u00e7\u00e3o em bloco cer\u00e2mico",
    "alvenaria em bloco ceramico": "Alvenaria de veda\u00e7\u00e3o em bloco cer\u00e2mico",
    "alvenaria ceramica": "Alvenaria de veda\u00e7\u00e3o em bloco cer\u00e2mico",
    "bloco ceramico": "Alvenaria de veda\u00e7\u00e3o em bloco cer\u00e2mico",
    "alvenaria estrutural em bloco ceramico": "Alvenaria estrutural em bloco cer\u00e2mico",
    "concreto armado": "Concreto armado",
    "concreto armado moldado in loco": "Concreto armado",
    "concreto pre moldado": "Concreto pr\u00e9-moldado",
    "concreto premoldado": "Concreto pr\u00e9-moldado",
    "drywall": "Drywall / Steel frame",
    "steel frame": "Drywall / Steel frame",
    "drywall steel frame": "Drywall / Steel frame",
    "alvenaria em bloco de concreto": "Alvenaria em bloco de concreto",
    "bloco de concreto": "Alvenaria em bloco de concreto",
    "estrutura metalica": "Estrutura met\u00e1lica",
    "painel de eps": "Painel de EPS",
}

_SLAB_SYSTEM_RULES: list[tuple[tuple[str, ...], str]] = [
    (("laje macica", "concreto armado"), "Laje maci\u00e7a de concreto armado"),
    (("laje nervurada",), "Laje nervurada"),
    (("pre moldada", "trelic"), "Laje pr\u00e9-moldada treli\u00e7ada"),
    (("alveolar",), "Laje alveolar pr\u00e9-moldada"),
    (("steel frame",), "Laje steel frame"),
    (("madeira",), "Laje de madeira"),
    (("grama",), "Revestimento de grama"),
    (("piso ceramico",), "Piso cer\u00e2mico / porcelanato"),
    (("porcelanato",), "Piso cer\u00e2mico / porcelanato"),
    (("ceramica",), "Piso cer\u00e2mico / porcelanato"),
    (("deck", "madeira"), "Deck de madeira externo"),
    (("piso de madeira",), "Piso de madeira"),
    (("parquet",), "Piso de madeira"),
    (("taco",), "Piso de madeira"),
    (("cimento queimado",), "Piso de cimento queimado"),
    (("concreto polido",), "Piso de concreto polido"),
    (("vinilico",), "Piso vin\u00edlico / laminado"),
    (("laminado",), "Piso vin\u00edlico / laminado"),
]

_SPACE_FUNCTION_ALIASES: dict[str, str] = {
    "lavabo": "Lavabo",
    "banheiro": "Banheiro",
    "wc": "Banheiro",
    "sala estar": "Sala de Estar",
    "sala de estar": "Sala de Estar",
    "living room": "Sala de Estar",
    "cozinha": "Cozinha",
    "dormitorio": "Dormitorio",
    "quarto": "Dormitorio",
    "suite": "Suite",
    "area servico": "Area de servico",
    "area de servico": "Area de servico",
    "circulacao": "Circulacao",
    "corredor": "Circulacao",
    "escritorio": "Escritorio",
}


def normalize_suggestion(
    issue: Issue,
    suggestion: Suggestion,
    bsdd_context: BSDDContext | None = None,
) -> Suggestion | None:
    """Normaliza uma sugestao individual para o formato canonico do projeto."""
    normalized_value = normalize_value_for_issue(issue, suggestion.value)
    if normalized_value is None:
        return None

    label = _render_label(issue, normalized_value, fallback=suggestion.label)
    justification = (suggestion.justification or "").strip()
    semantic_hint = _canonical_semantic_hint(issue, suggestion, normalized_value)
    canonical_term = _canonical_term(issue, suggestion, normalized_value)
    bsdd_uri = resolve_bsdd_uri(
        issue,
        normalized_value,
        bsdd_context,
        canonical_term=canonical_term,
        semantic_hint=semantic_hint,
        source_candidates=suggestion.source_candidates,
    )
    semantic_status = "not_applicable"
    review_required = suggestion.review_required
    semantic_source_origin = None
    if issue.issue_type in {"pset_missing", "space_unnamed", "system_unclassified", "classification_missing"}:
        semantic_status = "resolved" if bsdd_uri else "pending_review"
        review_required = review_required or bsdd_uri is None
        semantic_source_origin = "bsdd_context" if bsdd_uri else "llm_hint"

    return suggestion.model_copy(
        update={
            "label": label,
            "value": normalized_value,
            "justification": justification,
            "canonical_term": canonical_term,
            "semantic_hint": semantic_hint,
            "review_required": review_required,
            "semantic_status": semantic_status,
            "semantic_source_origin": semantic_source_origin,
            "bsdd_uri": bsdd_uri,
        }
    )


def normalize_value_for_issue(issue: Issue, raw_value: Any) -> Any | None:
    """Converte o valor cru para o tipo e formato esperados pela issue."""
    if issue.issue_type == "pset_missing":
        prop = str(issue.context.get("check_property") or "").strip()
        if prop == "ThermalTransmittance":
            return parse_numeric_value(raw_value)
        if prop == "FireRating":
            return normalize_fire_rating(raw_value)
        if prop == "Category":
            return normalize_text(raw_value)
        return _normalize_generic_pset_value(raw_value)

    if issue.issue_type == "system_unclassified":
        return canonicalize_system_label(raw_value, issue.element_class)

    if issue.issue_type == "space_unnamed":
        return canonicalize_space_label(raw_value)

    if issue.issue_type in {"classification_missing", "asset_unidentified", "relation_broken"}:
        return normalize_text(raw_value)

    return raw_value


def parse_numeric_value(raw_value: Any) -> float | None:
    """Extrai um float limpo mesmo quando o valor vier com unidade ou texto extra."""
    if isinstance(raw_value, bool) or raw_value is None:
        return None
    if isinstance(raw_value, (int, float)):
        value = float(raw_value)
        return value if math.isfinite(value) and value > 0 else None

    text = str(raw_value).strip()
    if not text:
        return None

    match = _FLOAT_RE.search(text)
    if not match:
        return None

    number = match.group().replace(",", ".")
    try:
        value = float(number)
    except ValueError:
        return None
    return value if math.isfinite(value) and value > 0 else None


def normalize_fire_rating(raw_value: Any) -> str | None:
    """Canonicaliza FireRating para o formato CLASSE n, ex.: REI 60 ou EI 30."""
    if raw_value is None or isinstance(raw_value, bool):
        return None

    text = str(raw_value).strip()
    if not text:
        return None

    canonical_match = _FIRE_RATING_RE.search(text)
    if canonical_match:
        rating_class = canonical_match.group(1).upper()
        minutes = int(canonical_match.group(2))
        return _render_fire_rating(rating_class, minutes)

    min_match = _FIRE_MIN_RE.search(text)
    if min_match:
        minutes = int(min_match.group(1))
        return _render_fire_rating("REI", minutes)

    hour_match = _FIRE_HOUR_RE.search(text)
    if hour_match:
        hours_text = hour_match.group(1).replace(",", ".")
        try:
            minutes = int(round(float(hours_text) * 60))
        except ValueError:
            return None
        return _render_fire_rating("REI", minutes)

    stripped = text.strip().upper()
    if re.fullmatch(r"\d+", stripped):
        minutes = int(stripped)
        return _render_fire_rating("REI", minutes)

    return None


def _render_fire_rating(rating_class: str, minutes: int) -> str | None:
    if minutes not in _COMMON_FIRE_RATING_MINUTES:
        return None
    return f"{rating_class} {minutes}"


def canonicalize_system_label(raw_value: Any, element_class: str | None = None) -> str | None:
    """Canonicaliza rotulos textuais equivalentes de sistema construtivo."""
    text = normalize_text(raw_value)
    if not text:
        return None

    normalized = _normalize_key(text)
    if element_class in {"IfcSlab", "IfcSlabStandardCase"}:
        for terms, canonical in _SLAB_SYSTEM_RULES:
            if all(term in normalized for term in terms):
                return canonical
        if normalized.startswith("laje "):
            return text
        return text

    if normalized in _WALL_SYSTEM_ALIASES:
        return _WALL_SYSTEM_ALIASES[normalized]

    for alias, canonical in _WALL_SYSTEM_ALIASES.items():
        if alias in normalized:
            return canonical

    return text


def canonicalize_space_label(raw_value: Any) -> str | None:
    """Canonicaliza classificacoes funcionais frequentes de espacos."""
    text = normalize_text(raw_value)
    if not text:
        return None

    normalized = _normalize_key(text)
    if normalized in _SPACE_FUNCTION_ALIASES:
        return _SPACE_FUNCTION_ALIASES[normalized]

    for alias, canonical in _SPACE_FUNCTION_ALIASES.items():
        if alias in normalized:
            return canonical

    return text


def resolve_bsdd_uri(
    issue: Issue,
    normalized_value: Any,
    bsdd_context: BSDDContext | None,
    canonical_term: str | None = None,
    semantic_hint: str | None = None,
    source_candidates: list[str] | None = None,
) -> str | None:
    """Resolve URI bSDD apenas a partir de contexto confiavel.

    A URI sugerida pelo LLM nunca e aceita como verdade final.
    """
    if bsdd_context is None:
        return None

    if issue.issue_type == "pset_missing":
        target_property = str(issue.context.get("check_property") or "").strip().casefold()
        for prop in bsdd_context.properties:
            if prop.name.strip().casefold() == target_property and is_valid_bsdd_uri(prop.uri):
                return prop.uri
        return None

    candidate_terms = [
        term for term in [canonical_term, semantic_hint, *(source_candidates or []), str(normalized_value)]
        if term
    ]
    normalized_keys = {_normalize_key(str(term)) for term in candidate_terms}
    for classification in bsdd_context.classes:
        if _normalize_key(classification.name) in normalized_keys and is_valid_bsdd_uri(classification.uri):
            return classification.uri

    return None


def is_valid_bsdd_uri(uri: str | None) -> bool:
    """Aceita apenas URIs bSDD/buildingSMART confiaveis."""
    classification = DEFAULT_SOURCE_POLICY.classify(uri)
    return classification.category == "official" and classification.reference_kind in {
        "canonical_uri",
        "api_resource",
    }


def _canonical_term(issue: Issue, suggestion: Suggestion, normalized_value: Any) -> str | None:
    if suggestion.canonical_term and suggestion.canonical_term.strip():
        return suggestion.canonical_term.strip()
    if suggestion.semantic_hint and suggestion.semantic_hint.strip():
        return suggestion.semantic_hint.strip()
    return str(normalized_value) if normalized_value is not None else None


def _canonical_semantic_hint(issue: Issue, suggestion: Suggestion, normalized_value: Any) -> str | None:
    if suggestion.semantic_hint and suggestion.semantic_hint.strip():
        return suggestion.semantic_hint.strip()
    if issue.issue_type == "system_unclassified":
        return canonicalize_system_label(normalized_value, issue.element_class)
    if issue.issue_type == "space_unnamed":
        return canonicalize_space_label(normalized_value)
    return suggestion.canonical_term or (str(normalized_value) if normalized_value is not None else None)


def suggestion_identity_key(issue: Issue, suggestion: Suggestion) -> str:
    """Gera chave canonica para deduplicar sugestoes semanticamente equivalentes."""
    value = suggestion.value
    if isinstance(value, float):
        rendered = f"{value:.6f}".rstrip("0").rstrip(".")
    else:
        rendered = str(value)
    return f"{issue.issue_type}:{_normalize_key(rendered)}"


def is_canonical_fire_rating(value: Any) -> bool:
    """Retorna True quando o valor segue o formato REI n."""
    return isinstance(value, str) and bool(_CANONICAL_FIRE_RE.fullmatch(value.strip()))


def normalize_text(value: Any) -> str | None:
    """Normalizacao textual simples para campos livres."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_generic_pset_value(raw_value: Any) -> Any | None:
    if isinstance(raw_value, str):
        return normalize_text(raw_value)
    return raw_value


def _render_label(issue: Issue, normalized_value: Any, fallback: str) -> str:
    if issue.issue_type == "pset_missing" and issue.context.get("check_property") == "ThermalTransmittance":
        return f"{normalized_value:.2f}"
    if normalized_value is None:
        return fallback
    return str(normalized_value)


def _normalize_key(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()
