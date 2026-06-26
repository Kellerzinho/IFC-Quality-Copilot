"""Agrupa issues estruturalmente equivalentes para reuso de sugestao LLM."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from typing import Any

from src.models import Issue


def _clean_text(value: object) -> str:
    """Texto normalizado para assinaturas estruturais."""
    return str(value or "").strip().casefold()


def _short_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _fingerprint_contained_elements(elements: object) -> str:
    """Hash dos elementos contidos (classe + label + nome, ordenados)."""
    if not isinstance(elements, list) or not elements:
        return "empty"

    tokens: list[str] = []
    for element in elements:
        if isinstance(element, dict):
            ifc_class = _clean_text(element.get("ifc_class"))
            label = _clean_text(element.get("functional_label"))
            name = _clean_text(element.get("name"))
            token = "|".join(part for part in (ifc_class, label, name) if part)
        else:
            token = _clean_text(element)
        if token:
            tokens.append(token)

    return _short_hash(sorted(tokens)) if tokens else "empty"


def _fingerprint_adjacent_spaces(spaces: object) -> str:
    """Hash de adjacencias funcionais do espaco, sem depender de GUID."""
    if not isinstance(spaces, list) or not spaces:
        return "empty"

    tokens: list[str] = []
    for space in spaces:
        if not isinstance(space, dict):
            continue
        connection_type = _clean_text(space.get("connection_type"))
        name = _clean_text(space.get("name"))
        token = "|".join(part for part in (connection_type, name) if part)
        if token:
            tokens.append(token)

    return _short_hash(sorted(tokens)) if tokens else "empty"


def _bucket_area(area: object) -> str:
    """Agrupa area m2 em faixas largas para compatibilidade com testes legados."""
    try:
        value = float(area)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "?"
    if value < 4:
        return "<4"
    if value < 8:
        return "4-8"
    if value < 15:
        return "8-15"
    if value < 25:
        return "15-25"
    if value < 50:
        return "25-50"
    return ">50"


def _rounded_measure(value: object, step: float) -> str:
    try:
        numeric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "?"
    return f"{round(numeric / step) * step:.2f}"


def _bucket_thickness(thickness: object) -> str:
    """Agrupa espessura em faixas de 2 cm."""
    return _rounded_measure(thickness, 0.02)


def _fingerprint_material_layers(materials: object) -> str:
    """Hash dos nomes e espessuras das camadas de material na ordem original."""
    if not isinstance(materials, list) or not materials:
        return "empty"

    layers = [
        {
            "name": _clean_text(layer.get("name") or layer.get("material")),
            "thickness": _bucket_thickness(layer.get("thickness_m") or layer.get("thickness")),
        }
        for layer in materials
        if isinstance(layer, dict)
    ]
    return _short_hash(layers) if layers else "empty"


def _fingerprint_existing_psets(psets: object) -> str:
    """Hash leve dos Psets existentes que podem diferenciar tipo/material/localizacao."""
    if not isinstance(psets, dict) or not psets:
        return "empty"

    interesting_props = {
        "isexternal",
        "fireexit",
        "thermaltransmittance",
        "firerating",
        "acousticrating",
        "glazingarea",
        "glasslayers",
        "operationtype",
        "reference",
        "status",
        "loadbearing",
    }
    payload: dict[str, dict[str, Any]] = {}
    for pset_name, props in psets.items():
        if not isinstance(props, dict):
            continue
        clean_props: dict[str, Any] = {}
        for prop_name, value in props.items():
            if _clean_text(prop_name) in interesting_props:
                clean_props[str(prop_name)] = value
        if clean_props:
            payload[str(pset_name)] = clean_props

    return _short_hash(payload) if payload else "empty"


def _context_text_hints(issue: Issue) -> str:
    """Pistas textuais de tipo/material sem numeros de instancia."""
    raw = " ".join(
        _clean_text(value)
        for value in (
            issue.element_name,
            issue.context.get("type_name"),
            issue.context.get("object_type"),
            issue.context.get("predefined_type"),
            issue.context.get("construction_type"),
            issue.context.get("material_name"),
        )
        if value
    )
    if not raw:
        return "empty"

    tokens = sorted(
        {
            token
            for token in raw.replace(":", " ").replace("_", " ").replace("-", " ").split()
            if token and not token.isdigit()
        }
    )
    return _short_hash(tokens) if tokens else "empty"


def _has_specific_text_hint(issue: Issue) -> bool:
    """True quando nome/tipo contem pista semantica alem de identificador generico."""
    raw = " ".join(
        _clean_text(value)
        for value in (
            issue.element_name,
            issue.context.get("type_name"),
            issue.context.get("object_type"),
            issue.context.get("predefined_type"),
            issue.context.get("construction_type"),
        )
        if value
    )
    if not raw:
        return False

    generic_tokens = {
        "door",
        "porta",
        "window",
        "janela",
        "wall",
        "parede",
        "space",
        "room",
        "sala",
        "generic",
        "default",
        "standard",
        "padrao",
        "padrão",
        "type",
        "tipo",
    }
    tokens = {
        token
        for token in raw.replace(":", " ").replace("_", " ").replace("-", " ").split()
        if token and not token.isdigit()
    }
    return any(token not in generic_tokens for token in tokens)


def _has_rich_space_context(issue: Issue) -> bool:
    context = issue.context
    return any(
        [
            _fingerprint_contained_elements(context.get("contained_elements")) != "empty",
            _fingerprint_adjacent_spaces(context.get("adjacent_spaces")) != "empty",
            context.get("area_m2") is not None,
            context.get("floor"),
            context.get("is_on_exterior") is not None,
        ]
    )


def _has_material_or_type_context(issue: Issue) -> bool:
    context = issue.context
    return any(
        [
            context.get("material_name"),
            _fingerprint_material_layers(context.get("layers")) != "empty",
            _fingerprint_material_layers(context.get("materials")) != "empty",
            context.get("thickness_m") is not None,
            context.get("is_external") is not None,
            _fingerprint_existing_psets(context.get("existing_psets")) != "empty",
            _has_specific_text_hint(issue),
        ]
    )


def is_safe_to_reuse(issue: Issue) -> bool:
    """Retorna se a issue tem contexto suficiente para reutilizar sugestao.

    Quando a sugestao depende de uso, material, localizacao ou tipo, a ausencia
    dessas pistas torna o agrupamento arriscado; nesse caso cada issue chama o
    LLM ou cacheia separadamente.
    """
    if issue.issue_type == "space_unnamed":
        return _has_rich_space_context(issue)

    if issue.issue_type == "pset_missing":
        prop = _clean_text(issue.context.get("check_property"))
        if issue.element_class in {"IfcDoor", "IfcWindow", "IfcSpace"}:
            return _has_material_or_type_context(issue) or _has_rich_space_context(issue)
        if prop in {"firerating", "thermaltransmittance", "isexternal"}:
            return _has_material_or_type_context(issue)

    if issue.issue_type in {
        "quantity_missing",
        "classification_missing",
        "material_unmapped",
        "asset_unidentified",
        "thermal_incomplete",
    }:
        return False

    return True


def compute_structural_signature(issue: Issue) -> str:
    """Gera assinatura estrutural de uma issue.

    Issues com a mesma assinatura podem reutilizar sugestoes apenas quando a
    assinatura inclui as caracteristicas que influenciam o valor sugerido.
    """
    parts = [
        issue.issue_type,
        issue.element_class,
        str(issue.context.get("check_pset") or issue.context.get("pset_name") or ""),
        str(issue.context.get("check_property") or ""),
        str(issue.context.get("expected_type") or ""),
        str(issue.context.get("expected_unit") or ""),
        str(issue.context.get("expected_value") or ""),
        str(issue.context.get("expected_relation") or ""),
    ]

    if issue.issue_type == "space_unnamed":
        if not is_safe_to_reuse(issue):
            parts.append(f"unique:{issue.element_guid}")
        parts.append(_fingerprint_contained_elements(issue.context.get("contained_elements")))
        parts.append(_fingerprint_adjacent_spaces(issue.context.get("adjacent_spaces")))
        parts.append(_rounded_measure(issue.context.get("area_m2"), 0.5))
        parts.append(_rounded_measure(issue.context.get("height_m"), 0.1))
        parts.append(_rounded_measure(issue.context.get("perimeter_m"), 0.5))
        parts.append(str(issue.context.get("is_on_exterior")))
        parts.append(_clean_text(issue.context.get("floor")))
        parts.append(_context_text_hints(issue))

    elif issue.issue_type == "pset_missing":
        if not is_safe_to_reuse(issue):
            parts.append(f"unique:{issue.element_guid}")
        parts.append(_clean_text(issue.context.get("material_name")))
        parts.append(_bucket_thickness(issue.context.get("thickness_m")))
        parts.append(_fingerprint_material_layers(issue.context.get("layers")))
        parts.append(_fingerprint_material_layers(issue.context.get("materials")))
        parts.append(str(issue.context.get("is_external")))
        parts.append(_fingerprint_existing_psets(issue.context.get("existing_psets")))
        parts.append(_fingerprint_contained_elements(issue.context.get("contained_elements")))
        parts.append(_fingerprint_adjacent_spaces(issue.context.get("adjacent_spaces")))
        parts.append(_rounded_measure(issue.context.get("area_m2"), 0.5))
        parts.append(_context_text_hints(issue))

    elif issue.issue_type == "system_unclassified":
        parts.append(_fingerprint_material_layers(issue.context.get("materials")))
        parts.append(_bucket_thickness(issue.context.get("total_thickness")))
        parts.append(_clean_text(issue.context.get("predefined_type")))
        parts.append(_context_text_hints(issue))

    elif issue.issue_type == "relation_broken":
        parts.append(f"unique:{issue.element_guid}")
        parts.append(_context_text_hints(issue))

    payload = "::".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


class IssueDeduplicator:
    """Agrupa issues estruturalmente equivalentes."""

    def group_issues(self, issues: list[Issue]) -> dict[str, list[str]]:
        """Retorna {primary_issue_id: [equivalent_issue_ids]}."""
        groups: OrderedDict[str, list[str]] = OrderedDict()
        sig_to_primary: dict[str, str] = {}
        for issue in issues:
            if not is_safe_to_reuse(issue):
                groups[issue.id] = [issue.id]
                continue

            sig = compute_structural_signature(issue)
            primary = sig_to_primary.get(sig)
            if primary is None:
                sig_to_primary[sig] = issue.id
                groups[issue.id] = [issue.id]
            else:
                groups[primary].append(issue.id)
        return dict(groups)

    def build_reuse_map(self, issues: list[Issue]) -> dict[str, str]:
        """Retorna {secondary_issue_id: primary_issue_id} para issues secundarias."""
        reuse_map: dict[str, str] = {}
        groups = self.group_issues(issues)
        for primary, members in groups.items():
            for member in members:
                if member != primary:
                    reuse_map[member] = primary
        return reuse_map

    def signature_for(self, issue: Issue) -> str:
        """Expoe a assinatura estrutural para inspecao/debug."""
        return compute_structural_signature(issue)
