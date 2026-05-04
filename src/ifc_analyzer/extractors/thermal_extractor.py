"""Extrator de dados térmicos de elementos IFC para contexto de energia/HVAC."""

import ifcopenshell
import ifcopenshell.util.element
from loguru import logger


# Palavras-chave para detectar camadas de isolamento (case-insensitive)
_INSULATION_KEYWORDS = (
    "eps",
    "xps",
    "isol",
    "lã",
    "la ",
    "manta",
    "poliestireno",
    "poliuretano",
    "rockwool",
    "mineral",
)

# Faixa estimada de transmitância (W/m²K) por palavra-chave no nome do material
# Formato: [(keyword, (u_min, u_max)), ...]
_U_RANGE_TABLE: list[tuple[str, tuple[float, float]]] = [
    ("concreto", (2.0, 3.5)),
    ("concrete", (2.0, 3.5)),
    ("bloco ceram", (1.5, 2.5)),
    ("ceramico", (1.5, 2.5)),
    ("cerâmico", (1.5, 2.5)),
    ("alvenaria", (1.5, 2.5)),
    ("drywall", (1.5, 2.0)),
    ("gesso", (1.5, 2.0)),
    ("eps", (0.3, 0.6)),
    ("xps", (0.25, 0.5)),
    ("isol", (0.3, 0.8)),
    ("lã", (0.3, 0.6)),
    ("mineral", (0.3, 0.6)),
    ("poliuretano", (0.25, 0.5)),
]


def _is_insulation_layer(material_name: str) -> bool:
    """Retorna True se o nome do material sugere isolamento térmico."""
    lower = material_name.lower()
    return any(kw in lower for kw in _INSULATION_KEYWORDS)


def _estimate_u_range(material_name: str) -> tuple[float, float] | None:
    """Estima faixa de transmitância U com base no nome do material."""
    lower = material_name.lower()
    for keyword, u_range in _U_RANGE_TABLE:
        if keyword in lower:
            return u_range
    return None


def _get_psets(element: ifcopenshell.entity_instance) -> dict:
    """Wrapper para get_psets que retorna dict vazio em caso de erro."""
    try:
        return ifcopenshell.util.element.get_psets(element)
    except Exception as exc:
        logger.debug(f"Não foi possível obter Psets de {element.is_a()}: {exc}")
        return {}


def _get_qtos(element: ifcopenshell.entity_instance) -> dict:
    """Wrapper para get_psets(qtos_only=True) que retorna dict vazio em caso de erro."""
    try:
        return ifcopenshell.util.element.get_psets(element, qtos_only=True)
    except Exception as exc:
        logger.debug(f"Não foi possível obter Qtos de {element.is_a()}: {exc}")
        return {}


def _extract_material_layers(
    element: ifcopenshell.entity_instance,
) -> tuple[str | None, list[dict], float | None]:
    """Extrai camadas de material de um elemento via IfcMaterialLayerSetUsage.

    Retorna:
        material_name: nome do conjunto de camadas ou da camada única
        layers: lista de dicts {name, thickness_m, is_insulation}
        total_thickness_m: soma das espessuras, ou None se sem dados
    """
    layers: list[dict] = []
    material_name: str | None = None
    total_thickness_m: float | None = None

    try:
        for rel in element.HasAssociations:
            if rel.is_a("IfcRelAssociatesMaterial"):
                mat = rel.RelatingMaterial
                layer_set = None

                if mat.is_a("IfcMaterialLayerSetUsage"):
                    layer_set = mat.ForLayerSet
                elif mat.is_a("IfcMaterialLayerSet"):
                    layer_set = mat
                elif mat.is_a("IfcMaterial"):
                    material_name = mat.Name
                    return material_name, layers, total_thickness_m

                if layer_set is not None:
                    material_name = layer_set.LayerSetName
                    for layer in layer_set.MaterialLayers:
                        layer_mat = layer.Material
                        name = layer_mat.Name if layer_mat else "Desconhecido"
                        thickness = layer.LayerThickness
                        layers.append(
                            {
                                "name": name,
                                "thickness_m": thickness,
                                "is_insulation": _is_insulation_layer(name),
                            }
                        )
                    if layers:
                        total_thickness_m = sum(l["thickness_m"] for l in layers)
                    break
    except Exception as exc:
        logger.debug(f"Erro ao extrair camadas de {element.is_a()}: {exc}")

    return material_name, layers, total_thickness_m


class ThermalExtractor:
    """Extrai dados térmicos de elementos para contexto de energia/HVAC."""

    def __init__(self, ifc_file: ifcopenshell.file) -> None:
        """Inicializa o extrator com o arquivo IFC aberto."""
        self.ifc_file = ifc_file

    # ------------------------------------------------------------------
    # Extratores por elemento
    # ------------------------------------------------------------------

    def extract_wall_thermal(self, wall: ifcopenshell.entity_instance) -> dict:
        """Extrai dados térmicos de uma IfcWall.

        Retorna:
            is_external: bool | None — extraído de Pset_WallCommon.IsExternal
            thermal_transmittance: float | None — W/m²K de Pset_WallCommon
            absorptance: float | None — absorção solar de Pset_WallCommon
            material_name: str | None — nome do conjunto de material
            layers: list[{name, thickness_m, is_insulation}]
            total_thickness_m: float | None
            has_insulation: bool
            estimated_u_range: tuple[float, float] | None — estimativa pela tabela
        """
        psets = _get_psets(wall)
        wall_common = psets.get("Pset_WallCommon", {})

        is_external: bool | None = wall_common.get("IsExternal")
        thermal_transmittance: float | None = wall_common.get("ThermalTransmittance")
        absorptance: float | None = wall_common.get("SolarAbsorptance")

        material_name, layers, total_thickness_m = _extract_material_layers(wall)
        has_insulation = any(l["is_insulation"] for l in layers)

        # Estima faixa U com base no material principal (primeira camada não-isolamento)
        estimated_u_range: tuple[float, float] | None = None
        dominant_layers = [l for l in layers if not l["is_insulation"]]
        if dominant_layers:
            estimated_u_range = _estimate_u_range(dominant_layers[0]["name"])
        elif material_name:
            estimated_u_range = _estimate_u_range(material_name)

        return {
            "is_external": is_external,
            "thermal_transmittance": thermal_transmittance,
            "absorptance": absorptance,
            "material_name": material_name,
            "layers": layers,
            "total_thickness_m": total_thickness_m,
            "has_insulation": has_insulation,
            "estimated_u_range": estimated_u_range,
        }

    def extract_window_thermal(self, window: ifcopenshell.entity_instance) -> dict:
        """Extrai dados térmicos de uma IfcWindow.

        Retorna:
            thermal_transmittance: float | None — W/m²K de Pset_WindowCommon
            shgc: float | None — Solar Heat Gain Coefficient
            frame_material: str | None
            glazing_type: str | None
        """
        psets = _get_psets(window)
        win_common = psets.get("Pset_WindowCommon", {})

        return {
            "thermal_transmittance": win_common.get("ThermalTransmittance"),
            "shgc": win_common.get("SolarHeatGainCoefficient"),
            "frame_material": win_common.get("FrameMaterial"),
            "glazing_type": win_common.get("GlazingType"),
        }

    def extract_slab_thermal(self, slab: ifcopenshell.entity_instance) -> dict:
        """Extrai dados térmicos de uma IfcSlab.

        Retorna:
            is_external: bool | None — indica se é cobertura
            thermal_transmittance: float | None — W/m²K de Pset_SlabCommon
            material: str | None
            thickness: float | None
        """
        psets = _get_psets(slab)
        slab_common = psets.get("Pset_SlabCommon", {})

        _, layers, total_thickness_m = _extract_material_layers(slab)
        material_name: str | None = None
        if layers:
            material_name = layers[0]["name"]

        return {
            "is_external": slab_common.get("IsExternal"),
            "thermal_transmittance": slab_common.get("ThermalTransmittance"),
            "material": material_name,
            "thickness": total_thickness_m,
        }

    def extract_space_thermal_zone(self, space: ifcopenshell.entity_instance) -> dict:
        """Extrai dados de zoneamento térmico de um IfcSpace.

        Retorna:
            functional_name: str — Name ou LongName do espaço
            is_conditioned: bool | None — inferido por nome ou equipamento HVAC
            adjacent_external_walls: int — paredes externas via IfcRelSpaceBoundary
            has_external_window: bool — se alguma parede externa tem janela
            floor_area: float — área de piso em m²
        """
        functional_name = space.LongName or space.Name or ""
        floor_area = self._get_space_floor_area(space)
        adjacent_external_walls, external_wall_guids = self._count_external_boundaries(space)
        has_external_window = self._space_has_external_window(external_wall_guids)
        is_conditioned = self._infer_conditioning(space)

        return {
            "functional_name": functional_name,
            "is_conditioned": is_conditioned,
            "adjacent_external_walls": adjacent_external_walls,
            "has_external_window": has_external_window,
            "floor_area": floor_area,
        }

    def get_building_envelope(self) -> dict:
        """Retorna resumo da envoltória térmica do edifício.

        Retorna:
            external_walls: list[{guid, area, u_value, material}]
            external_slabs: list[{guid, area, u_value, material}]
            windows: list[{guid, area, u_value, shgc}]
            total_wall_area: float
            total_window_area: float
            wwr: float — window-to-wall ratio
        """
        external_walls = self._collect_external_walls()
        external_slabs = self._collect_external_slabs()
        windows = self._collect_envelope_windows()

        total_wall_area = sum(w["area"] or 0.0 for w in external_walls)
        total_window_area = sum(w["area"] or 0.0 for w in windows)

        if total_wall_area > 0:
            wwr = total_window_area / total_wall_area
        else:
            wwr = 0.0

        return {
            "external_walls": external_walls,
            "external_slabs": external_slabs,
            "windows": windows,
            "total_wall_area": total_wall_area,
            "total_window_area": total_window_area,
            "wwr": wwr,
        }

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _get_space_floor_area(self, space: ifcopenshell.entity_instance) -> float:
        """Retorna área de piso do espaço a partir de Qto_SpaceBaseQuantities."""
        qtos = _get_qtos(space)
        space_qto = qtos.get("Qto_SpaceBaseQuantities", {})
        return space_qto.get("NetFloorArea") or space_qto.get("GrossFloorArea") or 0.0

    def _count_external_boundaries(
        self, space: ifcopenshell.entity_instance
    ) -> tuple[int, set[str]]:
        """Conta paredes externas adjacentes via IfcRelSpaceBoundary.

        Retorna:
            count: número de paredes externas únicas
            guids: conjunto de GlobalIds das paredes externas
        """
        external_wall_guids: set[str] = set()
        try:
            for rel in space.BoundedBy:
                if not rel.is_a("IfcRelSpaceBoundary"):
                    continue
                if rel.InternalOrExternalBoundary != "EXTERNAL":
                    continue
                elem = rel.RelatedBuildingElement
                if elem is None:
                    continue
                if elem.is_a("IfcWall") or elem.is_a("IfcWallStandardCase"):
                    external_wall_guids.add(elem.GlobalId)
        except Exception as exc:
            logger.debug(f"Erro ao contar fronteiras externas de {space.GlobalId[:8]}: {exc}")

        return len(external_wall_guids), external_wall_guids

    def _space_has_external_window(self, external_wall_guids: set[str]) -> bool:
        """Verifica se alguma parede externa contém janela via IfcRelVoidsElement."""
        if not external_wall_guids:
            return False
        try:
            for wall in self.ifc_file.by_type("IfcWall"):
                if wall.GlobalId not in external_wall_guids:
                    continue
                for rel in wall.HasOpenings:
                    opening = rel.RelatedOpeningElement
                    for fill_rel in opening.HasFillings:
                        if fill_rel.RelatedBuildingElement.is_a("IfcWindow"):
                            return True
        except Exception as exc:
            logger.debug(f"Erro ao verificar janelas externas: {exc}")
        return False

    def _infer_conditioning(self, space: ifcopenshell.entity_instance) -> bool | None:
        """Tenta inferir se o espaço é climatizado por nome ou equipamento HVAC.

        Retorna True/False se for possível inferir, None caso contrário.
        """
        name_lower = (space.Name or "").lower()
        # Palavras-chave que sugerem ambiente climatizado
        conditioned_keywords = ("sala", "escritório", "escritorio", "dormitório",
                                "dormitorio", "quarto", "suíte", "suite", "lobby",
                                "hall", "recepção", "recepcao")
        # Palavras-chave que sugerem não climatizado
        unconditioned_keywords = ("garagem", "garage", "escada", "shaft", "depósito",
                                  "deposito", "copa", "lavabo", "wc", "banheiro",
                                  "varanda", "terraço", "terraco")

        for kw in conditioned_keywords:
            if kw in name_lower:
                return True
        for kw in unconditioned_keywords:
            if kw in name_lower:
                return False
        return None

    def _get_element_area(self, element: ifcopenshell.entity_instance) -> float | None:
        """Obtém área de um elemento a partir de BaseQuantities."""
        qtos = _get_qtos(element)
        ifc_class = element.is_a()
        if "Wall" in ifc_class:
            wall_qto = qtos.get("Qto_WallBaseQuantities", {})
            return wall_qto.get("NetSideArea") or wall_qto.get("GrossSideArea")
        if "Slab" in ifc_class:
            slab_qto = qtos.get("Qto_SlabBaseQuantities", {})
            return slab_qto.get("NetArea") or slab_qto.get("GrossArea")
        if "Window" in ifc_class:
            win_qto = qtos.get("Qto_WindowBaseQuantities", {})
            return win_qto.get("Area")
        return None

    def _get_material_name_for_element(self, element: ifcopenshell.entity_instance) -> str | None:
        """Retorna nome do material principal do elemento."""
        material_name, layers, _ = _extract_material_layers(element)
        if material_name:
            return material_name
        if layers:
            return layers[0]["name"]
        return None

    def _collect_external_walls(self) -> list[dict]:
        """Coleta todas as paredes externas (IsExternal=True) do modelo."""
        result: list[dict] = []
        try:
            for wall in self.ifc_file.by_type("IfcWall"):
                psets = _get_psets(wall)
                wall_common = psets.get("Pset_WallCommon", {})
                if not wall_common.get("IsExternal"):
                    continue
                result.append(
                    {
                        "guid": wall.GlobalId,
                        "area": self._get_element_area(wall),
                        "u_value": wall_common.get("ThermalTransmittance"),
                        "material": self._get_material_name_for_element(wall),
                    }
                )
        except Exception as exc:
            logger.warning(f"Erro ao coletar paredes externas: {exc}")
        return result

    def _collect_external_slabs(self) -> list[dict]:
        """Coleta todas as lajes externas (IsExternal=True) do modelo."""
        result: list[dict] = []
        try:
            for slab in self.ifc_file.by_type("IfcSlab"):
                psets = _get_psets(slab)
                slab_common = psets.get("Pset_SlabCommon", {})
                if not slab_common.get("IsExternal"):
                    continue
                result.append(
                    {
                        "guid": slab.GlobalId,
                        "area": self._get_element_area(slab),
                        "u_value": slab_common.get("ThermalTransmittance"),
                        "material": self._get_material_name_for_element(slab),
                    }
                )
        except Exception as exc:
            logger.warning(f"Erro ao coletar lajes externas: {exc}")
        return result

    def _collect_envelope_windows(self) -> list[dict]:
        """Coleta janelas inseridas em paredes externas do modelo."""
        result: list[dict] = []
        collected_guids: set[str] = set()
        try:
            for wall in self.ifc_file.by_type("IfcWall"):
                psets = _get_psets(wall)
                wall_common = psets.get("Pset_WallCommon", {})
                if not wall_common.get("IsExternal"):
                    continue
                for rel in wall.HasOpenings:
                    opening = rel.RelatedOpeningElement
                    for fill_rel in opening.HasFillings:
                        elem = fill_rel.RelatedBuildingElement
                        if not elem.is_a("IfcWindow"):
                            continue
                        if elem.GlobalId in collected_guids:
                            continue
                        collected_guids.add(elem.GlobalId)
                        win_psets = _get_psets(elem)
                        win_common = win_psets.get("Pset_WindowCommon", {})
                        result.append(
                            {
                                "guid": elem.GlobalId,
                                "area": self._get_element_area(elem),
                                "u_value": win_common.get("ThermalTransmittance"),
                                "shgc": win_common.get("SolarHeatGainCoefficient"),
                            }
                        )
        except Exception as exc:
            logger.warning(f"Erro ao coletar janelas da envoltória: {exc}")
        return result
