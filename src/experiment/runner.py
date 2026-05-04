"""Runner para execução das condições experimentais."""

from typing import Any

from src.experiment.metrics import calculate_metrics
from src.pipeline import QualityPipeline


class ExperimentRunner:
    """Executa o pipeline nas diferentes condições de grounding."""

    def run(
        self,
        ifc_path: str,
        building_context: dict[str, Any],
        ids_path: str | None = None,
        modes: list[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Executa as condições e agrega métricas por modo."""
        results: dict[str, dict[str, Any]] = {}
        for mode in modes or ["none", "ids_only", "ids_bsdd"]:
            pipeline = QualityPipeline(
                ifc_path=ifc_path,
                building_context=building_context,
                ids_path=ids_path,
                grounding_mode=mode,  # type: ignore[arg-type]
            )
            try:
                report = pipeline.diagnose()
                results[mode] = calculate_metrics(report.issues)
            finally:
                pipeline.close()
        return results
