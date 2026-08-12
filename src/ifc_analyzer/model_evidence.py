"""Evidência agregada do modelo IFC, compartilhada entre diagnósticos.

Alguns julgamentos dependem do arquivo inteiro, não do elemento isolado. Decidir
se uma parede é de vedação ou estrutural, por exemplo, depende de saber se a
edificação tem pórtico: numa estrutura de pilares e vigas a carga corre por eles
e a alvenaria entre eles é vedação; sem pórtico, a parede é quem sustenta.

Esse dado está declarado no arquivo e nunca chegava ao LLM. No benchmark de
2026-08-10, três modelos classificaram as 262 paredes da maior classe de
equivalência como "alvenaria estrutural" num prédio que declara 216 pilares —
não por falta de conhecimento, mas porque o estímulo não dizia que os pilares
existiam.

Distinto do alias ``LoadBearing`` do próprio elemento: aquele é a resposta, este
é o contexto estrutural em que a resposta se decide.
"""

from typing import Any

import ifcopenshell
from loguru import logger

_STRUCTURAL_CLASSES: tuple[tuple[str, str, str], ...] = (
    ("IfcColumn", "pilar", "pilares"),
    ("IfcBeam", "viga", "vigas"),
)


def count_structural_frame(ifc_file: ifcopenshell.file) -> dict[str, int]:
    """Conta os elementos de pórtico declarados no arquivo, por classe IFC."""
    contagem: dict[str, int] = {}
    for ifc_class, _, _ in _STRUCTURAL_CLASSES:
        try:
            contagem[ifc_class] = len(ifc_file.by_type(ifc_class))
        except Exception as exc:  # arquivo sem a entidade no schema
            logger.debug("Contagem de {} indisponivel: {}", ifc_class, exc)
            contagem[ifc_class] = 0
    return contagem


def format_structural_inventory(ifc_file: ifcopenshell.file | None) -> str:
    """Frase declarativa com o pórtico do modelo, para injeção em prompt.

    Devolve só a contagem — a leitura do que ela significa fica com o LLM.
    """
    if ifc_file is None:
        return "não informado"

    contagem = count_structural_frame(ifc_file)
    partes: list[str] = []
    for ifc_class, singular, plural in _STRUCTURAL_CLASSES:
        total = contagem.get(ifc_class, 0)
        if total:
            partes.append(f"{total} {singular if total == 1 else plural}")

    if not partes:
        return "o arquivo não declara pilares nem vigas"
    return f"o arquivo declara {' e '.join(partes)}"


def build_model_evidence(ifc_file: ifcopenshell.file | None) -> dict[str, Any]:
    """Monta o pacote de evidência do modelo injetado no contexto das issues.

    Calculado uma vez por diagnóstico e repassado a cada issue: varrer o arquivo
    por elemento custaria uma passagem completa por issue.
    """
    return {"structural_inventory": format_structural_inventory(ifc_file)}
