"""Masking precisa cobrir o tipo e o Reference, não só a instância.

Auditoria de 2026-07-27: no ``predio_v1_masked.ifc``, o espaço cujo ``LongName``
foi removido ainda carregava o nome original em dois lugares:

    IfcSpaceType.Name          = 'Lava Pés 61:1373227'
    Pset_SpaceCommon.Reference = 'Lava Pés 61'

Hoje nada disso chega ao prompt, então o benchmark não foi contaminado. Mas o
vazamento é real e bloqueia uma melhoria óbvia do produto: ler o nome do tipo é
evidência legítima para nomear ambiente. As duas coisas têm de andar juntas —
mascarar o tipo e só então deixar o extrator lê-lo.
"""

from __future__ import annotations

import ifcopenshell
import ifcopenshell.guid

from src.experiment.mask_extractor import mask_space_names


def _modelo_com_espaco_nomeado() -> tuple[ifcopenshell.file, ifcopenshell.entity_instance]:
    f = ifcopenshell.file(schema="IFC4")
    space = f.create_entity(
        "IfcSpace", GlobalId=ifcopenshell.guid.new(), Name="61", LongName="Lava Pés"
    )
    space_type = f.create_entity(
        "IfcSpaceType", GlobalId=ifcopenshell.guid.new(), Name="Lava Pés 61:1373227"
    )
    f.create_entity(
        "IfcRelDefinesByType",
        GlobalId=ifcopenshell.guid.new(),
        RelatedObjects=[space],
        RelatingType=space_type,
    )
    pset = f.create_entity(
        "IfcPropertySet",
        GlobalId=ifcopenshell.guid.new(),
        Name="Pset_SpaceCommon",
        HasProperties=[
            f.create_entity(
                "IfcPropertySingleValue",
                Name="Reference",
                NominalValue=f.create_entity("IfcLabel", "Lava Pés 61"),
            ),
            f.create_entity(
                "IfcPropertySingleValue",
                Name="IsExternal",
                NominalValue=f.create_entity("IfcBoolean", False),
            ),
        ],
    )
    f.create_entity(
        "IfcRelDefinesByProperties",
        GlobalId=ifcopenshell.guid.new(),
        RelatedObjects=[space],
        RelatingPropertyDefinition=pset,
    )
    return f, space


def test_nome_do_tipo_e_mascarado():
    f, space = _modelo_com_espaco_nomeado()

    mask_space_names(f)

    tipo = f.by_type("IfcSpaceType")[0]
    assert "Lava" not in (tipo.Name or ""), "nome original sobreviveu no IfcSpaceType"


def test_reference_do_pset_e_mascarado():
    f, space = _modelo_com_espaco_nomeado()

    mask_space_names(f)

    import ifcopenshell.util.element as ue

    psets = ue.get_psets(space)
    referencia = str(psets.get("Pset_SpaceCommon", {}).get("Reference") or "")
    assert "Lava" not in referencia, "nome original sobreviveu no Reference"


def test_mascaramento_preserva_o_resto_do_pset():
    """Só o nome vaza; IsExternal e as quantidades continuam sendo evidência."""
    f, space = _modelo_com_espaco_nomeado()

    mask_space_names(f)

    import ifcopenshell.util.element as ue

    psets = ue.get_psets(space)
    assert psets["Pset_SpaceCommon"]["IsExternal"] is False


def test_ground_truth_guarda_o_nome_original():
    f, _ = _modelo_com_espaco_nomeado()

    items = mask_space_names(f)

    assert len(items) == 1
    assert items[0].expected_value == "Lava Pés"


def test_tipo_compartilhado_por_varios_espacos_nao_quebra():
    """Um IfcSpaceType pode servir a vários espaços; mascarar duas vezes é seguro."""
    f, space = _modelo_com_espaco_nomeado()
    outro = f.create_entity(
        "IfcSpace", GlobalId=ifcopenshell.guid.new(), Name="62", LongName="Lava Pés"
    )
    tipo = f.by_type("IfcSpaceType")[0]
    f.create_entity(
        "IfcRelDefinesByType",
        GlobalId=ifcopenshell.guid.new(),
        RelatedObjects=[outro],
        RelatingType=tipo,
    )

    items = mask_space_names(f)

    assert len(items) == 2
    assert "Lava" not in (tipo.Name or "")
