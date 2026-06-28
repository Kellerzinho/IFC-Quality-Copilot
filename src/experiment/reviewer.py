"""Revisor simulado (Fase 0.5 / F6) — proxy de decisão humana sobre cópia descartável.

Mapeia, para cada issue com ground truth, a decisão que um revisor humano tomaria,
usando a comparação **normalizada** da Fase 0.3:

- top-1 casa o GT → ``accepted`` (aplica o valor top-1);
- algo do top-3 casa → ``edited`` (aplica o valor que casou);
- nada casa, mas há abstenção/review_required → ``review`` (não aplica);
- nada casa e não há abstenção → ``rejected`` (não aplica).

As correções aceitas/editadas são aplicadas a uma **cópia descartável** do IFC (o
``QualityPipeline`` recebido já é construído sobre a cópia) e a conformidade IDS é
medida via ``PostValidator``. O IFC original **nunca** é alterado.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from loguru import logger
from pydantic import BaseModel

from src.experiment.evaluator import Evaluator, GroundTruth, GroundTruthItem
from src.experiment.metrics import ReviewProxyMetrics
from src.models import Issue, SuggestionSet

if TYPE_CHECKING:
    from src.pipeline import QualityPipeline


class ReviewDecision(BaseModel):
    """Decisão do revisor simulado para uma issue (rotulada como simulação)."""

    issue_id: str
    element_guid: str
    issue_type: str
    decision: Literal["accepted", "edited", "rejected", "review"]
    applied_value: Any = None
    post_validation: Literal["pass", "fail", "skip"] | None = None


def _decide(
    issue: Issue,
    suggestion_set: SuggestionSet,
    item: GroundTruthItem,
    evaluator: Evaluator,
) -> tuple[Literal["accepted", "edited", "rejected", "review"], Any]:
    """Decide a ação do revisor simulado e o valor a aplicar (None se não aplica)."""
    suggestions = suggestion_set.suggestions
    top3 = suggestions[:3]

    if suggestions and evaluator._suggestion_matches(issue, suggestions[0].value, item):
        return "accepted", suggestions[0].value

    for suggestion in top3:
        if evaluator._suggestion_matches(issue, suggestion.value, item):
            return "edited", suggestion.value

    # Nada casou: abstenção/review vs rejeição
    abstained = (not suggestions) or any(s.review_required for s in top3)
    if abstained:
        return "review", None
    return "rejected", None


def simulate_review(
    pipeline: "QualityPipeline",
    ground_truth: GroundTruth,
    evaluator: Evaluator | None = None,
    user: str = "revisor_simulado",
) -> tuple[ReviewProxyMetrics, list[ReviewDecision]]:
    """Aplica o revisor simulado sobre o pipeline (cópia descartável) + ground truth.

    Itera as issues com entrada no ground truth, decide a ação e aplica as
    correções aceitas/editadas na cópia em memória, medindo a conformidade IDS
    pós-correção. Retorna as métricas agregadas e as decisões por issue.
    """
    evaluator = evaluator or Evaluator()
    decisions: list[ReviewDecision] = []

    for issue, suggestion_set in pipeline.issues_suggestions:
        item = ground_truth.get_for_issue(issue)
        if item is None:
            continue

        decision, value = _decide(issue, suggestion_set, item, evaluator)
        post_status: Literal["pass", "fail", "skip"] | None = None

        if decision in ("accepted", "edited"):
            try:
                pipeline.apply_correction(issue.id, value, decision, user=user)
                result = pipeline.get_post_validation_result(issue.id)
                post_status = result.status if result is not None else "skip"
            except Exception as exc:
                # Correção não aplicável (ex.: material exige revisão manual): não conta
                # como conformidade; registra como skip e segue (cópia descartável).
                logger.debug(
                    "Revisor simulado: falha ao aplicar {} em {}: {}",
                    decision,
                    issue.id,
                    exc,
                )
                post_status = "skip"

        decisions.append(
            ReviewDecision(
                issue_id=issue.id,
                element_guid=issue.element_guid,
                issue_type=issue.issue_type,
                decision=decision,
                applied_value=value,
                post_validation=post_status,
            )
        )

    return _aggregate(decisions), decisions


def _aggregate(decisions: list[ReviewDecision]) -> ReviewProxyMetrics:
    """Consolida as decisões do revisor simulado em ReviewProxyMetrics."""
    total = len(decisions)
    accepted = sum(1 for d in decisions if d.decision == "accepted")
    edited = sum(1 for d in decisions if d.decision == "edited")
    rejected = sum(1 for d in decisions if d.decision == "rejected")
    review = sum(1 for d in decisions if d.decision == "review")

    post_pass = sum(1 for d in decisions if d.post_validation == "pass")
    post_fail = sum(1 for d in decisions if d.post_validation == "fail")
    post_skip = sum(1 for d in decisions if d.post_validation == "skip")
    conformity_den = post_pass + post_fail

    return ReviewProxyMetrics(
        accepted=accepted,
        edited=edited,
        rejected=rejected,
        review=review,
        total=total,
        acceptance_rate=(accepted / total) if total else 0.0,
        edit_rate=(edited / total) if total else 0.0,
        rejection_rate=(rejected / total) if total else 0.0,
        review_rate=(review / total) if total else 0.0,
        ids_post_pass=post_pass,
        ids_post_fail=post_fail,
        ids_post_skip=post_skip,
        ids_conformity_rate=(post_pass / conformity_den) if conformity_den else 0.0,
    )
