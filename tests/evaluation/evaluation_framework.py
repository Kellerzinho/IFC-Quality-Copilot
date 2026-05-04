"""Framework de avaliação multi-perfil para o IFC Quality Copilot.

Avalia a qualidade das sugestões geradas pelo pipeline contra um conjunto
de referência (ground truth), com suporte a filtragem e comparação por perfil.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pandas as pd
from pydantic import BaseModel, Field

from src.models import (
    Issue,
    ProfileRegistry,
    ReadinessProfile,
    ReadinessScore,
    SuggestionSet,
)

if TYPE_CHECKING:
    from src.pipeline import QualityPipeline


# ---------------------------------------------------------------------------
# Ground truth
# ---------------------------------------------------------------------------


@dataclass
class GroundTruth:
    """Dados de referência para avaliação: mapeamento issue_id → valor esperado.

    Atributos:
        corrections: dicionário {issue_id: valor_correto_esperado}
    """

    corrections: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Métricas de avaliação
# ---------------------------------------------------------------------------


class EvaluationMetrics(BaseModel):
    """Métricas de avaliação de um conjunto de sugestões, com suporte a perfis.

    Campos de acurácia baseados em comparação string com o ground truth.
    Campos de readiness calculados via ReadinessScore quando perfil fornecido.
    """

    accuracy_top1: float = 0.0
    """Proporção de issues em que a sugestão de maior ranking coincide com o ground truth."""

    accuracy_top3: float = 0.0
    """Proporção de issues em que alguma das 3 primeiras sugestões coincide com o ground truth."""

    precision: float = 0.0
    """True positives / total de suggestions geradas."""

    recall: float = 0.0
    """True positives / total de issues no ground truth."""

    f1: float = 0.0
    """Média harmônica entre precision e recall."""

    total_evaluated: int = 0
    """Número de issues avaliadas (presentes no ground truth)."""

    profile_id: str | None = None
    """ID do perfil usado para filtragem, ou None se avaliação global."""

    readiness_before: ReadinessScore | None = None
    """Score de prontidão antes de qualquer correção (todas as issues presentes)."""

    readiness_after: ReadinessScore | None = None
    """Score de prontidão se as correções do ground truth fossem aplicadas."""

    readiness_improvement: float = 0.0
    """Delta percentual: readiness_after.score_percent − readiness_before.score_percent."""

    by_profile: dict[str, dict] = Field(default_factory=dict)
    """Métricas consolidadas por perfil, preenchidas por evaluate_all_profiles()."""


# ---------------------------------------------------------------------------
# Avaliador
# ---------------------------------------------------------------------------


class Evaluator:
    """Avalia sugestões do pipeline contra ground truth, com suporte a múltiplos perfis."""

    # ------------------------------------------------------------------
    # Método principal
    # ------------------------------------------------------------------

    def evaluate(
        self,
        results: list[tuple[Issue, SuggestionSet]],
        ground_truth: GroundTruth,
        profile: ReadinessProfile | None = None,
    ) -> EvaluationMetrics:
        """Avalia resultados contra ground truth, filtrando por perfil se fornecido.

        Args:
            results: pares (Issue, SuggestionSet) gerados pelo pipeline.
            ground_truth: mapeamento issue_id → valor correto esperado.
            profile: perfil de prontidão para filtrar issues e calcular readiness.
                     Se None, avalia todas as issues sem cálculo de readiness.

        Returns:
            EvaluationMetrics com acurácia, precision/recall/f1 e, quando perfil
            fornecido, scores de prontidão antes e depois das correções.
        """
        filtered = self._filter_by_profile(results, profile)

        acc1, acc3, precision, recall, f1, total_evaluated = self._compute_accuracy(
            filtered, ground_truth
        )

        readiness_before, readiness_after, improvement = self._compute_readiness(
            filtered, ground_truth, profile
        )

        return EvaluationMetrics(
            accuracy_top1=round(acc1, 4),
            accuracy_top3=round(acc3, 4),
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1=round(f1, 4),
            total_evaluated=total_evaluated,
            profile_id=profile.id if profile else None,
            readiness_before=readiness_before,
            readiness_after=readiness_after,
            readiness_improvement=round(improvement, 2),
        )

    # ------------------------------------------------------------------
    # Avaliação multi-perfil
    # ------------------------------------------------------------------

    def evaluate_all_profiles(
        self,
        pipeline: "QualityPipeline",
        ground_truth: GroundTruth,
        registry: ProfileRegistry,
    ) -> dict[str, EvaluationMetrics]:
        """Avalia o pipeline para todos os perfis registrados.

        Reutiliza os resultados já gerados pelo pipeline (issues_suggestions)
        sem re-executar diagnóstico ou geração de sugestões.

        Args:
            pipeline: pipeline com diagnóstico e sugestões já executados.
            ground_truth: mapeamento issue_id → valor correto esperado.
            registry: registro com todos os perfis disponíveis.

        Returns:
            Dicionário {profile_id → EvaluationMetrics} para cada perfil.
        """
        results = pipeline.issues_suggestions
        all_metrics: dict[str, EvaluationMetrics] = {}

        for profile in registry.list_profiles():
            metrics = self.evaluate(results, ground_truth, profile=profile)
            all_metrics[profile.id] = metrics

        # Preencher by_profile em cada entrada com snapshot compacto de todas
        summary_per_profile = {
            pid: {
                "accuracy_top1": m.accuracy_top1,
                "accuracy_top3": m.accuracy_top3,
                "precision": m.precision,
                "recall": m.recall,
                "f1": m.f1,
                "readiness_improvement": m.readiness_improvement,
            }
            for pid, m in all_metrics.items()
        }
        for metrics in all_metrics.values():
            metrics.by_profile = summary_per_profile

        return all_metrics

    # ------------------------------------------------------------------
    # Comparação cross-profile
    # ------------------------------------------------------------------

    def compare_profiles(
        self,
        results: dict[str, EvaluationMetrics],
    ) -> pd.DataFrame:
        """Cria DataFrame comparativo das métricas por perfil.

        Args:
            results: dicionário {profile_id → EvaluationMetrics}, tipicamente
                     retornado por evaluate_all_profiles().

        Returns:
            DataFrame com colunas: profile, accuracy_top1, accuracy_top3,
            precision, recall, f1, readiness_before, readiness_after, improvement.
            Retorna DataFrame vazio com as colunas corretas se results for vazio.
        """
        _COLUMNS = [
            "profile",
            "accuracy_top1",
            "accuracy_top3",
            "precision",
            "recall",
            "f1",
            "readiness_before",
            "readiness_after",
            "improvement",
        ]

        if not results:
            return pd.DataFrame(columns=_COLUMNS)

        rows = []
        for profile_id, metrics in results.items():
            rows.append(
                {
                    "profile": profile_id,
                    "accuracy_top1": metrics.accuracy_top1,
                    "accuracy_top3": metrics.accuracy_top3,
                    "precision": metrics.precision,
                    "recall": metrics.recall,
                    "f1": metrics.f1,
                    "readiness_before": (
                        metrics.readiness_before.score_percent
                        if metrics.readiness_before is not None
                        else None
                    ),
                    "readiness_after": (
                        metrics.readiness_after.score_percent
                        if metrics.readiness_after is not None
                        else None
                    ),
                    "improvement": metrics.readiness_improvement,
                }
            )

        return pd.DataFrame(rows, columns=_COLUMNS)

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_by_profile(
        results: list[tuple[Issue, SuggestionSet]],
        profile: ReadinessProfile | None,
    ) -> list[tuple[Issue, SuggestionSet]]:
        """Filtra pares (Issue, SuggestionSet) pelos issue_types do perfil."""
        if profile is None:
            return list(results)
        allowed = set(profile.issue_types)
        return [(issue, ss) for issue, ss in results if issue.issue_type in allowed]

    @staticmethod
    def _compute_accuracy(
        filtered: list[tuple[Issue, SuggestionSet]],
        ground_truth: GroundTruth,
    ) -> tuple[float, float, float, float, float, int]:
        """Calcula acurácia top-1, top-3, precision, recall e f1.

        Compara string(suggestion.value) com string(ground_truth.corrections[issue.id]).

        Returns:
            (accuracy_top1, accuracy_top3, precision, recall, f1, total_evaluated)
        """
        top1_hits = 0
        top3_hits = 0
        true_positives = 0
        total_with_gt = 0
        total_suggestions_generated = 0

        for issue, suggestion_set in filtered:
            if issue.id not in ground_truth.corrections:
                continue

            total_with_gt += 1
            expected = str(ground_truth.corrections[issue.id])
            suggestions = suggestion_set.suggestions

            if suggestions:
                total_suggestions_generated += 1
                if str(suggestions[0].value) == expected:
                    top1_hits += 1
                    true_positives += 1

            top3 = suggestions[:3]
            if any(str(s.value) == expected for s in top3):
                top3_hits += 1

        acc1 = top1_hits / total_with_gt if total_with_gt > 0 else 0.0
        acc3 = top3_hits / total_with_gt if total_with_gt > 0 else 0.0
        precision = (
            true_positives / total_suggestions_generated
            if total_suggestions_generated > 0
            else 0.0
        )
        recall = (
            true_positives / len(ground_truth.corrections)
            if ground_truth.corrections
            else 0.0
        )
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        return acc1, acc3, precision, recall, f1, total_with_gt

    @staticmethod
    def _compute_readiness(
        filtered: list[tuple[Issue, SuggestionSet]],
        ground_truth: GroundTruth,
        profile: ReadinessProfile | None,
    ) -> tuple[ReadinessScore | None, ReadinessScore | None, float]:
        """Calcula scores de prontidão antes e depois das correções do ground truth.

        - before: todas as issues do perfil estão presentes (nenhuma corrigida).
        - after: issues presentes no ground_truth.corrections são removidas
                 (simulando que todas as correções esperadas foram aplicadas).

        Returns:
            (readiness_before, readiness_after, improvement_pct)
        """
        if profile is None:
            return None, None, 0.0

        all_issues = [issue for issue, _ in filtered]
        total_checks = max(len(all_issues), 1)

        readiness_before = ReadinessScore.compute(
            profile=profile,
            issues=all_issues,
            total_checks=total_checks,
        )

        gt_ids = set(ground_truth.corrections.keys())
        remaining_issues = [i for i in all_issues if i.id not in gt_ids]
        readiness_after = ReadinessScore.compute(
            profile=profile,
            issues=remaining_issues,
            total_checks=total_checks,
        )

        improvement = readiness_after.score_percent - readiness_before.score_percent
        return readiness_before, readiness_after, improvement
