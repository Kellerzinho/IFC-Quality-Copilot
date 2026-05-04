"""Orquestrador principal dos módulos de diagnóstico IFC."""

from pathlib import Path
from typing import Any

import ifcopenshell
import ifcopenshell.util.element
from loguru import logger

from src.models import DiagnosticReport, IFCElement, Issue, ReadinessProfile
from src.ifc_analyzer.space_diagnostics import diagnose_spaces
from src.ifc_analyzer.pset_diagnostics import diagnose_psets
from src.ifc_analyzer.relation_diagnostics import diagnose_relations
from src.ifc_analyzer.system_diagnostics import diagnose_systems


# ---------------------------------------------------------------------------
# Mapeamento: nome do campo de contexto → (extrator, chave no resultado)
# ---------------------------------------------------------------------------

_CONTEXT_FIELD_MAP: dict[str, tuple[str, str]] = {
    # thermal
    "is_external": ("thermal", "is_external"),
    "thermal_transmittance": ("thermal", "thermal_transmittance"),
    "material": ("thermal", "material_name"),
    "material_name": ("thermal", "material_name"),
    "layers": ("thermal", "layers"),
    "thickness": ("thermal", "total_thickness_m"),
    "total_thickness_m": ("thermal", "total_thickness_m"),
    "has_insulation": ("thermal", "has_insulation"),
    "estimated_u_range": ("thermal", "estimated_u_range"),
    "absorptance": ("thermal", "absorptance"),
    # quantities
    "width": ("quantities", "width"),
    "height": ("quantities", "height"),
    "length": ("quantities", "length"),
    "volume": ("quantities", "volume"),
    "net_side_area": ("quantities", "net_side_area"),
    "gross_side_area": ("quantities", "gross_side_area"),
    "net_area": ("quantities", "net_area"),
    "gross_area": ("quantities", "gross_area"),
    "net_floor_area": ("quantities", "net_floor_area"),
    "gross_floor_area": ("quantities", "gross_floor_area"),
    # classifications
    "has_classification": ("classifications", "has_classification"),
    "classification_system": ("classifications", "classification_system"),
    "classification_code": ("classifications", "classification_code"),
    "classification_name": ("classifications", "classification_name"),
    # assets
    "manufacturer": ("assets", "manufacturer"),
    "asset_type": ("assets", "asset_type"),
    "model_reference": ("assets", "model_reference"),
    "containing_space": ("assets", "containing_space"),
}

# Campos padrão a enriquecer por extrator (usados quando profile.required_extractors é informado)
_EXTRACTOR_DEFAULT_FIELDS: dict[str, list[str]] = {
    "thermal": [
        "is_external",
        "thermal_transmittance",
        "material",
        "total_thickness_m",
        "has_insulation",
        "estimated_u_range",
    ],
    "quantities": ["width", "height", "length", "volume", "net_side_area", "net_floor_area"],
    "classifications": ["has_classification", "classification_code", "classification_name"],
    "assets": ["manufacturer", "asset_type", "model_reference"],
}


class IFCAnalyzer:
    """Orquestra todos os módulos de diagnóstico sobre um modelo IFC."""

    def __init__(self, ifc_path: str) -> None:
        """Abre o arquivo IFC e inicializa o analisador."""
        self.ifc_path = ifc_path
        self.ifc_file = ifcopenshell.open(ifc_path)
        self.model_name = Path(ifc_path).stem
        self.extractors: dict[str, Any] = {}
        logger.info(f"Modelo '{self.model_name}' carregado: {self._count_elements()} elementos")

    def get_extractor(self, name: str) -> Any:
        """Retorna extrator por nome, criando-o se necessário (lazy init).

        Args:
            name: identificador do extrator — "quantities", "thermal", "assets"
                  ou "classifications".

        Returns:
            Instância do extrator correspondente ao nome informado.

        Raises:
            ValueError: se o nome não corresponde a nenhum extrator conhecido.
        """
        if name in self.extractors:
            return self.extractors[name]

        if name == "quantities":
            from src.ifc_analyzer.extractors import QuantityExtractor
            self.extractors[name] = QuantityExtractor(self.ifc_file)
        elif name == "thermal":
            from src.ifc_analyzer.extractors import ThermalExtractor
            self.extractors[name] = ThermalExtractor(self.ifc_file)
        elif name == "assets":
            from src.ifc_analyzer.extractors import AssetExtractor
            self.extractors[name] = AssetExtractor(self.ifc_file)
        elif name == "classifications":
            from src.ifc_analyzer.extractors import ClassificationExtractor
            self.extractors[name] = ClassificationExtractor(self.ifc_file)
        else:
            raise ValueError(f"Extrator desconhecido: '{name}'")

        return self.extractors[name]

    def enrich_issue_context(self, issue: Issue, required_context: list[str]) -> Issue:
        """Enriquece o contexto de um Issue com dados extraídos dos extratores.

        Para cada campo em required_context, localiza o extrator responsável,
        chama-o uma única vez por extrator (cache interno) e adiciona o valor
        resultante em issue.context.

        Args:
            issue: Issue a ser enriquecido (modificado in-place).
            required_context: lista de nomes de campos desejados,
                ex.: ["is_external", "thermal_transmittance", "width"].

        Returns:
            O mesmo Issue com issue.context atualizado.
        """
        try:
            element = self.ifc_file.by_guid(issue.element_guid)
        except Exception:
            logger.warning(f"Elemento {issue.element_guid[:8]} não encontrado para enriquecimento")
            return issue

        if element is None:
            return issue

        # Cache por extrator para evitar chamadas duplicadas ao mesmo elemento
        extractor_cache: dict[str, dict] = {}

        for field in required_context:
            if field not in _CONTEXT_FIELD_MAP:
                logger.debug(f"Campo '{field}' não mapeado para nenhum extrator")
                continue

            extractor_name, result_key = _CONTEXT_FIELD_MAP[field]

            if extractor_name not in extractor_cache:
                try:
                    extractor_cache[extractor_name] = self._extract_context_from_extractor(
                        extractor_name, element
                    )
                except Exception as exc:
                    logger.warning(f"Erro ao extrair contexto '{extractor_name}': {exc}")
                    extractor_cache[extractor_name] = {}

            data = extractor_cache[extractor_name]
            if result_key in data:
                issue.context[field] = data[result_key]

        return issue

    def analyze(
        self,
        required_psets: dict | None = None,
        profile: ReadinessProfile | None = None,
    ) -> DiagnosticReport:
        """Executa todos os diagnósticos e retorna relatório consolidado.

        Args:
            required_psets: Psets obrigatórios customizados para o diagnóstico de Psets.
            profile: perfil de prontidão para enriquecimento de contexto das issues.
                     Se fornecido, cada issue gerada é enriquecida com os campos
                     padrão dos extratores listados em profile.required_extractors.
        """
        all_issues: list[Issue] = []
        all_issues.extend(diagnose_spaces(self.ifc_file))
        all_issues.extend(diagnose_psets(self.ifc_file, required_psets))
        all_issues.extend(diagnose_relations(self.ifc_file))
        all_issues.extend(diagnose_systems(self.ifc_file))

        deduped = self._deduplicate_issues(all_issues)
        sorted_issues = sorted(deduped, key=lambda i: i.severity_order)

        if profile is not None:
            required_context: list[str] = []
            for extractor_name in profile.required_extractors:
                required_context.extend(_EXTRACTOR_DEFAULT_FIELDS.get(extractor_name, []))
            for issue in sorted_issues:
                self.enrich_issue_context(issue, required_context)

        return DiagnosticReport(
            model_name=self.model_name,
            model_path=self.ifc_path,
            total_elements=len(self.ifc_file.by_type("IfcProduct")),
            total_spaces=len(self.ifc_file.by_type("IfcSpace")),
            total_walls=len(self.ifc_file.by_type("IfcWall")),
            total_doors=len(self.ifc_file.by_type("IfcDoor")),
            total_windows=len(self.ifc_file.by_type("IfcWindow")),
            total_slabs=len(self.ifc_file.by_type("IfcSlab")),
            issues=sorted_issues,
        )

    def analyze_for_profile(self, profile: ReadinessProfile) -> DiagnosticReport:
        """Executa diagnósticos relevantes ao perfil e enriquece contexto de cada issue.

        Roda todos os diagnósticos, filtra os issues pelos tipos definidos no perfil
        (se issue_types estiver preenchido) e enriquece o contexto de cada issue
        usando os extratores listados em profile.required_extractors.

        Args:
            profile: perfil de prontidão que define extratores e tipos de issue relevantes.

        Returns:
            DiagnosticReport com issues filtradas e contexto enriquecido.
        """
        report = self.analyze(profile=profile)

        if profile.issue_types:
            filtered = [i for i in report.issues if i.issue_type in profile.issue_types]
            report = DiagnosticReport(
                model_name=report.model_name,
                model_path=report.model_path,
                total_elements=report.total_elements,
                total_spaces=report.total_spaces,
                total_walls=report.total_walls,
                total_doors=report.total_doors,
                total_windows=report.total_windows,
                total_slabs=report.total_slabs,
                issues=filtered,
            )

        return report

    def analyze_spaces_only(self) -> list[Issue]:
        """Diagnóstico apenas de espaços."""
        return diagnose_spaces(self.ifc_file)

    def analyze_psets_only(self, required_psets: dict | None = None) -> list[Issue]:
        """Diagnóstico apenas de Psets."""
        return diagnose_psets(self.ifc_file, required_psets)

    def analyze_relations_only(self) -> list[Issue]:
        """Diagnóstico apenas de relações."""
        return diagnose_relations(self.ifc_file)

    def analyze_systems_only(self) -> list[Issue]:
        """Diagnóstico apenas de sistemas construtivos."""
        return diagnose_systems(self.ifc_file)

    def get_element(self, guid: str) -> IFCElement | None:
        """Retorna IFCElement completo a partir do GUID."""
        try:
            element = self.ifc_file.by_guid(guid)
        except Exception:
            return None

        if element is None:
            return None

        psets: dict[str, dict[str, Any]] = ifcopenshell.util.element.get_psets(element)

        floor: str | None = None
        for rel in self.ifc_file.by_type("IfcRelContainedInSpatialStructure"):
            if element in rel.RelatedElements:
                storey = rel.RelatingStructure
                floor = getattr(storey, "Name", None)
                break

        return IFCElement(
            guid=element.GlobalId,
            ifc_class=element.is_a(),
            name=getattr(element, "Name", None),
            long_name=getattr(element, "LongName", None),
            description=getattr(element, "Description", None),
            properties=psets,
            floor=floor,
        )

    def get_model_summary(self) -> dict:
        """Retorna resumo: total por classe, schema, nome."""
        return {
            "model_name": self.model_name,
            "model_path": self.ifc_path,
            "schema": self.ifc_file.schema,
            "total_elements": len(self.ifc_file.by_type("IfcProduct")),
            "total_spaces": len(self.ifc_file.by_type("IfcSpace")),
            "total_walls": len(self.ifc_file.by_type("IfcWall")),
            "total_doors": len(self.ifc_file.by_type("IfcDoor")),
            "total_windows": len(self.ifc_file.by_type("IfcWindow")),
            "total_slabs": len(self.ifc_file.by_type("IfcSlab")),
        }

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _extract_context_from_extractor(
        self, extractor_name: str, element: Any
    ) -> dict[str, Any]:
        """Chama o método correto do extrator para o tipo de elemento IFC.

        Args:
            extractor_name: nome do extrator ("thermal", "quantities", etc.).
            element: instância de elemento IFC.

        Returns:
            Dict com os dados extraídos pelo extrator para o elemento.
        """
        extractor = self.get_extractor(extractor_name)
        ifc_class = element.is_a()

        if extractor_name == "thermal":
            if "Wall" in ifc_class:
                return extractor.extract_wall_thermal(element)
            elif "Window" in ifc_class:
                return extractor.extract_window_thermal(element)
            elif "Slab" in ifc_class:
                return extractor.extract_slab_thermal(element)
            elif "Space" in ifc_class:
                return extractor.extract_space_thermal_zone(element)
            return {}
        elif extractor_name == "quantities":
            return extractor.extract_all(element)
        elif extractor_name == "classifications":
            return extractor.extract_classification(element)
        elif extractor_name == "assets":
            return extractor.extract_asset_info(element)
        return {}

    def _count_elements(self) -> int:
        """Conta total de elementos no modelo."""
        return len(self.ifc_file.by_type("IfcProduct"))

    def _deduplicate_issues(self, issues: list[Issue]) -> list[Issue]:
        """Remove duplicatas (mesmo guid + mesmo issue_type)."""
        seen: set[tuple[str, str]] = set()
        result: list[Issue] = []
        for issue in issues:
            key = (issue.element_guid, issue.issue_type)
            if key not in seen:
                seen.add(key)
                result.append(issue)
        return result
