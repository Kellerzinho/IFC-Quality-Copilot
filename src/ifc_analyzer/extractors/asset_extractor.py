"""Extrator de dados de ativos/equipamentos de elementos IFC para contexto de FM."""

import ifcopenshell
import ifcopenshell.util.element
from loguru import logger


# Classes IFC que representam ativos de FM rastreáveis
_ASSET_CLASSES: list[str] = [
    "IfcFurnishingElement",
    "IfcFlowTerminal",
    "IfcEnergyConversionDevice",
    "IfcFlowMovingDevice",
    "IfcFlowStorageDevice",
    "IfcDistributionControlElement",
]

# Mapeamento de classe IFC → tipo simplificado para relatórios FM
_ASSET_TYPE_MAP: dict[str, str] = {
    "IfcFurnishingElement": "furnishing",
    "IfcFlowTerminal": "flow_terminal",
    "IfcEnergyConversionDevice": "energy_conversion",
    "IfcFlowMovingDevice": "flow_moving",
    "IfcFlowStorageDevice": "flow_storage",
    "IfcDistributionControlElement": "distribution_control",
}


def _get_psets(element: ifcopenshell.entity_instance) -> dict:
    """Wrapper para get_psets que retorna dict vazio em caso de erro."""
    try:
        return ifcopenshell.util.element.get_psets(element)
    except Exception as exc:
        logger.debug(f"Não foi possível obter Psets de {element.is_a()}: {exc}")
        return {}


def _get_containing_space_name(element: ifcopenshell.entity_instance) -> str | None:
    """Retorna o nome do IfcSpace que contém diretamente o ativo, ou None."""
    try:
        for rel in element.ContainedInStructure:
            container = rel.RelatingStructure
            if container.is_a("IfcSpace"):
                return container.LongName or container.Name or None
    except Exception as exc:
        logger.debug(
            f"Erro ao buscar espaço contentor de {element.is_a()} "
            f"#{element.GlobalId[:8]}: {exc}"
        )
    return None


def _get_floor_name(element: ifcopenshell.entity_instance) -> str | None:
    """Retorna o nome do IfcBuildingStorey que contém o ativo.

    Percorre a hierarquia: elemento → container direto (espaço ou pavimento).
    Se o container direto for um espaço, sobe para encontrar o pavimento via Decomposes.
    """
    try:
        for rel in element.ContainedInStructure:
            container = rel.RelatingStructure
            if container.is_a("IfcBuildingStorey"):
                return container.Name
            if container.is_a("IfcSpace"):
                # Sobe um nível: espaço → pavimento via Decomposes
                for decomp_rel in container.Decomposes:
                    relating = decomp_rel.RelatingObject
                    if relating.is_a("IfcBuildingStorey"):
                        return relating.Name
    except Exception as exc:
        logger.debug(
            f"Erro ao buscar pavimento de {element.is_a()} "
            f"#{element.GlobalId[:8]}: {exc}"
        )
    return None


class AssetExtractor:
    """Extrai dados de ativos/equipamentos para contexto de FM."""

    def __init__(self, ifc_file: ifcopenshell.file) -> None:
        """Inicializa o extrator com o arquivo IFC aberto."""
        self.ifc_file = ifc_file

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def extract_asset_info(self, element: ifcopenshell.entity_instance) -> dict:
        """Extrai dados de FM de um elemento de ativo IFC.

        Lê os Psets padrão de manufatura, garantia e localização espacial.

        Args:
            element: instância IFC do tipo IfcFurnishingElement, IfcFlowTerminal,
                     IfcEnergyConversionDevice ou assemelhados.

        Returns:
            Dict com as chaves:
                - asset_type: str — classe IFC simplificada (ex: "flow_terminal")
                - name: str | None — Name do elemento IFC
                - manufacturer: str | None — Pset_ManufacturerTypeInformation.Manufacturer
                - model_reference: str | None — ModelReference ou ModelLabel
                - serial_number: str | None — SerialNumber
                - installation_date: str | None — Pset_Asset.InstallationDate
                - warranty_duration: str | None — Pset_Warranty.WarrantyDuration
                - containing_space: str | None — nome do IfcSpace contentor
                - floor: str | None — nome do IfcBuildingStorey
        """
        psets = _get_psets(element)
        mfr_pset = psets.get("Pset_ManufacturerTypeInformation", {})
        warranty_pset = psets.get("Pset_Warranty", {})
        asset_pset = psets.get("Pset_Asset", {})

        ifc_class = element.is_a()
        asset_type = _ASSET_TYPE_MAP.get(ifc_class, ifc_class.replace("Ifc", "").lower())

        return {
            "asset_type": asset_type,
            "name": getattr(element, "Name", None),
            "manufacturer": mfr_pset.get("Manufacturer"),
            "model_reference": mfr_pset.get("ModelReference") or mfr_pset.get("ModelLabel"),
            "serial_number": mfr_pset.get("SerialNumber"),
            "installation_date": asset_pset.get("InstallationDate"),
            "warranty_duration": warranty_pset.get("WarrantyDuration"),
            "containing_space": _get_containing_space_name(element),
            "floor": _get_floor_name(element),
        }

    def get_unidentified_assets(self) -> list[dict]:
        """Lista equipamentos sem nome, fabricante E localização simultaneamente.

        Um ativo é considerado não identificado quando os três campos principais
        de rastreabilidade FM estão ausentes: name, manufacturer e containing_space.

        Returns:
            Lista de dicts com chave extra 'guid' além dos campos de extract_asset_info.
        """
        result: list[dict] = []
        seen_guids: set[str] = set()

        for asset_class in _ASSET_CLASSES:
            try:
                elements = self.ifc_file.by_type(asset_class)
            except Exception as exc:
                logger.debug(f"Classe {asset_class} não disponível no schema: {exc}")
                continue

            for element in elements:
                guid = element.GlobalId
                if guid in seen_guids:
                    continue
                seen_guids.add(guid)

                info = self.extract_asset_info(element)
                if not info["name"] and not info["manufacturer"] and not info["containing_space"]:
                    result.append({"guid": guid, **info})

        return result

    def get_asset_inventory(self) -> list[dict]:
        """Inventário completo de ativos com todos os dados disponíveis.

        Itera sobre todas as classes de ativo FM e consolida os resultados,
        garantindo que cada elemento apareça apenas uma vez no inventário.

        Returns:
            Lista de dicts com chave extra 'guid' além dos campos de extract_asset_info.
        """
        result: list[dict] = []
        seen_guids: set[str] = set()

        for asset_class in _ASSET_CLASSES:
            try:
                elements = self.ifc_file.by_type(asset_class)
            except Exception as exc:
                logger.debug(f"Classe {asset_class} não disponível no schema: {exc}")
                continue

            for element in elements:
                guid = element.GlobalId
                if guid in seen_guids:
                    continue
                seen_guids.add(guid)

                info = self.extract_asset_info(element)
                result.append({"guid": guid, **info})

        return result
