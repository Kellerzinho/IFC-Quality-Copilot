"""Módulo responsável por executar correções no arquivo IFC após aprovação humana."""

import os
from typing import Any

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.util.element

from loguru import logger

from src.suggestion_engine.normalization import normalize_fire_rating, parse_numeric_value

# Mapeamento de sufixo de nome → (tipo IFC, atributo de valor)
_QTY_TYPE_MAP: dict[str, tuple[str, str]] = {
    "area": ("IfcQuantityArea", "AreaValue"),
    "length": ("IfcQuantityLength", "LengthValue"),
    "height": ("IfcQuantityLength", "LengthValue"),
    "width": ("IfcQuantityLength", "LengthValue"),
    "perimeter": ("IfcQuantityLength", "LengthValue"),
    "volume": ("IfcQuantityVolume", "VolumeValue"),
    "count": ("IfcQuantityCount", "CountValue"),
}


def _quantity_ifc_type(name: str) -> tuple[str, str]:
    """Retorna (tipo_ifc, atributo_valor) para o nome de uma quantidade."""
    lower = name.lower()
    for suffix, info in _QTY_TYPE_MAP.items():
        if lower.endswith(suffix):
            return info
    return ("IfcQuantityLength", "LengthValue")


def _read_qty_value(q: ifcopenshell.entity_instance) -> float | None:
    """Lê o valor numérico de uma IfcPhysicalSimpleQuantity."""
    if q.is_a("IfcQuantityArea"):
        return q.AreaValue
    if q.is_a("IfcQuantityVolume"):
        return q.VolumeValue
    if q.is_a("IfcQuantityCount"):
        return q.CountValue
    return getattr(q, "LengthValue", None)


def _set_qty_value(q: ifcopenshell.entity_instance, value: float) -> None:
    """Define o valor numérico de uma IfcPhysicalSimpleQuantity."""
    if q.is_a("IfcQuantityArea"):
        q.AreaValue = value
    elif q.is_a("IfcQuantityVolume"):
        q.VolumeValue = value
    elif q.is_a("IfcQuantityCount"):
        q.CountValue = value
    else:
        q.LengthValue = value


class IFCWriter:
    """Executa correções no arquivo IFC após aprovação humana."""

    def __init__(self, ifc_file: ifcopenshell.file) -> None:
        self.ifc_file = ifc_file

    def renomear_espaco(self, guid: str, novo_long_name: str) -> tuple[bool, str | None]:
        """Renomeia o LongName de um IfcSpace.

        Valida que o GUID existe e pertence a um IfcSpace, então atualiza apenas
        o LongName, preservando o Name original.

        Args:
            guid: GlobalId do IfcSpace a ser renomeado.
            novo_long_name: Novo valor para o atributo LongName.

        Returns:
            Tupla (sucesso, valor_anterior):
                - (True, valor_anterior) quando a alteração foi realizada.
                - (False, None) quando LongName já era o valor desejado (noop).

        Raises:
            ValueError: Se o GUID não existe no modelo ou novo_long_name for vazio.
            TypeError: Se o elemento encontrado não for um IfcSpace.
        """
        if not novo_long_name:
            raise ValueError(f"novo_long_name não pode ser vazio (guid={guid})")

        try:
            element = self.ifc_file.by_guid(guid)
        except RuntimeError:
            raise ValueError(f"GUID não encontrado no modelo: {guid}")

        if not element.is_a("IfcSpace"):
            raise TypeError(
                f"Elemento {guid} é {element.is_a()}, esperado IfcSpace"
            )

        valor_anterior = element.LongName or ""
        if valor_anterior == novo_long_name:
            logger.debug("renomear_espaco: LongName já é '{}', noop (guid={})", novo_long_name, guid)
            return False, None

        element.LongName = novo_long_name
        logger.info(
            "renomear_espaco: guid={} | '{}' → '{}'",
            guid,
            valor_anterior,
            novo_long_name,
        )
        return True, valor_anterior

    def preencher_pset(
        self, guid: str, pset_name: str, properties: dict[str, Any]
    ) -> tuple[bool, dict]:
        """Cria ou atualiza propriedades em um Property Set.

        Busca o elemento pelo GUID e verifica se o Pset já existe. Se não
        existir, cria via add_pset antes de editar. Os tipos Python são
        mapeados para tipos IFC pela API do ifcopenshell:
            bool  → IfcBoolean
            float → IfcReal (ou medida específica, ex: IfcThermalTransmittanceMeasure)
            str   → IfcLabel
            int   → IfcInteger

        Args:
            guid: GlobalId do elemento IFC a ser modificado.
            pset_name: Nome do Property Set (ex: "Pset_WallCommon").
            properties: Dicionário {nome_propriedade: valor} a criar/atualizar.

        Returns:
            Tupla (sucesso, valores_anteriores) onde valores_anteriores contém
            apenas as propriedades que já existiam antes da edição.

        Raises:
            ValueError: Se o GUID não existe no modelo.
        """
        try:
            element = self.ifc_file.by_guid(guid)
        except RuntimeError:
            raise ValueError(f"GUID não encontrado no modelo: {guid}")

        psets = ifcopenshell.util.element.get_psets(element)
        valores_anteriores: dict = {}

        if pset_name in psets:
            pset_data = psets[pset_name]
            pset_entity = self.ifc_file.by_id(pset_data["id"])
            for prop_name in properties:
                if prop_name in pset_data:
                    valores_anteriores[prop_name] = pset_data[prop_name]
        else:
            pset_entity = ifcopenshell.api.run(
                "pset.add_pset", self.ifc_file, product=element, name=pset_name
            )

        coerced_properties = {
            prop_name: self._coerce_property_value(prop_name, prop_value)
            for prop_name, prop_value in properties.items()
        }

        ifcopenshell.api.run(
            "pset.edit_pset", self.ifc_file, pset=pset_entity, properties=coerced_properties
        )

        logger.info(
            "preencher_pset: guid={} pset={} props={}",
            guid,
            pset_name,
            list(coerced_properties.keys()),
        )
        return True, valores_anteriores

    def criar_relacao_fills(
        self, door_guid: str, wall_guid: str
    ) -> tuple[bool, None]:
        """Cria IfcRelFillsElement entre uma porta/janela e uma abertura na parede.

        Busca o elemento de abertura (IfcOpeningElement) já existente na parede
        sem preenchimento. Se não existir, cria um novo. Se a porta já possui
        IfcRelFillsElement, retorna noop.

        Args:
            door_guid: GlobalId do IfcDoor ou IfcWindow a ser vinculado.
            wall_guid: GlobalId do IfcWall que contém (ou conterá) a abertura.

        Returns:
            (True, None) quando a relação foi criada.
            (False, None) quando a porta já possui IfcRelFillsElement.

        Raises:
            ValueError: Se qualquer GUID não existe no modelo.
            TypeError: Se door_guid não é IfcDoor/IfcWindow ou wall_guid não é IfcWall.
        """
        try:
            door = self.ifc_file.by_guid(door_guid)
        except RuntimeError:
            raise ValueError(f"GUID não encontrado no modelo: {door_guid}")

        try:
            wall = self.ifc_file.by_guid(wall_guid)
        except RuntimeError:
            raise ValueError(f"GUID não encontrado no modelo: {wall_guid}")

        if not door.is_a("IfcDoor") and not door.is_a("IfcWindow"):
            raise TypeError(
                f"Elemento {door_guid} é {door.is_a()}, esperado IfcDoor ou IfcWindow"
            )
        if not wall.is_a("IfcWall"):
            raise TypeError(
                f"Elemento {wall_guid} é {wall.is_a()}, esperado IfcWall"
            )

        # Verificar se a porta já possui IfcRelFillsElement
        existing_fills = [
            rel
            for rel in self.ifc_file.by_type("IfcRelFillsElement")
            if rel.RelatedBuildingElement == door
        ]
        if existing_fills:
            logger.debug("criar_relacao_fills: porta {} já tem fills, noop", door_guid)
            return False, None

        # Procurar opening na parede sem preenchimento
        wall_openings = [
            rel.RelatedOpeningElement
            for rel in self.ifc_file.by_type("IfcRelVoidsElement")
            if rel.RelatingBuildingElement == wall
        ]
        filled_openings = {
            rel.RelatingOpeningElement
            for rel in self.ifc_file.by_type("IfcRelFillsElement")
        }
        orphan_openings = [o for o in wall_openings if o not in filled_openings]

        if orphan_openings:
            opening = orphan_openings[0]
            logger.debug(
                "criar_relacao_fills: reusando opening existente {} para porta {}",
                opening.GlobalId,
                door_guid,
            )
        else:
            opening = self.ifc_file.create_entity(
                "IfcOpeningElement",
                GlobalId=ifcopenshell.guid.new(),
                Name=f"Opening-{door.Name or door_guid}",
            )
            self.ifc_file.create_entity(
                "IfcRelVoidsElement",
                GlobalId=ifcopenshell.guid.new(),
                RelatingBuildingElement=wall,
                RelatedOpeningElement=opening,
            )
            logger.debug(
                "criar_relacao_fills: criado opening {} para parede {}",
                opening.GlobalId,
                wall_guid,
            )

        self.ifc_file.create_entity(
            "IfcRelFillsElement",
            GlobalId=ifcopenshell.guid.new(),
            RelatingOpeningElement=opening,
            RelatedBuildingElement=door,
        )
        logger.info("criar_relacao_fills: door={} wall={}", door_guid, wall_guid)
        return True, None

    def classificar_sistema(
        self,
        element_guid: str,
        sistema: str,
        classification_name: str = "Sistema Construtivo",
    ) -> tuple[bool, str | None]:
        """Adiciona ou atualiza a classificação de sistema construtivo no elemento.

        Busca ou cria um IfcClassification com o nome indicado, depois cria
        IfcClassificationReference vinculando o elemento. Se já existir uma
        referência para o mesmo IfcClassification, remove a anterior e cria a
        nova (atualização).

        Args:
            element_guid: GlobalId do elemento IFC a classificar.
            sistema: Nome do sistema construtivo (valor da referência).
            classification_name: Nome do IfcClassification pai.

        Returns:
            (True, None) quando é uma nova classificação.
            (True, sistema_anterior) quando atualiza uma existente.

        Raises:
            ValueError: Se o GUID não existe no modelo.
        """
        try:
            element = self.ifc_file.by_guid(element_guid)
        except RuntimeError:
            raise ValueError(f"GUID não encontrado no modelo: {element_guid}")

        # Buscar ou criar IfcClassification
        existing = [
            c
            for c in self.ifc_file.by_type("IfcClassification")
            if c.Name == classification_name
        ]
        if existing:
            classification = existing[0]
        else:
            classification = ifcopenshell.api.run(
                "classification.add_classification",
                self.ifc_file,
                classification=classification_name,
            )

        # Verificar se o elemento já tem referência nesta classificação
        sistema_anterior: str | None = None
        old_reference = None
        for rel in self.ifc_file.by_type("IfcRelAssociatesClassification"):
            rc = rel.RelatingClassification
            if element in rel.RelatedObjects and rc.is_a("IfcClassificationReference"):
                source = rc.ReferencedSource
                if (
                    source
                    and source.is_a("IfcClassification")
                    and source.Name == classification_name
                ):
                    old_reference = rc
                    sistema_anterior = rc.Name
                    break

        if old_reference is not None:
            ifcopenshell.api.run(
                "classification.remove_reference",
                self.ifc_file,
                reference=old_reference,
                products=[element],
            )
            logger.debug(
                "classificar_sistema: removida referência anterior '{}' do elemento {}",
                sistema_anterior,
                element_guid,
            )

        ifcopenshell.api.run(
            "classification.add_reference",
            self.ifc_file,
            products=[element],
            classification=classification,
            identification=sistema,
            name=sistema,
        )
        logger.info(
            "classificar_sistema: element={} sistema='{}' (anterior='{}')",
            element_guid,
            sistema,
            sistema_anterior,
        )
        return True, sistema_anterior

    def preencher_base_quantities(
        self, guid: str, qto_name: str, quantities: dict[str, float]
    ) -> tuple[bool, dict]:
        """Cria ou atualiza BaseQuantities (Qto_*) de um elemento.

        Busca ou cria IfcElementQuantity com Name=qto_name. Para cada quantity,
        determina o tipo IFC pelo sufixo do nome (*Area, *Length, *Height,
        *Width, *Perimeter → Length, *Volume, *Count) e cria ou atualiza
        a entidade correspondente. Vincula ao elemento via
        IfcRelDefinesByProperties se ainda não vinculado.

        Args:
            guid: GlobalId do elemento IFC a modificar.
            qto_name: Nome do IfcElementQuantity (ex: "Qto_WallBaseQuantities").
            quantities: Dicionário {nome_quantidade: valor_float} a criar/atualizar.

        Returns:
            Tupla (True, valores_anteriores) onde valores_anteriores contém
            apenas as quantities que já existiam antes da edição.

        Raises:
            ValueError: Se o GUID não existe no modelo.
        """
        try:
            element = self.ifc_file.by_guid(guid)
        except RuntimeError:
            raise ValueError(f"GUID não encontrado no modelo: {guid}")

        valores_anteriores: dict = {}

        # Buscar IfcElementQuantity existente vinculado ao elemento
        qto_entity = None
        for rel in self.ifc_file.by_type("IfcRelDefinesByProperties"):
            if element in rel.RelatedObjects:
                prop_def = rel.RelatingPropertyDefinition
                if prop_def.is_a("IfcElementQuantity") and prop_def.Name == qto_name:
                    qto_entity = prop_def
                    break

        if qto_entity is None:
            qto_entity = ifcopenshell.api.run(
                "pset.add_qto", self.ifc_file, product=element, name=qto_name
            )

        # Indexar quantities existentes por nome
        existing_qtys: dict[str, ifcopenshell.entity_instance] = {
            q.Name: q for q in (qto_entity.Quantities or [])
        }

        # Registrar valores anteriores
        for qty_name in quantities:
            if qty_name in existing_qtys:
                valores_anteriores[qty_name] = _read_qty_value(existing_qtys[qty_name])

        # Atualizar existentes ou criar novas quantities
        new_qtys = list(qto_entity.Quantities or [])
        for qty_name, qty_value in quantities.items():
            if qty_name in existing_qtys:
                _set_qty_value(existing_qtys[qty_name], qty_value)
            else:
                ifc_type, value_attr = _quantity_ifc_type(qty_name)
                new_q = self.ifc_file.create_entity(
                    ifc_type, Name=qty_name, **{value_attr: qty_value}
                )
                new_qtys.append(new_q)

        qto_entity.Quantities = new_qtys

        logger.info(
            "preencher_base_quantities: guid={} qto={} qtys={}",
            guid,
            qto_name,
            list(quantities.keys()),
        )
        return True, valores_anteriores

    def mapear_classificacao(
        self, guid: str, system_name: str, code: str, description: str
    ) -> tuple[bool, str | None]:
        """Cria ou atualiza IfcClassificationReference com sistema de classificação.

        Busca ou cria IfcClassification com Name=system_name. Cria
        IfcClassificationReference com ItemReference=code e Name=description,
        vinculando ao elemento via IfcRelAssociatesClassification. Se o elemento
        já possuir referência do mesmo sistema, remove a anterior e cria a nova.

        Args:
            guid: GlobalId do elemento IFC a classificar.
            system_name: Nome do sistema de classificação (ex: "SINAPI", "Omniclass").
            code: Código de identificação (ex: "87878", "73.10.050").
            description: Descrição legível da classificação.

        Returns:
            (True, None) quando é uma nova classificação.
            (True, code_anterior) quando atualiza uma classificação existente.

        Raises:
            ValueError: Se o GUID não existe no modelo.
        """
        try:
            element = self.ifc_file.by_guid(guid)
        except RuntimeError:
            raise ValueError(f"GUID não encontrado no modelo: {guid}")

        # Buscar ou criar IfcClassification
        existing = [
            c
            for c in self.ifc_file.by_type("IfcClassification")
            if c.Name == system_name
        ]
        if existing:
            classification = existing[0]
        else:
            classification = ifcopenshell.api.run(
                "classification.add_classification",
                self.ifc_file,
                classification=system_name,
            )

        # Verificar se o elemento já tem referência neste sistema
        code_anterior: str | None = None
        old_reference = None
        for rel in self.ifc_file.by_type("IfcRelAssociatesClassification"):
            rc = rel.RelatingClassification
            if element in rel.RelatedObjects and rc.is_a("IfcClassificationReference"):
                source = rc.ReferencedSource
                if (
                    source
                    and source.is_a("IfcClassification")
                    and source.Name == system_name
                ):
                    old_reference = rc
                    code_anterior = getattr(rc, "ItemReference", None) or getattr(
                        rc, "Identification", None
                    )
                    break

        if old_reference is not None:
            ifcopenshell.api.run(
                "classification.remove_reference",
                self.ifc_file,
                reference=old_reference,
                products=[element],
            )
            logger.debug(
                "mapear_classificacao: removida referência anterior '{}' do elemento {}",
                code_anterior,
                guid,
            )

        ifcopenshell.api.run(
            "classification.add_reference",
            self.ifc_file,
            products=[element],
            classification=classification,
            identification=code,
            name=description,
        )
        logger.info(
            "mapear_classificacao: element={} sistema='{}' code='{}' (anterior='{}')",
            guid,
            system_name,
            code,
            code_anterior,
        )
        return True, code_anterior

    def associar_zona_termica(
        self, space_guid: str, zone_name: str, zone_type: str = "thermal"
    ) -> tuple[bool, None]:
        """Associa IfcSpace a uma IfcZone para zoneamento térmico/HVAC.

        Busca IfcZone com Name=zone_name; se não existe, cria. Adiciona o
        IfcSpace à zona via IfcRelAssignsToGroup. Se o espaço já pertence à
        zona, retorna noop.

        Args:
            space_guid: GlobalId do IfcSpace a associar.
            zone_name: Nome da zona (ex: "Zona Norte", "HVAC-01").
            zone_type: Tipo semântico da zona ("thermal", "hvac", "lighting").

        Returns:
            (True, None) quando o espaço foi adicionado à zona.
            (False, None) quando o espaço já pertencia à zona.

        Raises:
            ValueError: Se o GUID não existe no modelo.
            TypeError: Se o elemento não for um IfcSpace.
        """
        try:
            space = self.ifc_file.by_guid(space_guid)
        except RuntimeError:
            raise ValueError(f"GUID não encontrado no modelo: {space_guid}")

        if not space.is_a("IfcSpace"):
            raise TypeError(
                f"Elemento {space_guid} é {space.is_a()}, esperado IfcSpace"
            )

        # Buscar ou criar IfcZone
        existing_zones = [
            z for z in self.ifc_file.by_type("IfcZone") if z.Name == zone_name
        ]
        if existing_zones:
            zone = existing_zones[0]
        else:
            zone = ifcopenshell.api.run(
                "root.create_entity", self.ifc_file, ifc_class="IfcZone", name=zone_name
            )
            zone.ObjectType = zone_type
            logger.debug("associar_zona_termica: criada zona '{}' ({})", zone_name, zone_type)

        # Verificar se o espaço já está na zona
        for rel in self.ifc_file.by_type("IfcRelAssignsToGroup"):
            if rel.RelatingGroup == zone and space in rel.RelatedObjects:
                logger.debug(
                    "associar_zona_termica: space {} já está na zona '{}', noop",
                    space_guid,
                    zone_name,
                )
                return False, None

        # Adicionar à relação existente ou criar nova
        zone_rels = [
            rel
            for rel in self.ifc_file.by_type("IfcRelAssignsToGroup")
            if rel.RelatingGroup == zone
        ]
        if zone_rels:
            rel = zone_rels[0]
            rel.RelatedObjects = list(rel.RelatedObjects) + [space]
        else:
            self.ifc_file.create_entity(
                "IfcRelAssignsToGroup",
                GlobalId=ifcopenshell.guid.new(),
                RelatedObjects=[space],
                RelatingGroup=zone,
            )

        logger.info(
            "associar_zona_termica: space={} zona='{}' tipo='{}'",
            space_guid,
            zone_name,
            zone_type,
        )
        return True, None

    def salvar(self, output_path: str) -> str:
        """Salva o modelo IFC modificado em disco.

        Args:
            output_path: Caminho de destino para o arquivo IFC.

        Returns:
            Caminho absoluto do arquivo salvo.
        """
        self.ifc_file.write(output_path)
        absolute_path = os.path.abspath(output_path)
        logger.info("salvar: arquivo salvo em {}", absolute_path)
        return absolute_path

    def _coerce_property_value(self, prop_name: str, prop_value: Any) -> Any:
        """Aplica coercao defensiva por propriedade antes de escrever no IFC."""
        if prop_name == "ThermalTransmittance":
            normalized = parse_numeric_value(prop_value)
            if normalized is None:
                raise ValueError("ThermalTransmittance invalido para escrita")
            return normalized
        if prop_name == "FireRating":
            normalized = normalize_fire_rating(prop_value)
            if normalized is None:
                raise ValueError("FireRating invalido para escrita")
            return normalized
        return prop_value
