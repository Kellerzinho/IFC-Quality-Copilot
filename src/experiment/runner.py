"""Runner para execução experimental do pipeline."""

from typing import Any

from src.experiment.metrics import calculate_metrics
from src.pipeline import QualityPipeline


class ExperimentRunner:
    """Executa o pipeline (grounding IDS+bSDD) e agrega as métricas."""

    def run(
        self,
        ifc_path: str,
        building_context: dict[str, Any],
        ids_path: str | None = None,
    ) -> dict[str, Any]:
        """Executa o pipeline e retorna as métricas do diagnóstico."""
        pipeline = QualityPipeline(
            ifc_path=ifc_path,
            building_context=building_context,
            ids_path=ids_path,
        )
        try:
            report = pipeline.diagnose()
            return calculate_metrics(report.issues)
        finally:
            pipeline.close()
