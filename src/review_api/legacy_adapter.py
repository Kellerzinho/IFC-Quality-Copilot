"""Adaptador LEGADO: lacunas por elemento a partir de IFC + IDS, somente leitura.

Fonte: ``src.ifc_analyzer.analyzer.IFCAnalyzer.analyze_from_ids`` (parser IDS
e regras de ``src.translator``). O legado identifica elementos apenas por
GlobalId; este adaptador traduz cada GlobalId para os express_ids daquele
arquivo e, se houver mais de um, marca a lacuna como ``ambiguous`` sem escolher.

Os marcadores "A definir", 0 e FALSE são observação PRÓPRIA do adaptador
(``origin="m4_adapter_marker"`` ou ``provisional_marker``), nunca atribuída ao
legado. O valor atual é lido com ``ifcopenshell.util.element.get_psets``.
Nada aqui escreve no IFC.
"""

import hashlib
from collections.abc import Callable
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element
from loguru import logger

from src.ifc_analyzer.analyzer import IFCAnalyzer
from src.models import Issue, OperationalRule
from src.review_api.schemas import (
    ElementRef,
    Gap,
    GapRequirement,
    ObservedValue,
    ProvisionalMarkerObservation,
    ScalarValue,
)
from src.translator.ids_parser import parse_ids
from src.translator.rule_generator import _matches_filter, generate_rules

LEGACY_SOURCE = "legado: src.ifc_analyzer.analyzer.IFCAnalyzer.analyze_from_ids"

LIMITATIONS: list[str] = [
    "PROVISÓRIO: formato aguardando o diagnóstico canônico de M2 e o enriquecimento de M3.",
    "O legado só reporta falhas; não há os cinco estados M2 (conforme, não conforme, "
    "não aplicável, não verificado, erro).",
    "O legado identifica elementos só por GlobalId; GlobalId repetido no mesmo arquivo "
    "vira lacuna 'ambiguous' com todos os candidatos, sem escolha.",
    "Marcadores 'A definir'/0/FALSE são observação do adaptador M4, não do legado; "
    "o legado aceita 'A definir' e FALSE como presentes.",
    "Valor atual lido por nome exato de Pset/propriedade; o legado pode resolver aliases.",
    "Aplicabilidade e checagens seguem o subconjunto IDS suportado pelo parser legado.",
]

_ATTRIBUTE_PSET = ""
_RELATION_PSET = "IFC_RELATION"


def _kind_of(value: ScalarValue) -> str:
    """Classifica o tipo do valor sem perder bool/int/float."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "real"
    return "string"


def observe(element: ifcopenshell.entity_instance, pset: str, prop: str) -> ObservedValue:
    """Lê o valor atual de uma propriedade (ou atributo) sem alterar o IFC."""
    if pset == _ATTRIBUTE_PSET:
        if not hasattr(element, prop):
            return ObservedValue(state="property_absent")
        raw = getattr(element, prop)
    else:
        psets = ifcopenshell.util.element.get_psets(element)
        if pset not in psets:
            return ObservedValue(state="pset_absent")
        if prop not in psets[pset]:
            return ObservedValue(state="property_absent")
        raw = psets[pset][prop]

    if raw is None:
        return ObservedValue(state="null")
    if isinstance(raw, str) and raw == "":
        return ObservedValue(state="empty", kind="string", value="")
    if isinstance(raw, bool | int | float | str):
        return ObservedValue(state="present", kind=_kind_of(raw), value=raw)
    return ObservedValue(state="present", kind="other", value=str(raw))


def detect_marker(observed: ObservedValue) -> ProvisionalMarkerObservation | None:
    """Reconhece "A definir", 0 e FALSE como marcadores provisórios."""
    if observed.state != "present":
        return None
    value = observed.value
    if isinstance(value, bool):
        return ProvisionalMarkerObservation(marker="FALSE") if value is False else None
    if isinstance(value, int | float) and value == 0:
        return ProvisionalMarkerObservation(marker="0")
    if isinstance(value, str) and value.strip().casefold() == "a definir":
        return ProvisionalMarkerObservation(marker="A definir")
    return None


def global_id_index(ifc_file: ifcopenshell.file) -> dict[str, list[int]]:
    """Mapeia GlobalId → express_ids no arquivo (lista, pois pode repetir)."""
    index: dict[str, list[int]] = {}
    for entity in ifc_file.by_type("IfcRoot"):
        guid = getattr(entity, "GlobalId", None)
        if guid:
            index.setdefault(guid, []).append(entity.id())
    for ids in index.values():
        ids.sort()
    return index


def _gap_id(*parts: object) -> str:
    """Gera identificador determinístico de lacuna."""
    joined = "|".join(str(p) for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:20]


def _requirement_from_issue(issue: Issue) -> GapRequirement:
    """Converte o contexto da Issue legada em requisito de transporte."""
    ctx = issue.context
    return GapRequirement(
        property_set=str(ctx.get("check_pset", "")),
        property_name=str(ctx.get("check_property", "")),
        check=str(ctx.get("check_type", "")),
        expected_value=ctx.get("expected_value"),
        unit=ctx.get("unit"),
        specification=str(ctx.get("source_spec", "")),
    )


def _requirement_from_rule(rule: OperationalRule) -> GapRequirement:
    """Converte uma regra legada em requisito de transporte."""
    return GapRequirement(
        property_set=rule.check_pset,
        property_name=rule.check_property,
        check=rule.check_type,
        expected_value=rule.expected_value,
        unit=rule.evidence_source,
        specification=rule.source_spec,
    )


def compute_gaps(
    ifc_path: Path,
    ids_path: Path,
    model_id: str,
    ifc_revision_id: str,
) -> list[Gap]:
    """Executa o legado em modo leitura e devolve lacunas PROVISÓRIAS por ElementRef.

    Args:
        ifc_path: caminho do IFC armazenado (bytes imutáveis da revisão).
        ids_path: caminho do IDS armazenado.
        model_id: linha do projeto a que o IFC pertence.
        ifc_revision_id: SHA-256 do IFC.

    Returns:
        Lacunas ordenadas de forma estável.
    """
    analyzer = IFCAnalyzer(str(ifc_path))
    ifc_file = analyzer.ifc_file
    report = analyzer.analyze_from_ids(str(ids_path))
    index = global_id_index(ifc_file)

    def ref(express_id: int) -> ElementRef:
        return ElementRef(
            model_id=model_id, ifc_revision_id=ifc_revision_id, express_id=express_id
        )

    gaps: list[Gap] = []
    resolved_keys: set[tuple[int, str, str]] = set()

    for issue in report.issues:
        requirement = _requirement_from_issue(issue)
        if requirement.property_set == _RELATION_PSET:
            continue
        express_ids = index.get(issue.element_guid, [])
        base = {
            "origin": "legacy_ifc_analyzer",
            "global_id": issue.element_guid,
            "ifc_class": issue.element_class,
            "element_name": issue.element_name,
            "requirement": requirement,
        }
        if len(express_ids) == 1:
            element = ifc_file.by_id(express_ids[0])
            observed = observe(element, requirement.property_set, requirement.property_name)
            gaps.append(
                Gap(
                    gap_id=_gap_id("legacy", model_id, ifc_revision_id, express_ids[0],
                                   requirement.specification, requirement.property_set,
                                   requirement.property_name),
                    resolution="resolved",
                    element=ref(express_ids[0]),
                    current_value=observed,
                    provisional_marker=detect_marker(observed),
                    **base,
                )
            )
            resolved_keys.add(
                (express_ids[0], requirement.property_set, requirement.property_name)
            )
        elif len(express_ids) > 1:
            gaps.append(
                Gap(
                    gap_id=_gap_id("legacy-ambiguous", model_id, ifc_revision_id,
                                   issue.element_guid, requirement.specification,
                                   requirement.property_set, requirement.property_name),
                    resolution="ambiguous",
                    candidates=[ref(i) for i in express_ids],
                    **base,
                )
            )
        else:
            logger.warning("GlobalId {} do legado não localizado no arquivo", issue.element_guid)
            gaps.append(
                Gap(
                    gap_id=_gap_id("legacy-not-found", model_id, ifc_revision_id,
                                   issue.element_guid, requirement.property_set,
                                   requirement.property_name),
                    resolution="not_found",
                    **base,
                )
            )

    gaps.extend(
        _marker_gaps(ifc_file, ids_path, model_id, ifc_revision_id, resolved_keys, ref)
    )
    gaps.sort(key=_sort_key)
    return gaps


def _marker_gaps(
    ifc_file: ifcopenshell.file,
    ids_path: Path,
    model_id: str,
    ifc_revision_id: str,
    already_reported: set[tuple[int, str, str]],
    ref: Callable[[int], ElementRef],
) -> list[Gap]:
    """Observação própria: requisitos que o legado aceitou mas contêm marcador."""
    rules = generate_rules(parse_ids(str(ids_path)))
    psets_cache: dict[str, dict[str, dict]] = {}
    found: list[Gap] = []
    seen: set[tuple[int, str, str]] = set()
    for rule in rules:
        if rule.check_pset == _RELATION_PSET:
            continue
        try:
            elements = ifc_file.by_type(rule.filter_entity)
        except RuntimeError:
            continue
        for element in elements:
            key = (element.id(), rule.check_pset, rule.check_property)
            if key in already_reported or key in seen:
                continue
            if not _matches_filter(element, rule.filter_conditions, ifc_file, psets_cache):
                continue
            observed = observe(element, rule.check_pset, rule.check_property)
            marker = detect_marker(observed)
            if marker is None:
                continue
            seen.add(key)
            found.append(
                Gap(
                    gap_id=_gap_id("marker", model_id, ifc_revision_id, element.id(),
                                   rule.source_spec, rule.check_pset, rule.check_property),
                    origin="m4_adapter_marker",
                    resolution="resolved",
                    element=ref(element.id()),
                    global_id=getattr(element, "GlobalId", None),
                    ifc_class=element.is_a(),
                    element_name=getattr(element, "Name", None),
                    requirement=_requirement_from_rule(rule),
                    current_value=observed,
                    provisional_marker=marker,
                )
            )
    return found


def _sort_key(gap: Gap) -> tuple[str, int, str, str, str]:
    """Ordem estável: classe, primeiro express_id, Pset, propriedade, origem."""
    anchor = gap.element or (gap.candidates[0] if gap.candidates else None)
    return (
        gap.ifc_class,
        anchor.express_id if anchor else 0,
        gap.requirement.property_set,
        gap.requirement.property_name,
        gap.origin,
    )
