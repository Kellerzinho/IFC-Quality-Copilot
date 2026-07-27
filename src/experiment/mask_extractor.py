"""Masking de nomes de espaços para a tarefa de nomeação (Fase C.3).

O prédio de estudo tem todos os 82 IfcSpaces com nomes funcionais — a tarefa
de **nomeação de espaços** não gera issue nenhuma nele. Este módulo deriva um
modelo mascarado: grava os ``LongName`` originais (autoria do projetista) como
ground truth e **remove** o ``LongName`` dos espaços, fazendo o diagnóstico
cair no ``Name`` numérico do Revit (ex.: "40"), que casa com o padrão genérico
``^\\d+$`` de ``space_diagnostics`` e dispara ``space_unnamed``.

Guardrail anti-circularidade (C.0): o GT são os nomes originais do autor —
nenhuma LLM participa. Na curadoria (C.2 passo 4), adicionar
``accepted_alternatives`` onde múltiplos nomes são igualmente corretos
(ex.: "Lavatório Social" vs "Lavabo").

Uso:

    python -m src.experiment.mask_extractor \\
        --ifc data/evaluation/predio/predio_v1.ifc \\
        --out-ifc data/evaluation/predio/predio_v1_masked.ifc \\
        --output data/evaluation/predio/ground_truth_spaces.yaml
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

import ifcopenshell
from loguru import logger

from src.experiment.evaluator import GroundTruth, GroundTruthItem
from src.experiment.gt_extractor import GTExtractionResult, write_ground_truth_yaml
from src.ifc_analyzer.space_diagnostics import _is_generic_name


def mask_space_names(model: ifcopenshell.file) -> list[GroundTruthItem]:
    """Mascara os LongNames funcionais dos IfcSpaces e retorna o GT dos originais.

    Espaços cujo nome já é genérico/vazio não são tocados (não há GT confiável
    para eles). A mutação é in-place no ``model`` — o chamador decide onde
    salvar a cópia mascarada; nunca sobrescrever o modelo congelado.
    """
    items: list[GroundTruthItem] = []
    for space in model.by_type("IfcSpace"):
        long_name = (getattr(space, "LongName", None) or "").strip()
        name = (getattr(space, "Name", None) or "").strip()
        functional = long_name if long_name and not _is_generic_name(long_name) else ""
        if not functional and name and not _is_generic_name(name):
            functional = name
        if not functional:
            continue  # já genérico/vazio — não há GT confiável
        alternatives = (
            [name] if name and name != functional and not _is_generic_name(name) else []
        )
        items.append(
            GroundTruthItem(
                element_guid=space.GlobalId,
                issue_type="space_unnamed",
                check_property="",
                expected_value=functional,
                accepted_alternatives=alternatives,
                verified=False,
                notes=(
                    "Nome original do autor, removido por masking (protocolo C.3). "
                    "Curadoria: adicionar accepted_alternatives para sinônimos."
                ),
            )
        )
        # Remove toda a semântica de nome; um Name genérico (ex.: número do
        # ambiente no Revit) é preservado para manter a rastreabilidade.
        space.LongName = None
        if name and not _is_generic_name(name):
            space.Name = None
        _mask_type_and_reference(model, space, functional)
    logger.info("mask_space_names: {} espaços mascarados", len(items))
    return items


def _mask_type_and_reference(
    model: ifcopenshell.file,
    space: ifcopenshell.entity_instance,
    functional: str,
) -> None:
    """Remove o nome funcional que sobrevive no tipo e no ``Reference`` do Pset.

    Mascarar só a instância deixava o nome original em dois lugares — medido em
    ``predio_v1_masked.ifc``: ``IfcSpaceType.Name = 'Lava Pés 61:1373227'`` e
    ``Pset_SpaceCommon.Reference = 'Lava Pés 61'``. Nenhum dos dois chegava ao
    prompt na época, mas o vazamento impedia que o extrator passasse a ler o
    tipo — que é evidência legítima para o produto.
    """
    alvo = functional.strip().casefold()

    for rel in model.by_type("IfcRelDefinesByType"):
        if space not in (rel.RelatedObjects or []):
            continue
        tipo = rel.RelatingType
        if tipo is not None and alvo and alvo in str(getattr(tipo, "Name", "") or "").casefold():
            # O tipo pode ser compartilhado por varios espacos do mesmo ambiente;
            # zerar o nome uma vez ja basta e repetir e inofensivo.
            tipo.Name = None

    for rel in model.by_type("IfcRelDefinesByProperties"):
        if space not in (rel.RelatedObjects or []):
            continue
        definicao = rel.RelatingPropertyDefinition
        if definicao is None or not definicao.is_a("IfcPropertySet"):
            continue
        for prop in definicao.HasProperties or []:
            if prop.Name != "Reference" or not prop.is_a("IfcPropertySingleValue"):
                continue
            valor = getattr(prop.NominalValue, "wrappedValue", None)
            if valor and alvo and alvo in str(valor).casefold():
                prop.NominalValue = None


def _build_parser() -> argparse.ArgumentParser:
    """Monta o parser de argumentos do CLI."""
    parser = argparse.ArgumentParser(
        prog="python -m src.experiment.mask_extractor",
        description=(
            "Deriva modelo com nomes de espaços mascarados + ground truth dos "
            "nomes originais (protocolo masking, Fase C.3)."
        ),
    )
    parser.add_argument("--ifc", required=True, help="IFC de origem (não é modificado)")
    parser.add_argument("--out-ifc", required=True, help="Caminho do IFC mascarado")
    parser.add_argument(
        "--output", required=True, help="Caminho do ground_truth de nomes (YAML)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Executa o protocolo de masking de ponta a ponta pela linha de comando."""
    args = _build_parser().parse_args(argv)
    if args.ifc == args.out_ifc:
        logger.error("out-ifc não pode sobrescrever o IFC de origem congelado")
        return 1

    model = ifcopenshell.open(args.ifc)
    items = mask_space_names(model)
    model.write(args.out_ifc)
    logger.info("mask_extractor: modelo mascarado salvo em {}", args.out_ifc)

    metadata: dict[str, Any] = {
        "protocol": "masking",
        "method": (
            "LongName original do autor gravado como GT e removido do modelo "
            "mascarado; o Name numérico remanescente dispara space_unnamed. "
            "Sem participação de LLM (guardrail C.0)."
        ),
        "source_ifc": str(args.ifc),
        "masked_ifc": str(args.out_ifc),
        "requires_human_review": True,
    }
    result = GTExtractionResult(
        ground_truth=GroundTruth(items=items, metadata=metadata), skipped=[]
    )
    write_ground_truth_yaml(result, args.output, input_ifc_path=args.ifc)
    logger.info(
        "mask_extractor: {} itens de GT (verified:false) em {}", len(items), args.output
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
