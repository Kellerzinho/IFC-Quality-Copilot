"""Leitura unificada de material e camadas de um elemento IFC.

Existiam quatro leituras independentes de material no projeto (diagnóstico de
sistemas, extrator térmico, extrator de classificação, extrator universal), e
apenas a do extrator universal entendia ``IfcMaterialConstituentSet`` — o
formato que o Revit exporta. Consequência medida em 2026-07-27 no modelo do
prédio: **867 das 887** issues de ``system_unclassified`` chegavam ao LLM com
``materials=[]``, e **606 de 606** issues de ``ThermalTransmittance`` com
``thickness_m=None``. O modelo classificava sistema construtivo e estimava
transmitância sem nenhuma evidência de material.

Particularidade do formato: ``IfcMaterialConstituent`` **não** guarda espessura.
Ela fica no conjunto de quantidades, como ``IfcPhysicalComplexQuantity`` com
``Discrimination='Layer'`` (uma por camada, com ``Width``), e a espessura total
em ``Width`` (paredes) ou ``Depth`` (lajes).
"""

from __future__ import annotations

from typing import Any

import ifcopenshell
import ifcopenshell.util.element
from loguru import logger
from pydantic import BaseModel, Field

# Nome da quantidade que carrega a espessura, por classe de elemento.
#
# So classes em que Width/Depth SIGNIFICAM espessura de secao entram aqui: numa
# esquadria (IfcWindow/IfcDoor), Width e a LARGURA do vao — uma janela de 1,5 m
# entrou no prompt termico como "Espessura total: 1.5 m" quando o fallback era
# generico (regressao de 2026-07-27). Classe fora da tabela = sem fallback.
_THICKNESS_QUANTITY: dict[str, tuple[str, ...]] = {
    "IfcWall": ("Width",),
    "IfcWallStandardCase": ("Width",),
    "IfcSlab": ("Depth", "Width"),
    "IfcRoof": ("Depth", "Width"),
    "IfcCovering": ("Width",),
    "IfcPlate": ("Width",),
}


class MaterialReading(BaseModel):
    """Material de um elemento: nome do conjunto, camadas e espessura total."""

    material_name: str | None = None
    layers: list[dict[str, Any]] = Field(default_factory=list)
    """Camadas na ordem do modelo: ``{"name": str | None, "thickness_m": float | None}``."""
    total_thickness_m: float | None = None


def _layer_quantities(element: ifcopenshell.entity_instance) -> list[tuple[str, float | None]]:
    """Espessuras por camada declaradas no conjunto de quantidades, em ordem.

    O Revit emite uma ``IfcPhysicalComplexQuantity`` por camada, com
    ``Discrimination='Layer'`` e uma ``Width`` dentro.
    """
    encontrados: list[tuple[str, float | None]] = []
    try:
        qtos = ifcopenshell.util.element.get_psets(element, qtos_only=True)
    except Exception as exc:
        logger.debug("Erro ao ler quantidades de {}: {}", element.is_a(), exc)
        return encontrados

    for quantities in qtos.values():
        if not isinstance(quantities, dict):
            continue
        for nome, valor in quantities.items():
            if not isinstance(valor, dict) or valor.get("Discrimination") != "Layer":
                continue
            propriedades = valor.get("properties")
            largura = propriedades.get("Width") if isinstance(propriedades, dict) else None
            encontrados.append((str(nome), float(largura) if largura is not None else None))
    return encontrados


def _total_thickness_quantity(element: ifcopenshell.entity_instance) -> float | None:
    """Espessura total do elemento no conjunto de quantidades (Width/Depth)."""
    nomes = _THICKNESS_QUANTITY.get(element.is_a())
    if not nomes:
        return None
    try:
        qtos = ifcopenshell.util.element.get_psets(element, qtos_only=True)
    except Exception:
        return None

    for nome in nomes:
        for quantities in qtos.values():
            if not isinstance(quantities, dict):
                continue
            valor = quantities.get(nome)
            if isinstance(valor, (int, float)) and valor > 0:
                return float(valor)
    return None


def _strip_duplicate_suffix(nome: str) -> str:
    """Remove o sufixo ' (2)' que o exportador acrescenta a nomes repetidos."""
    if nome.endswith(")") and " (" in nome:
        base, _, resto = nome.rpartition(" (")
        if resto[:-1].isdigit():
            return base
    return nome


def _read_layer_set(layer_set: ifcopenshell.entity_instance) -> MaterialReading:
    """Lê um IfcMaterialLayerSet (formato clássico, com espessura no próprio material)."""
    layers: list[dict[str, Any]] = []
    for layer in layer_set.MaterialLayers or []:
        espessura = layer.LayerThickness
        layers.append(
            {
                "name": layer.Material.Name if layer.Material else None,
                "thickness_m": float(espessura) if espessura is not None else None,
            }
        )
    total = sum(lay["thickness_m"] or 0.0 for lay in layers)
    return MaterialReading(
        material_name=getattr(layer_set, "LayerSetName", None),
        layers=layers,
        total_thickness_m=total if total > 0 else None,
    )


def _read_constituent_set(
    element: ifcopenshell.entity_instance,
    constituent_set: ifcopenshell.entity_instance,
) -> MaterialReading:
    """Lê um IfcMaterialConstituentSet, buscando a espessura nas quantidades."""
    constituintes = constituent_set.MaterialConstituents or []
    nomes = [
        (c.Material.Name if c.Material else None) or getattr(c, "Name", None)
        for c in constituintes
    ]

    quantidades = _layer_quantities(element)
    espessuras: list[float | None] = [None] * len(nomes)
    if len(quantidades) == len(nomes):
        # Mesma cardinalidade: o exportador emite camadas e quantidades na mesma ordem.
        espessuras = [largura for _, largura in quantidades]
    elif quantidades:
        # Cardinalidades diferentes: casa pelo nome (ignorando o sufixo de repetido).
        por_nome: dict[str, float | None] = {}
        for nome, largura in quantidades:
            por_nome.setdefault(_strip_duplicate_suffix(nome), largura)
        espessuras = [por_nome.get(_strip_duplicate_suffix(n or "")) for n in nomes]

    layers = [
        {"name": nome, "thickness_m": espessura}
        for nome, espessura in zip(nomes, espessuras)
    ]
    soma = sum(e for e in espessuras if e)
    return MaterialReading(
        material_name=getattr(constituent_set, "Name", None),
        layers=layers,
        total_thickness_m=(soma if soma > 0 else _total_thickness_quantity(element)),
    )


def read_material_layers(element: ifcopenshell.entity_instance) -> MaterialReading:
    """Lê material e camadas do elemento, em qualquer um dos formatos usuais.

    Cobre ``IfcMaterialLayerSetUsage``, ``IfcMaterialLayerSet``,
    ``IfcMaterialConstituentSet`` (Revit) e ``IfcMaterial`` único. Nunca lança:
    um elemento sem material devolve leitura vazia.
    """
    try:
        material = ifcopenshell.util.element.get_material(element)
    except Exception as exc:
        logger.debug("Erro ao ler material de {}: {}", element.is_a(), exc)
        return MaterialReading()

    if material is None:
        return MaterialReading()

    try:
        if material.is_a("IfcMaterialLayerSetUsage"):
            return _read_layer_set(material.ForLayerSet)
        if material.is_a("IfcMaterialLayerSet"):
            return _read_layer_set(material)
        if material.is_a("IfcMaterialConstituentSet"):
            return _read_constituent_set(element, material)
        if material.is_a("IfcMaterial"):
            return MaterialReading(
                material_name=material.Name,
                layers=[{"name": material.Name, "thickness_m": None}],
                total_thickness_m=_total_thickness_quantity(element),
            )
    except Exception as exc:
        logger.warning("Erro ao interpretar material de {}: {}", element.is_a(), exc)

    return MaterialReading(material_name=getattr(material, "Name", None))
