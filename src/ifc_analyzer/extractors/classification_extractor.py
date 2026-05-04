"""Extrator de dados de classificação de elementos IFC para orçamento e compliance."""

import ifcopenshell
import ifcopenshell.util.element
from loguru import logger


# Classes IFC verificadas por padrão em get_unclassified_elements
_DEFAULT_TARGET_CLASSES: list[str] = [
    "IfcWall",
    "IfcSlab",
    "IfcDoor",
    "IfcWindow",
    "IfcBeam",
    "IfcColumn",
    "IfcFurnishingElement",
]

# Tabela de palavras-chave de material → categoria sugestiva para orçamento.
# Formato: [(keyword_lowercase, categoria_sugerida), ...]
# Segue nomenclatura de grupos de insumos típicos em composições de custo unitário.
_MATERIAL_CATEGORY_TABLE: list[tuple[str, str]] = [
    ("concreto", "Estruturas de Concreto"),
    ("concrete", "Estruturas de Concreto"),
    ("armado", "Estruturas de Concreto Armado"),
    ("aço", "Estruturas Metálicas"),
    ("aco", "Estruturas Metálicas"),
    ("steel", "Estruturas Metálicas"),
    ("alvenaria", "Vedações em Alvenaria"),
    ("bloco ceram", "Vedações em Alvenaria Cerâmica"),
    ("cerâmico", "Vedações em Alvenaria Cerâmica"),
    ("ceramico", "Vedações em Alvenaria Cerâmica"),
    ("drywall", "Vedações em Drywall"),
    ("gesso acartonado", "Vedações em Drywall"),
    ("gesso", "Revestimentos em Gesso"),
    ("eps", "Isolamentos Térmicos"),
    ("xps", "Isolamentos Térmicos"),
    ("isol", "Isolamentos Térmicos"),
    ("lã mineral", "Isolamentos Térmicos"),
    ("poliuretano", "Isolamentos Térmicos"),
    ("vidro", "Esquadrias e Vidros"),
    ("glass", "Esquadrias e Vidros"),
    ("madeira", "Madeiras e Esquadrias"),
    ("wood", "Madeiras e Esquadrias"),
    ("mármore", "Revestimentos em Pedra"),
    ("marmore", "Revestimentos em Pedra"),
    ("granito", "Revestimentos em Pedra"),
    ("cerâmica", "Revestimentos Cerâmicos"),
    ("ceramica", "Revestimentos Cerâmicos"),
    ("porcelanato", "Revestimentos Cerâmicos"),
    ("tinta", "Pinturas e Revestimentos"),
    ("argamassa", "Argamassas e Revestimentos"),
]


def _get_psets(element: ifcopenshell.entity_instance) -> dict:
    """Wrapper para get_psets que retorna dict vazio em caso de erro."""
    try:
        return ifcopenshell.util.element.get_psets(element)
    except Exception as exc:
        logger.debug(f"Não foi possível obter Psets de {element.is_a()}: {exc}")
        return {}


def _get_classification_ref_code(cls_ref: ifcopenshell.entity_instance) -> str | None:
    """Retorna o código de identificação de uma IfcClassificationReference.

    Tenta o atributo 'Identification' (IFC4) e cai para 'ItemReference' (IFC2X3).
    """
    for attr_name in ("Identification", "ItemReference"):
        try:
            value = getattr(cls_ref, attr_name, None)
            if value is not None:
                return str(value)
        except Exception:
            continue
    return None


def _extract_classification_ref(
    element: ifcopenshell.entity_instance,
) -> tuple[bool, str | None, str | None, str | None]:
    """Percorre HasAssociations buscando IfcRelAssociatesClassification.

    Returns:
        (has_classification, classification_system, classification_code, classification_name)
    """
    try:
        for rel in element.HasAssociations:
            if not rel.is_a("IfcRelAssociatesClassification"):
                continue
            cls_ref = rel.RelatingClassification
            if cls_ref.is_a("IfcClassificationReference"):
                code: str | None = _get_classification_ref_code(cls_ref)
                name: str | None = getattr(cls_ref, "Name", None)
                source = getattr(cls_ref, "ReferencedSource", None)
                system: str | None = None
                if source is not None and source.is_a("IfcClassification"):
                    system = getattr(source, "Name", None)
                return True, system, code, name
            if cls_ref.is_a("IfcClassification"):
                return True, getattr(cls_ref, "Name", None), None, None
    except Exception as exc:
        logger.debug(f"Erro ao extrair classificação de {element.is_a()}: {exc}")
    return False, None, None, None


def _extract_material_classification(element: ifcopenshell.entity_instance) -> str | None:
    """Retorna a classificação associada ao material do elemento, se existir.

    Percorre IfcRelAssociatesMaterial para obter o material principal e então
    verifica se esse material tem IfcRelAssociatesClassification própria.
    """
    try:
        for rel in element.HasAssociations:
            if not rel.is_a("IfcRelAssociatesMaterial"):
                continue
            mat = rel.RelatingMaterial
            material: ifcopenshell.entity_instance | None = None

            if mat.is_a("IfcMaterial"):
                material = mat
            elif mat.is_a("IfcMaterialLayerSetUsage"):
                layer_set = mat.ForLayerSet
                if layer_set and layer_set.MaterialLayers:
                    material = layer_set.MaterialLayers[0].Material
            elif mat.is_a("IfcMaterialLayerSet"):
                if mat.MaterialLayers:
                    material = mat.MaterialLayers[0].Material

            if material is None:
                continue

            for mat_rel in material.HasAssociations:
                if not mat_rel.is_a("IfcRelAssociatesClassification"):
                    continue
                cls_ref = mat_rel.RelatingClassification
                if cls_ref.is_a("IfcClassificationReference"):
                    code = getattr(cls_ref, "ItemReference", None)
                    name = getattr(cls_ref, "Name", None)
                    return code or name
                if cls_ref.is_a("IfcClassification"):
                    return getattr(cls_ref, "Name", None)
    except Exception as exc:
        logger.debug(f"Erro ao extrair classificação de material: {exc}")
    return None


def _get_material_name(element: ifcopenshell.entity_instance) -> str | None:
    """Retorna o nome do material principal do elemento, ou None se indisponível.

    Prioriza o nome do material da primeira camada sobre o nome do layer set,
    pois o LayerSetName costuma ser um identificador do conjunto (ex: "Wall layers"),
    enquanto o material individual contém a designação semântica (ex: "Concreto 20cm").
    """
    try:
        for rel in element.HasAssociations:
            if not rel.is_a("IfcRelAssociatesMaterial"):
                continue
            mat = rel.RelatingMaterial
            if mat.is_a("IfcMaterial"):
                return mat.Name
            if mat.is_a("IfcMaterialLayerSetUsage"):
                layer_set = mat.ForLayerSet
                if layer_set:
                    if layer_set.MaterialLayers:
                        first_mat = layer_set.MaterialLayers[0].Material
                        if first_mat and first_mat.Name:
                            return first_mat.Name
                    if layer_set.LayerSetName:
                        return layer_set.LayerSetName
            if mat.is_a("IfcMaterialLayerSet"):
                if mat.MaterialLayers:
                    first_mat = mat.MaterialLayers[0].Material
                    if first_mat and first_mat.Name:
                        return first_mat.Name
                if mat.LayerSetName:
                    return mat.LayerSetName
    except Exception as exc:
        logger.debug(f"Erro ao obter nome de material: {exc}")
    return None


class ClassificationExtractor:
    """Extrai dados de classificação de elementos IFC para orçamento e compliance."""

    def __init__(self, ifc_file: ifcopenshell.file) -> None:
        """Inicializa o extrator com o arquivo IFC aberto."""
        self.ifc_file = ifc_file

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def extract_classification(self, element: ifcopenshell.entity_instance) -> dict:
        """Extrai dados de classificação de um elemento IFC.

        Verifica IfcRelAssociatesClassification no próprio elemento e
        classificação associada ao material via IfcRelAssociatesMaterial.

        Args:
            element: qualquer instância IFC que suporte HasAssociations.

        Returns:
            Dict com as chaves:
                - has_classification: bool — True se há IfcRelAssociatesClassification
                - classification_system: str | None — nome do IfcClassification (ex: "Uniclass 2015")
                - classification_code: str | None — ItemReference da referência de classificação
                - classification_name: str | None — Name da referência de classificação
                - material_classification: str | None — classificação do material principal
        """
        has_cls, system, code, name = _extract_classification_ref(element)
        material_classification = _extract_material_classification(element)

        return {
            "has_classification": has_cls,
            "classification_system": system,
            "classification_code": code,
            "classification_name": name,
            "material_classification": material_classification,
        }

    def get_unclassified_elements(
        self, target_classes: list[str] | None = None
    ) -> list[dict]:
        """Lista elementos sem IfcRelAssociatesClassification.

        Args:
            target_classes: lista de classes IFC a verificar. Se None, usa o conjunto
                padrão: IfcWall, IfcSlab, IfcDoor, IfcWindow, IfcBeam, IfcColumn,
                IfcFurnishingElement.

        Returns:
            Lista de dicts com guid, ifc_class, name e os campos de extract_classification.
        """
        classes_to_check = target_classes if target_classes is not None else _DEFAULT_TARGET_CLASSES
        result: list[dict] = []
        seen_guids: set[str] = set()

        for ifc_class in classes_to_check:
            try:
                elements = self.ifc_file.by_type(ifc_class)
            except Exception as exc:
                logger.debug(f"Classe {ifc_class} não disponível no schema: {exc}")
                continue

            for element in elements:
                guid = element.GlobalId
                if guid in seen_guids:
                    continue
                seen_guids.add(guid)

                info = self.extract_classification(element)
                if not info["has_classification"]:
                    result.append(
                        {
                            "guid": guid,
                            "ifc_class": element.is_a(),
                            "name": getattr(element, "Name", None),
                            **info,
                        }
                    )

        return result

    def suggest_classification_from_material(
        self, element: ifcopenshell.entity_instance
    ) -> str | None:
        """Tenta inferir categoria de classificação a partir do nome do material.

        Usa tabela interna de palavras-chave de materiais → categorias de insumo
        típicas em composições de custo unitário. Útil como ponto de partida para
        orçamento quando não há classificação formal no elemento.

        Args:
            element: instância IFC com material associado via IfcRelAssociatesMaterial.

        Returns:
            String de categoria sugerida (ex: "Estruturas de Concreto") ou None se
            nenhuma palavra-chave bater no nome do material.
        """
        material_name = _get_material_name(element)
        if not material_name:
            logger.debug(
                f"Sem material para inferir classificação em "
                f"{element.is_a()} #{element.GlobalId[:8]}"
            )
            return None

        lower = material_name.lower()
        for keyword, category in _MATERIAL_CATEGORY_TABLE:
            if keyword in lower:
                logger.debug(
                    f"Classificação sugerida para {element.is_a()} "
                    f"#{element.GlobalId[:8]}: '{category}' (material: '{material_name}')"
                )
                return category

        logger.debug(
            f"Nenhuma categoria encontrada para material '{material_name}' em "
            f"{element.is_a()} #{element.GlobalId[:8]}"
        )
        return None
