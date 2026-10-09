"""Adaptadores finos que ligam módulos existentes aos contratos da fundação."""

from pathlib import Path
from typing import Any

from loguru import logger

from src.experiment.metrics import calculate_metrics
from src.foundation.contracts import LocalLanguageModel
from src.foundation.locality import LocalityPolicy, ensure_local_endpoint
from src.models import IDSSpecification, Issue
from src.translator.ids_parser import parse_ids


class IDSFileRequirementSource:
    """Requisitos lidos de um arquivo IDS local pelo ``parse_ids`` existente."""

    def __init__(self, ids_path: Path) -> None:
        """Guarda o caminho do IDS; falha cedo se o arquivo não existir."""
        if not ids_path.is_file():
            raise FileNotFoundError(f"IDS não encontrado: {ids_path}")
        self._ids_path = ids_path

    def specifications(self) -> list[IDSSpecification]:
        """Lê e devolve as especificações do arquivo IDS."""
        specs = parse_ids(str(self._ids_path))
        logger.debug("IDS {} carregado: {} especificações", self._ids_path.name, len(specs))
        return specs


class IssueMetricsEvaluation:
    """Avaliação científica sobre issues revisadas pelo ``calculate_metrics`` existente."""

    def evaluate(self, issues: list[Issue]) -> dict[str, Any]:
        """Calcula as métricas agregadas das issues."""
        return calculate_metrics(issues)


def require_local_model(
    model: LocalLanguageModel,
    policy: LocalityPolicy | None = None,
) -> LocalLanguageModel:
    """Valida que o LLM aponta para endpoint local ou interno antes de qualquer uso."""
    ensure_local_endpoint(model.base_url, policy)
    return model
