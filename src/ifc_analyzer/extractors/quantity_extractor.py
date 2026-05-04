"""Extrator de BaseQuantities de elementos IFC para contexto de orçamento."""

from typing import Any

import ifcopenshell
import ifcopenshell.util.element
from loguru import logger


# Campos esperados por classe IFC — usados em get_missing_quantities
_EXPECTED_QUANTITIES: dict[str, list[str]] = {
    "IfcWall": ["net_side_area", "gross_side_area", "width", "height", "length", "volume"],
    "IfcWallStandardCase": ["net_side_area", "gross_side_area", "width", "height", "length", "volume"],
    "IfcSlab": ["net_area", "gross_area", "width", "perimeter", "volume"],
    "IfcDoor": ["area", "height", "width"],
    "IfcWindow": ["area", "height", "width"],
    "IfcSpace": ["net_floor_area", "gross_floor_area", "height", "volume"],
    "IfcBeam": ["length", "cross_section_area", "volume"],
    "IfcColumn": ["length", "cross_section_area", "volume"],
}


class QuantityExtractor:
    """Extrai BaseQuantities de elementos IFC para contexto de orçamento."""

    def __init__(self, ifc_file: ifcopenshell.file) -> None:
        """Inicializa o extrator com o arquivo IFC aberto."""
        self.ifc_file = ifc_file

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _get_qto(
        self, element: ifcopenshell.entity_instance, qto_name: str
    ) -> dict[str, Any]:
        """Retorna o dict de quantidades de um Qto específico, ou vazio se ausente."""
        qtos = ifcopenshell.util.element.get_psets(element, qtos_only=True)
        return qtos.get(qto_name, {})

    def _try_geometry_fallback(
        self, element: ifcopenshell.entity_instance
    ) -> dict[str, float]:
        """Tenta extrair dimensões via bounding-box geométrico (requer OCC).

        Retorna dict com chaves dx, dy, dz se bem-sucedido, ou vazio caso contrário.
        """
        try:
            import ifcopenshell.geom
            import ifcopenshell.util.shape as shape_util

            settings = ifcopenshell.geom.settings()
            shape = ifcopenshell.geom.create_shape(settings, element)
            verts = shape_util.get_vertices(shape.geometry)
            if verts is None or len(verts) == 0:
                return {}

            xs = [v[0] for v in verts]
            ys = [v[1] for v in verts]
            zs = [v[2] for v in verts]
            return {
                "dx": max(xs) - min(xs),
                "dy": max(ys) - min(ys),
                "dz": max(zs) - min(zs),
            }
        except Exception as exc:
            logger.debug(
                f"Geometria indisponível para {element.is_a()} "
                f"#{element.GlobalId[:8]}: {exc}"
            )
            return {}

    # ------------------------------------------------------------------
    # Extratores por classe
    # ------------------------------------------------------------------

    def extract_wall_quantities(
        self, wall: ifcopenshell.entity_instance
    ) -> dict[str, float | None]:
        """Extrai quantidades de IfcWall a partir de Qto_WallBaseQuantities.

        Campos: net_side_area, gross_side_area, width (espessura), height, length, volume.
        Se Qto_WallBaseQuantities estiver ausente, tenta calcular via bounding-box geométrico.
        """
        qto = self._get_qto(wall, "Qto_WallBaseQuantities")
        result: dict[str, float | None] = {
            "net_side_area": qto.get("NetSideArea"),
            "gross_side_area": qto.get("GrossSideArea"),
            "width": qto.get("Width"),
            "height": qto.get("Height"),
            "length": qto.get("Length"),
            "volume": qto.get("NetVolume"),
        }

        if all(v is None for v in result.values()):
            geo = self._try_geometry_fallback(wall)
            if geo:
                dx, dy, dz = geo["dx"], geo["dy"], geo["dz"]
                width = min(dx, dy)
                length = max(dx, dy)
                height = dz
                result.update(
                    {
                        "width": width,
                        "height": height,
                        "length": length,
                        "volume": width * length * height,
                        "net_side_area": length * height,
                        "gross_side_area": length * height,
                    }
                )
                logger.debug(
                    f"Quantidades de IfcWall #{wall.GlobalId[:8]} extraídas via geometria."
                )

        return result

    def extract_slab_quantities(
        self, slab: ifcopenshell.entity_instance
    ) -> dict[str, float | None]:
        """Extrai quantidades de IfcSlab a partir de Qto_SlabBaseQuantities.

        Campos: net_area, gross_area, width (espessura), perimeter, volume.
        """
        qto = self._get_qto(slab, "Qto_SlabBaseQuantities")
        result: dict[str, float | None] = {
            "net_area": qto.get("NetArea"),
            "gross_area": qto.get("GrossArea"),
            "width": qto.get("Width"),
            "perimeter": qto.get("Perimeter"),
            "volume": qto.get("NetVolume"),
        }

        if all(v is None for v in result.values()):
            geo = self._try_geometry_fallback(slab)
            if geo:
                dx, dy, dz = geo["dx"], geo["dy"], geo["dz"]
                width = min(dx, dy, dz)
                # espessura é a menor dimensão; área = produto das duas maiores
                dims = sorted([dx, dy, dz])
                area = dims[1] * dims[2]
                result.update(
                    {
                        "width": width,
                        "net_area": area,
                        "gross_area": area,
                        "volume": dx * dy * dz,
                    }
                )
                logger.debug(
                    f"Quantidades de IfcSlab #{slab.GlobalId[:8]} extraídas via geometria."
                )

        return result

    def extract_door_quantities(
        self, door: ifcopenshell.entity_instance
    ) -> dict[str, float | None]:
        """Extrai quantidades de IfcDoor a partir de Qto_DoorBaseQuantities.

        Campos: area, height, width.
        """
        qto = self._get_qto(door, "Qto_DoorBaseQuantities")
        return {
            "area": qto.get("Area"),
            "height": qto.get("Height"),
            "width": qto.get("Width"),
        }

    def extract_window_quantities(
        self, window: ifcopenshell.entity_instance
    ) -> dict[str, float | None]:
        """Extrai quantidades de IfcWindow a partir de Qto_WindowBaseQuantities.

        Campos: area, height, width.
        """
        qto = self._get_qto(window, "Qto_WindowBaseQuantities")
        return {
            "area": qto.get("Area"),
            "height": qto.get("Height"),
            "width": qto.get("Width"),
        }

    def extract_space_quantities(
        self, space: ifcopenshell.entity_instance
    ) -> dict[str, float | None]:
        """Extrai quantidades de IfcSpace a partir de Qto_SpaceBaseQuantities.

        Campos: net_floor_area, gross_floor_area, height, volume.
        """
        qto = self._get_qto(space, "Qto_SpaceBaseQuantities")
        return {
            "net_floor_area": qto.get("NetFloorArea"),
            "gross_floor_area": qto.get("GrossFloorArea"),
            "height": qto.get("Height"),
            "volume": qto.get("NetVolume"),
        }

    def extract_beam_quantities(
        self, beam: ifcopenshell.entity_instance
    ) -> dict[str, float | None]:
        """Extrai quantidades de IfcBeam a partir de Qto_BeamBaseQuantities.

        Campos: length, cross_section_area, volume.
        """
        qto = self._get_qto(beam, "Qto_BeamBaseQuantities")
        return {
            "length": qto.get("Length"),
            "cross_section_area": qto.get("CrossSectionArea"),
            "volume": qto.get("NetVolume"),
        }

    def extract_column_quantities(
        self, column: ifcopenshell.entity_instance
    ) -> dict[str, float | None]:
        """Extrai quantidades de IfcColumn a partir de Qto_ColumnBaseQuantities.

        Campos: length, cross_section_area, volume.
        """
        qto = self._get_qto(column, "Qto_ColumnBaseQuantities")
        return {
            "length": qto.get("Length"),
            "cross_section_area": qto.get("CrossSectionArea"),
            "volume": qto.get("NetVolume"),
        }

    # ------------------------------------------------------------------
    # Roteador genérico
    # ------------------------------------------------------------------

    def extract_all(
        self, element: ifcopenshell.entity_instance
    ) -> dict[str, float | None]:
        """Roteia para o extrator correto baseado na classe IFC do elemento.

        Retorna dict vazio para classes sem extrator definido.
        """
        ifc_class = element.is_a()
        extractors: dict[str, Any] = {
            "IfcWall": self.extract_wall_quantities,
            "IfcWallStandardCase": self.extract_wall_quantities,
            "IfcSlab": self.extract_slab_quantities,
            "IfcDoor": self.extract_door_quantities,
            "IfcWindow": self.extract_window_quantities,
            "IfcSpace": self.extract_space_quantities,
            "IfcBeam": self.extract_beam_quantities,
            "IfcColumn": self.extract_column_quantities,
        }
        extractor = extractors.get(ifc_class)
        if extractor is None:
            logger.warning(f"Sem extrator de quantities para classe {ifc_class}")
            return {}
        return extractor(element)

    def get_missing_quantities(
        self, element: ifcopenshell.entity_instance
    ) -> list[str]:
        """Retorna lista de nomes de quantities ausentes (valor None) para o elemento.

        Compara o resultado de extract_all com os campos esperados para a classe IFC.
        Retorna lista vazia para classes sem expectativas definidas.
        """
        ifc_class = element.is_a()
        expected = _EXPECTED_QUANTITIES.get(ifc_class)
        if expected is None:
            logger.debug(f"Classe {ifc_class} não possui quantities esperadas definidas.")
            return []

        quantities = self.extract_all(element)
        return [field for field in expected if quantities.get(field) is None]
