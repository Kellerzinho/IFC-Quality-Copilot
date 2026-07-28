"""Evidências que faltavam no prompt (auditoria do benchmark 2026-07-28).

Dois vazios medidos no dump de prompts do run limpo:

1. ``IfcRoof`` chegava ao prompt térmico com ``Material: None`` e camadas
   "não informado" — o Revit agrega o material nas partes (``IfcRelAggregates``)
   e o leitor unificado não descia até elas. Todos os 10 modelos erraram os
   telhados.
2. ``IfcSpace.Category`` era pedido mostrando só o ``Name`` numérico ("64"),
   descartando o ``LongName`` — o campo em que o projetista declarou o uso.
"""

from __future__ import annotations

import ifcopenshell
import ifcopenshell.guid

from src.ifc_analyzer.material_reader import read_material_layers
from src.ifc_analyzer.pset_diagnostics import diagnose_psets
from src.suggestion_engine.prompt_templates import TEMPLATES, build_prompt
from src.models import Issue


def _roof_com_parte_agregada() -> tuple[ifcopenshell.file, object]:
    f = ifcopenshell.file(schema="IFC4")
    roof = f.create_entity("IfcRoof", GlobalId=ifcopenshell.guid.new(), Name="Telhado")
    slab = f.create_entity("IfcSlab", GlobalId=ifcopenshell.guid.new(), Name="Aba do telhado")

    mat = f.create_entity("IfcMaterial", Name="Fibrocimento ondulado")
    layer = f.create_entity("IfcMaterialLayer", Material=mat, LayerThickness=0.008)
    layer_set = f.create_entity(
        "IfcMaterialLayerSet", MaterialLayers=[layer], LayerSetName="Telha fibrocimento"
    )
    usage = f.create_entity(
        "IfcMaterialLayerSetUsage",
        ForLayerSet=layer_set,
        LayerSetDirection="AXIS3",
        DirectionSense="POSITIVE",
        OffsetFromReferenceLine=0.0,
    )
    f.create_entity(
        "IfcRelAssociatesMaterial",
        GlobalId=ifcopenshell.guid.new(),
        RelatedObjects=[slab],
        RelatingMaterial=usage,
    )
    f.create_entity(
        "IfcRelAggregates",
        GlobalId=ifcopenshell.guid.new(),
        RelatingObject=roof,
        RelatedObjects=[slab],
    )
    return f, roof


def test_ifcroof_sem_material_proprio_herda_das_partes_agregadas():
    _, roof = _roof_com_parte_agregada()

    leitura = read_material_layers(roof)

    assert leitura.layers, "o telhado deve herdar as camadas da parte agregada"
    assert leitura.layers[0]["name"] == "Fibrocimento ondulado"
    assert leitura.total_thickness_m == 0.008


def test_elemento_sem_material_e_sem_partes_continua_vazio():
    f = ifcopenshell.file(schema="IFC4")
    roof = f.create_entity("IfcRoof", GlobalId=ifcopenshell.guid.new(), Name="Nu")

    leitura = read_material_layers(roof)

    assert leitura.material_name is None
    assert leitura.layers == []


def test_categoria_de_espaco_contextualiza_long_name():
    f = ifcopenshell.file(schema="IFC4")
    f.create_entity(
        "IfcSpace", GlobalId=ifcopenshell.guid.new(), Name="64", LongName="Sacada"
    )

    issues = diagnose_psets(f)

    category = [
        i for i in issues if i.context.get("check_property") == "Category"
    ]
    assert category, "espaço sem Pset_SpaceCommon.Category deve gerar issue"
    assert category[0].context.get("long_name") == "Sacada"


def test_template_de_category_mostra_long_name_no_prompt():
    assert "{long_name}" in TEMPLATES["pset_missing_space_category"]

    issue = Issue(
        element_guid="3nJOFsJsX8QO2odKZbQnBj",
        element_class="IfcSpace",
        issue_type="pset_missing",
        severity="medium",
        description="Category ausente",
        context={
            "check_property": "Category",
            "pset_name": "Pset_SpaceCommon",
            "long_name": "Uso Declarado Qualquer",
            "area_m2": 6.3,
            "contained_elements": [],
        },
    )
    _, user = build_prompt(issue, {"building_type": "X", "bioclimatic_zone": "3"})

    assert "Uso Declarado Qualquer" in user
