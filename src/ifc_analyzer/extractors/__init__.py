"""Extratores de dados especializados para elementos IFC."""

from src.ifc_analyzer.extractors.asset_extractor import AssetExtractor
from src.ifc_analyzer.extractors.classification_extractor import ClassificationExtractor
from src.ifc_analyzer.extractors.quantity_extractor import QuantityExtractor
from src.ifc_analyzer.extractors.thermal_extractor import ThermalExtractor

__all__ = ["AssetExtractor", "ClassificationExtractor", "QuantityExtractor", "ThermalExtractor"]
