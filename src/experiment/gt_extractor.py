"""Extrator de ground truth por diff de modelo enriquecido (Fase C.2, passo 3).

Protocolo **GT-by-diff**: para cada issue detectada no modelo v1 (com lacunas),
busca no modelo enriquecido pelo especialista (por ``GlobalId``) o valor correto
e gera ``ground_truth.yaml`` com ``verified: false`` — a revisão humana item a
item (que vira ``verified: true``) é o passo 4 do protocolo (Fase C.2).

Cobertura: as **3 tarefas do experimento** —

- ``pset_missing`` → valor da propriedade em ``check_pset`` (com fallback para
  outros psets do elemento, anotado em ``notes``);
- ``space_unnamed`` → ``LongName`` do IfcSpace (``Name`` como fallback), com
  guardrail: nome igual ao genérico da v1 conta como *não enriquecido*;
- ``system_unclassified`` → ``IfcClassificationReference`` do sistema
  construtivo (mesmo local onde ``IFCWriter.classificar_sistema`` escreve).

Guardrail anti-circularidade (C.0): este módulo só **lê** valores produzidos
pelo especialista no modelo GT; a LLM avaliada nunca participa da extração.

Uso:

    python -m src.experiment.gt_extractor --ifc predio_v1.ifc \\
        --ids data/ids_templates/residencial_nbr15575.ids \\
        --gt-ifc predio_gt.ifc \\
        --output data/evaluation/predio/ground_truth.yaml
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import ifcopenshell
import ifcopenshell.util.element
import yaml
from loguru import logger
from pydantic import BaseModel, Field

from src.experiment.evaluator import GroundTruth, GroundTruthItem
from src.experiment.runner import sha256_of
from src.models import Issue

# Nome do IfcClassification usado por IFCWriter.classificar_sistema
DEFAULT_CLASSIFICATION_NAME = "Sistema Construtivo"

# Tarefas do experimento cobertas pelo protocolo GT-by-diff
SUPPORTED_ISSUE_TYPES = frozenset(
    {"pset_missing", "space_unnamed", "system_unclassified"}
)


class SkippedIssue(BaseModel):
    """Issue da v1 que não gerou item de GT, com o motivo (para o README do dataset)."""

    issue_id: str
    element_guid: str
    issue_type: str
    check_property: str = ""
    reason: str


class GTExtractionResult(BaseModel):
    """Resultado da extração: ground truth candidato + issues não cobertas."""

    ground_truth: GroundTruth
    skipped: list[SkippedIssue] = Field(default_factory=list)

    @property
    def extracted_count(self) -> int:
        """Número de itens de GT extraídos do modelo enriquecido."""
        return len(self.ground_truth.items)


# ---------------------------------------------------------------------------
# Extração por tarefa
# ---------------------------------------------------------------------------


def _find_element(gt_model: ifcopenshell.file, guid: str) -> Any | None:
    """Busca elemento por GlobalId no modelo GT; None se ausente."""
    try:
        return gt_model.by_guid(guid)
    except RuntimeError:
        return None


def _extract_space_name(element: Any, v1_name: str | None) -> tuple[Any | None, str | None]:
    """Extrai o nome funcional do IfcSpace enriquecido.

    Prefere ``LongName`` (onde ``IFCWriter.renomear_espaco`` escreve), com
    ``Name`` como fallback. Retorna (None, motivo) quando o nome continua
    vazio ou igual ao genérico da v1 (não enriquecido).
    """
    long_name = (getattr(element, "LongName", None) or "").strip()
    name = (getattr(element, "Name", None) or "").strip()
    value = long_name or name
    if not value:
        return None, "espaço sem LongName/Name no modelo GT"
    if v1_name and value.strip().casefold() == v1_name.strip().casefold():
        return None, f"nome no GT ('{value}') igual ao genérico da v1 (não enriquecido)"
    return value, None


def _extract_pset_value(
    element: Any, check_pset: str, check_property: str
) -> tuple[Any | None, str | None, str | None]:
    """Extrai o valor da propriedade no modelo GT.

    Busca primeiro no pset esperado (``check_pset``); se ausente, varre os
    demais psets do elemento (fallback anotado em notes).

    Returns:
        (valor, note, motivo_skip) — valor None implica motivo_skip preenchido.
    """
    if not check_property:
        return None, None, "issue pset_missing sem check_property no contexto"

    psets = ifcopenshell.util.element.get_psets(element)

    if check_pset and check_pset in psets:
        value = psets[check_pset].get(check_property)
        if value is not None:
            return value, None, None

    # Fallback: propriedade pode ter sido preenchida em outro pset
    for pset_name, props in psets.items():
        if pset_name == check_pset or not isinstance(props, dict):
            continue
        value = props.get(check_property)
        if value is not None and check_property != "id":
            return value, f"valor encontrado em '{pset_name}' (esperado '{check_pset}')", None

    return None, None, (
        f"propriedade '{check_property}' ausente no modelo GT (não enriquecida)"
    )


def _extract_system_classification(
    gt_model: ifcopenshell.file,
    element: Any,
    classification_name: str = DEFAULT_CLASSIFICATION_NAME,
) -> tuple[Any | None, str | None, str | None]:
    """Extrai a classificação de sistema construtivo do elemento no modelo GT.

    Lê o mesmo local onde ``IFCWriter.classificar_sistema`` escreve:
    ``IfcClassificationReference`` sob o ``IfcClassification`` indicado.
    Se não houver referência nesse sistema, aceita a primeira referência de
    qualquer sistema (fallback anotado em notes).

    Returns:
        (valor, note, motivo_skip) — valor None implica motivo_skip preenchido.
    """
    fallback: tuple[str, str] | None = None  # (valor, nome_sistema)
    for rel in gt_model.by_type("IfcRelAssociatesClassification"):
        rc = rel.RelatingClassification
        if element not in rel.RelatedObjects or not rc.is_a("IfcClassificationReference"):
            continue
        value = rc.Name or getattr(rc, "ItemReference", None) or getattr(
            rc, "Identification", None
        )
        if not value:
            continue
        source = rc.ReferencedSource
        source_name = (
            source.Name if source is not None and source.is_a("IfcClassification") else None
        )
        if source_name == classification_name:
            return str(value), None, None
        if fallback is None:
            fallback = (str(value), source_name or "desconhecido")

    if fallback is not None:
        value, system = fallback
        note = f"classificação encontrada no sistema '{system}' (esperado '{classification_name}')"
        return value, note, None

    return None, None, "elemento sem classificação de sistema no modelo GT (não enriquecido)"


def extract_value_for_issue(
    gt_model: ifcopenshell.file,
    issue: Issue,
    classification_name: str = DEFAULT_CLASSIFICATION_NAME,
) -> tuple[Any | None, str | None, str | None]:
    """Extrai do modelo GT o valor correto para uma issue da v1.

    Returns:
        (valor, note, motivo_skip): valor extraído (None quando não há),
        anotação de fallback para ``notes`` e motivo do skip quando aplicável.
    """
    if issue.issue_type not in SUPPORTED_ISSUE_TYPES:
        return None, None, (
            f"issue_type '{issue.issue_type}' fora das 3 tarefas do experimento"
        )

    element = _find_element(gt_model, issue.element_guid)
    if element is None:
        return None, None, "GlobalId ausente no modelo GT"

    if issue.issue_type == "space_unnamed":
        value, reason = _extract_space_name(element, issue.element_name)
        return value, None, reason

    if issue.issue_type == "pset_missing":
        check_pset = str(issue.context.get("check_pset") or issue.context.get("pset_name") or "")
        check_property = str(issue.context.get("check_property") or "")
        return _extract_pset_value(element, check_pset, check_property)

    # system_unclassified
    return _extract_system_classification(gt_model, element, classification_name)


# ---------------------------------------------------------------------------
# Extração do conjunto completo
# ---------------------------------------------------------------------------


def extract_ground_truth(
    issues: list[Issue],
    gt_model: ifcopenshell.file,
    metadata: dict[str, Any] | None = None,
    classification_name: str = DEFAULT_CLASSIFICATION_NAME,
) -> GTExtractionResult:
    """Gera o ground truth candidato a partir das issues da v1 e do modelo enriquecido.

    Cada issue coberta vira um :class:`GroundTruthItem` com chave natural
    ``(element_guid, issue_type, check_property)``, ``issue_id`` (determinístico,
    Fase 0.2) e ``verified: false`` — a verificação humana é etapa posterior.
    Issues sem valor extraível são reportadas em ``skipped`` com motivo.
    """
    items: list[GroundTruthItem] = []
    skipped: list[SkippedIssue] = []

    for issue in issues:
        check_property = str(issue.context.get("check_property") or "")
        value, note, skip_reason = extract_value_for_issue(
            gt_model, issue, classification_name=classification_name
        )
        if skip_reason is not None:
            skipped.append(
                SkippedIssue(
                    issue_id=issue.id,
                    element_guid=issue.element_guid,
                    issue_type=issue.issue_type,
                    check_property=check_property,
                    reason=skip_reason,
                )
            )
            continue
        items.append(
            GroundTruthItem(
                element_guid=issue.element_guid,
                issue_type=issue.issue_type,
                check_property=check_property,
                issue_id=issue.id,
                expected_value=value,
                verified=False,
                notes=note,
            )
        )

    logger.info(
        "gt_extractor: {} itens extraídos, {} issues sem GT ({} issues de entrada)",
        len(items),
        len(skipped),
        len(issues),
    )
    ground_truth = GroundTruth(items=items, metadata=metadata or {})
    return GTExtractionResult(ground_truth=ground_truth, skipped=skipped)


# ---------------------------------------------------------------------------
# Serialização YAML
# ---------------------------------------------------------------------------


def write_ground_truth_yaml(
    result: GTExtractionResult,
    output_path: str | Path,
    *,
    input_ifc_path: str | Path | None = None,
    gt_ifc_path: str | Path | None = None,
    ids_path: str | Path | None = None,
) -> Path:
    """Serializa o ground truth candidato em YAML versionável.

    O cabeçalho ``metadata`` registra protocolo, data, hashes SHA256 dos
    arquivos de origem e o campo ``verified_by`` (a preencher na revisão
    humana). Os itens saem ordenados por (issue_type, element_guid,
    check_property) para diffs estáveis no git. O arquivo é compatível com
    :meth:`GroundTruth.from_yaml`.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    metadata: dict[str, Any] = {
        "protocol": "gt-by-diff",
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "verified_by": None,
        "input_ifc_sha256": sha256_of(input_ifc_path),
        "gt_ifc_sha256": sha256_of(gt_ifc_path),
        "ids_sha256": sha256_of(ids_path),
        "total_items": result.extracted_count,
        "total_skipped": len(result.skipped),
        **result.ground_truth.metadata,
    }

    sorted_items = sorted(
        result.ground_truth.items,
        key=lambda i: (i.issue_type or "", i.element_guid or "", i.check_property),
    )
    payload: dict[str, Any] = {
        "metadata": metadata,
        "items": [
            item.model_dump(exclude_none=True, exclude_defaults=False)
            for item in sorted_items
        ],
    }
    if result.skipped:
        payload["skipped"] = [s.model_dump() for s in result.skipped]

    output.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    logger.info("gt_extractor: ground truth candidato salvo em {}", output)
    return output


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Monta o parser de argumentos do CLI."""
    parser = argparse.ArgumentParser(
        prog="python -m src.experiment.gt_extractor",
        description=(
            "Extrai ground truth candidato por diff entre o modelo v1 (com lacunas) "
            "e o modelo enriquecido pelo especialista (protocolo GT-by-diff, Fase C.2)."
        ),
    )
    parser.add_argument("--ifc", required=True, help="Caminho do IFC v1 (com lacunas)")
    parser.add_argument("--ids", required=True, help="Caminho do perfil IDS aplicável")
    parser.add_argument(
        "--gt-ifc", required=True, help="Caminho do IFC enriquecido pelo especialista"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Caminho do ground_truth.yaml de saída (verified: false)",
    )
    parser.add_argument(
        "--building-type", default="Residencial unifamiliar", help="Tipo da edificação"
    )
    parser.add_argument(
        "--bioclimatic-zone", default="3", help="Zona bioclimática NBR 15575"
    )
    parser.add_argument(
        "--classification-name",
        default=DEFAULT_CLASSIFICATION_NAME,
        help="Nome do IfcClassification do sistema construtivo no modelo GT",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Executa o protocolo GT-by-diff de ponta a ponta pela linha de comando."""
    args = _build_parser().parse_args(argv)

    # Import tardio: evita carregar o pipeline completo em usos programáticos
    from src.pipeline import QualityPipeline

    building_context = {
        "building_type": args.building_type,
        "bioclimatic_zone": args.bioclimatic_zone,
    }

    logger.info("gt_extractor: diagnosticando {} com IDS {}", args.ifc, args.ids)
    pipeline = QualityPipeline(args.ifc, building_context, ids_path=args.ids)
    report = pipeline.diagnose()
    issues = report.issues
    logger.info("gt_extractor: {} issues detectadas na v1", len(issues))

    gt_model = ifcopenshell.open(args.gt_ifc)
    result = extract_ground_truth(
        issues, gt_model, classification_name=args.classification_name
    )

    write_ground_truth_yaml(
        result,
        args.output,
        input_ifc_path=args.ifc,
        gt_ifc_path=args.gt_ifc,
        ids_path=args.ids,
    )

    for item in result.skipped:
        logger.warning(
            "gt_extractor: sem GT para {} ({} {}): {}",
            item.issue_id,
            item.issue_type,
            item.element_guid[:8],
            item.reason,
        )
    logger.info(
        "gt_extractor: concluído — {} itens (verified: false), {} skips. "
        "Próximo passo do protocolo: revisão humana item a item.",
        result.extracted_count,
        len(result.skipped),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
