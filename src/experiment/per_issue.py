"""Resultado por issue e agregação por estrato (P1).

O ``ExperimentResult`` guarda apenas agregados: um top-1 de 33% pode ser
"tudo mediano" ou "FireRating ótimo + ThermalTransmittance zero", e depois do
run não há como distinguir. Sem o registro por issue também não é possível
teste pareado entre modelos (McNemar), análise de erro, nem verificar se uma
correção de prompt ajudou o estrato que ela mirava.

Um **estrato** é ``issue_type/check_property`` (ou só ``issue_type`` quando a
tarefa não tem propriedade alvo, como ``space_unnamed``): é a unidade em que a
tarefa muda de natureza — nomear ambiente, escolher rating de fogo, calcular
transmitância — e portanto a unidade em que a acurácia deve ser lida.

O denominador é o mesmo do ``Evaluator``: issues com entrada no ground truth.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.experiment.evaluator import Evaluator, GroundTruth
from src.models import Issue, SuggestionSet


class IssueOutcome(BaseModel):
    """Resultado de uma issue avaliada: o que se esperava, o que veio, o que casou."""

    issue_id: str
    element_guid: str
    element_class: str
    issue_type: str
    check_property: str = ""
    stratum: str
    expected: Any = None
    accepted_alternatives: list[Any] = Field(default_factory=list)
    top_values: list[Any] = Field(default_factory=list)
    """Valores das sugestões na ordem apresentada (já limitada a 3 pelo gerador)."""
    match_top1: bool = False
    match_top3: bool = False
    abstained: bool = False
    """True quando nenhuma sugestão foi produzida (abstenção ≠ erro de conteúdo)."""
    review_required: bool = False
    confidence_top1: str | None = None
    failure_reason: str | None = None
    attempts: int = 0
    reused_from: str | None = None
    """issue_id da primária quando a sugestão foi reaproveitada (não é observação nova)."""
    latency_ms: float = 0.0
    output_tokens: int = 0


def stratum_of(issue: Issue) -> str:
    """Retorna o estrato da issue: ``issue_type/propriedade`` ou só ``issue_type``."""
    check_property = str(issue.context.get("check_property") or "").strip()
    if check_property:
        return f"{issue.issue_type}/{check_property}"
    return issue.issue_type


def build_issue_outcomes(
    results: list[tuple[Issue, SuggestionSet]],
    ground_truth: GroundTruth,
    evaluator: Evaluator | None = None,
) -> list[IssueOutcome]:
    """Constrói um ``IssueOutcome`` por issue avaliada (com entrada no ground truth).

    Usa o mesmo casamento normalizado do ``Evaluator`` — top-1/top-3 aqui e no
    agregado não podem divergir.
    """
    evaluator = evaluator or Evaluator()
    outcomes: list[IssueOutcome] = []

    for issue, suggestion_set in results:
        item = ground_truth.get_for_issue(issue)
        if item is None:
            continue

        suggestions = suggestion_set.suggestions
        top3 = suggestions[:3]
        match_top1 = bool(
            suggestions and evaluator._suggestion_matches(issue, suggestions[0].value, item)
        )
        match_top3 = any(
            evaluator._suggestion_matches(issue, s.value, item) for s in top3
        )
        metrics = suggestion_set.metrics

        outcomes.append(
            IssueOutcome(
                issue_id=issue.id,
                element_guid=issue.element_guid,
                element_class=issue.element_class,
                issue_type=issue.issue_type,
                check_property=str(issue.context.get("check_property") or ""),
                stratum=stratum_of(issue),
                expected=item.expected_value,
                accepted_alternatives=list(item.accepted_alternatives),
                top_values=[s.value for s in top3],
                match_top1=match_top1,
                match_top3=match_top3,
                abstained=not suggestions,
                review_required=any(s.review_required for s in top3),
                confidence_top1=suggestions[0].confidence if suggestions else None,
                failure_reason=metrics.failure_reason if metrics else None,
                attempts=metrics.attempts if metrics else 0,
                reused_from=metrics.reused_from_issue_id if metrics else None,
                latency_ms=metrics.llm_total_ms if metrics else 0.0,
                output_tokens=metrics.output_tokens if metrics else 0,
            )
        )

    return outcomes


def aggregate_by_stratum(outcomes: list[IssueOutcome]) -> list[dict[str, Any]]:
    """Agrega top-1/top-3, abstenção e estímulos distintos por estrato.

    ``estimulos`` conta as issues que geraram chamada própria ao LLM (as demais
    reaproveitam uma primária): é o n para inferência, não o número de issues.
    """
    por_estrato: dict[str, list[IssueOutcome]] = {}
    for outcome in outcomes:
        por_estrato.setdefault(outcome.stratum, []).append(outcome)

    linhas: list[dict[str, Any]] = []
    for stratum, items in por_estrato.items():
        n = len(items)
        linhas.append(
            {
                "stratum": stratum,
                "n": n,
                "estimulos": sum(1 for o in items if o.reused_from is None),
                "top1": sum(o.match_top1 for o in items) / n,
                "top3": sum(o.match_top3 for o in items) / n,
                "abstencao": sum(o.abstained for o in items) / n,
                "acertos_top1": sum(o.match_top1 for o in items),
            }
        )

    return sorted(linhas, key=lambda row: -row["n"])


def write_outcomes_jsonl(outcomes: list[IssueOutcome], path: str | Path) -> str:
    """Grava um ``IssueOutcome`` por linha em JSONL e retorna o caminho."""
    destino = Path(path)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8") as fh:
        for outcome in outcomes:
            fh.write(json.dumps(outcome.model_dump(), ensure_ascii=False, default=str))
            fh.write("\n")
    return str(destino)


def read_outcomes_jsonl(path: str | Path) -> list[IssueOutcome]:
    """Lê um JSONL de resultados por issue produzido por ``write_outcomes_jsonl``."""
    origem = Path(path)
    outcomes: list[IssueOutcome] = []
    with origem.open("r", encoding="utf-8") as fh:
        for linha in fh:
            linha = linha.strip()
            if linha:
                outcomes.append(IssueOutcome.model_validate_json(linha))
    return outcomes
