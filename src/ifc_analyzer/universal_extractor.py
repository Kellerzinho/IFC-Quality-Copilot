"""Extrator universal de contexto IFC para qualquer elemento e qualquer IDS.

Produz um dicionário rico e genérico com todos os dados disponíveis no
modelo IFC para um elemento, independentemente do perfil ou IDS carregado.

Usado como fallback quando nenhum perfil define required_extractors, garantindo
que sugestões LLM sempre tenham contexto relevante para qualquer propriedade IDS.
"""

from typing import Any

import ifcopenshell
import ifcopenshell.util.element
from loguru import logger


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Chaves internas do IfcOpenShell que não devem aparecer no contexto
_INTERNAL_KEYS: frozenset[str] = frozenset({"id"})

# Número máximo de propriedades incluídas por Pset no resumo compacto
_MAX_PROPS_PER_PSET = 20

# Número máximo de Psets incluídos no resumo
_MAX_PSETS = 15


class UniversalExtractor:
    """Extrai todo o contexto disponível de um elemento IFC.

    Independente de classe de elemento ou perfil de análise. Útil para
    enriquecer issues geradas a partir de IDS customizados onde não há
    perfil pré-definido com required_extractors.
    """

    def __init__(self, ifc_file: ifcopenshell.file) -> None:
        self.ifc_file = ifc_file

    def extract(self, element: ifcopenshell.entity_instance) -> dict[str, Any]:
        """Extrai contexto completo de um elemento IFC.

        Retorna dict com:
          - all_psets: resumo compacto de todos os Psets com seus valores
          - material_name, layers, total_thickness_m: material do elemento
          - geometry: quantidades disponíveis (de Qto_* sets)
          - classification: código e sistema de classificação, se houver
          - containing_space: nome do espaço contentor
          - floor: nome do pavimento
          - existing_properties: lista de (pset.prop) que já têm valor preenchido
          - attributes: atributos IFC diretos (Name, LongName, Description, ObjectType)
        """
        result: dict[str, Any] = {}

        try:
            result.update(self._extract_attributes(element))
        except Exception as exc:
            logger.debug("UniversalExtractor: erro em _extract_attributes: {}", exc)

        try:
            result.update(self._extract_psets_summary(element))
        except Exception as exc:
            logger.debug("UniversalExtractor: erro em _extract_psets_summary: {}", exc)

        try:
            result.update(self._extract_material(element))
        except Exception as exc:
            logger.debug("UniversalExtractor: erro em _extract_material: {}", exc)

        try:
            result.update(self._extract_quantities(element))
        except Exception as exc:
            logger.debug("UniversalExtractor: erro em _extract_quantities: {}", exc)

        try:
            result.update(self._extract_classification(element))
        except Exception as exc:
            logger.debug("UniversalExtractor: erro em _extract_classification: {}", exc)

        try:
            result.update(self._extract_spatial(element))
        except Exception as exc:
            logger.debug("UniversalExtractor: erro em _extract_spatial: {}", exc)

        try:
            result["existing_properties"] = self._list_existing_properties(element)
        except Exception as exc:
            logger.debug("UniversalExtractor: erro em _list_existing_properties: {}", exc)

        return result

    # ------------------------------------------------------------------
    # Extratores internos
    # ------------------------------------------------------------------

    def _extract_attributes(self, element: ifcopenshell.entity_instance) -> dict[str, Any]:
        """Extrai atributos IFC diretos do elemento."""
        return {
            "ifc_name": getattr(element, "Name", None),
            "ifc_long_name": getattr(element, "LongName", None),
            "ifc_description": getattr(element, "Description", None),
            "object_type": getattr(element, "ObjectType", None),
            "predefined_type": getattr(element, "PredefinedType", None),
            "ifc_class": element.is_a(),
        }

    def _extract_psets_summary(self, element: ifcopenshell.entity_instance) -> dict[str, Any]:
        """Extrai resumo compacto de todos os Psets do elemento."""
        try:
            raw_psets = ifcopenshell.util.element.get_psets(element)
        except Exception:
            return {"all_psets": {}}

        summary: dict[str, dict[str, Any]] = {}
        pset_count = 0
        for pset_name, props in raw_psets.items():
            if pset_count >= _MAX_PSETS:
                break
            if not isinstance(props, dict):
                continue
            filtered = {
                k: v for k, v in props.items()
                if k not in _INTERNAL_KEYS and v is not None
            }
            if filtered:
                summary[pset_name] = dict(list(filtered.items())[:_MAX_PROPS_PER_PSET])
                pset_count += 1

        return {"all_psets": summary}

    def _extract_material(self, element: ifcopenshell.entity_instance) -> dict[str, Any]:
        """Extrai informações de material e camadas."""
        result: dict[str, Any] = {
            "material_name": None,
            "total_thickness_m": None,
            "layers": [],
        }

        try:
            material = ifcopenshell.util.element.get_material(element)
        except Exception:
            return result

        if material is None:
            return result

        if material.is_a("IfcMaterialLayerSetUsage"):
            layer_set = material.ForLayerSet
            result.update(self._read_layer_set(layer_set))

        elif material.is_a("IfcMaterialLayerSet"):
            result.update(self._read_layer_set(material))

        elif material.is_a("IfcMaterialConstituentSet"):
            constituents = []
            for c in (material.MaterialConstituents or []):
                mat_name = c.Material.Name if c.Material else None
                fraction = getattr(c, "Fraction", None)
                constituents.append({"name": mat_name, "fraction": fraction})
            result["material_name"] = getattr(material, "Name", None)
            result["layers"] = constituents

        elif material.is_a("IfcMaterial"):
            result["material_name"] = material.Name

        else:
            result["material_name"] = getattr(material, "Name", None)

        return result

    def _read_layer_set(self, layer_set: ifcopenshell.entity_instance) -> dict[str, Any]:
        layers = []
        total = 0.0
        for layer in (layer_set.MaterialLayers or []):
            mat_name = layer.Material.Name if layer.Material else None
            thickness = float(layer.LayerThickness or 0.0)
            total += thickness
            layers.append({"name": mat_name, "thickness_m": thickness})

        set_name = getattr(layer_set, "LayerSetName", None)
        if not set_name and layers:
            set_name = layers[0]["name"]

        return {
            "material_name": set_name,
            "total_thickness_m": total if total > 0 else None,
            "layers": layers,
        }

    def _extract_quantities(self, element: ifcopenshell.entity_instance) -> dict[str, Any]:
        """Extrai quantidades de base de Qto_* sets."""
        try:
            qtos = ifcopenshell.util.element.get_psets(element, qtos_only=True)
        except Exception:
            return {}

        geometry: dict[str, Any] = {}
        for qto_data in qtos.values():
            if not isinstance(qto_data, dict):
                continue
            for k, v in qto_data.items():
                if k in _INTERNAL_KEYS or v is None:
                    continue
                if isinstance(v, (int, float)):
                    geometry[k] = v

        return {"geometry": geometry} if geometry else {}

    def _extract_classification(self, element: ifcopenshell.entity_instance) -> dict[str, Any]:
        """Extrai referência de classificação IFC, se houver."""
        result: dict[str, Any] = {
            "has_classification": False,
            "classification_system": None,
            "classification_code": None,
            "classification_name": None,
        }

        for rel in getattr(element, "HasAssociations", []):
            if rel.is_a("IfcRelAssociatesClassification"):
                ref = rel.RelatingClassification
                if ref is None:
                    continue
                result["has_classification"] = True
                if ref.is_a("IfcClassificationReference"):
                    result["classification_code"] = getattr(ref, "Identification", None) or getattr(ref, "ItemReference", None)
                    result["classification_name"] = getattr(ref, "Name", None)
                    source = getattr(ref, "ReferencedSource", None)
                    if source is not None:
                        result["classification_system"] = getattr(source, "Name", None)
                elif ref.is_a("IfcClassification"):
                    result["classification_system"] = getattr(ref, "Name", None)
                break

        return result

    def _extract_spatial(self, element: ifcopenshell.entity_instance) -> dict[str, Any]:
        """Extrai localização espacial: pavimento e espaço contentor."""
        result: dict[str, Any] = {
            "containing_space": None,
            "floor": None,
        }

        for rel in self.ifc_file.by_type("IfcRelContainedInSpatialStructure"):
            if element not in rel.RelatedElements:
                continue
            structure = rel.RelatingStructure
            if structure.is_a("IfcBuildingStorey"):
                result["floor"] = getattr(structure, "Name", None)
            elif structure.is_a("IfcSpace"):
                result["containing_space"] = getattr(structure, "LongName", None) or getattr(structure, "Name", None)
            break

        return result

    def _list_existing_properties(
        self, element: ifcopenshell.entity_instance
    ) -> list[str]:
        """Retorna lista de 'Pset.Prop' que já têm valor preenchido.

        Útil para o LLM entender o que está disponível e o que falta.
        """
        try:
            psets = ifcopenshell.util.element.get_psets(element)
        except Exception:
            return []

        filled: list[str] = []
        for pset_name, props in psets.items():
            if not isinstance(props, dict):
                continue
            for prop_name, value in props.items():
                if prop_name in _INTERNAL_KEYS:
                    continue
                if value is not None and str(value).strip() not in ("", "None"):
                    filled.append(f"{pset_name}.{prop_name}")

        return filled
