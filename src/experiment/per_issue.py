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
from math import comb
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.experiment.evaluator import Evaluator, GroundTruth, _as_float
from src.models import Issue, SuggestionSet


def _relative_error_pct(candidate: Any, expected: Any) -> float | None:
    """Erro relativo em % entre candidato e esperado, ou None se não for grandeza numérica.

    O **esperado** precisa ser numérico de fato: ``"REI 60"`` parseia como 60 e
    entraria como erro de 0% num estrato categórico, contaminando o MAPE. Já o
    candidato pode vir como texto (``"2.48"``), que é como o LLM costuma devolver.
    """
    if isinstance(expected, bool) or not isinstance(expected, (int, float)):
        return None
    cand = _as_float(candidate)
    if cand is None or expected == 0:
        return None
    return abs(cand - float(expected)) / abs(float(expected)) * 100.0


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
    error_pct: float | None = None
    """Erro relativo do top-1 (%) quando esperado e sugerido são numéricos.

    Acerto binário não distingue errar 5% de errar 300%; com o erro gravado, o
    top-1 sob qualquer banda de equivalência pode ser recalculado sem repetir o run.
    """
    # Proveniência de grounding (revisão bSDD 2026-08-04): sem estes campos o
    # JSONL não prova o que o bSDD entregou e a ablação de grounding não roda.
    grounding_sources: list[str] = Field(default_factory=list)
    """Fontes de grounding do prompt ("ids", "bsdd"); vazio = prompt sem grounding."""
    bsdd_source_status: str | None = None
    """source_status do BSDDContext (live/cache/empty/offline) na geração."""
    bsdd_class_uri: str | None = None
    """URI canônica da classe bSDD resolvida para a issue, se houver."""
    has_official_candidates: bool = False
    """True quando o prompt recebeu lista fechada de candidatos oficiais."""
    thermal_recomputed: bool = False
    """True quando a camada determinística refez a soma de U (condição v7).

    Separa "o modelo acertou" de "o modelo montou os termos e o código somou".
    """
    num_ctx_effective: int = 0
    """Janela de contexto realmente enviada ao Ollama nesta issue.

    O metadata do run registra a política e o valor configurado; este campo
    registra o que de fato foi usado, por chamada. Sem ele, a rodada v7.5
    publicou ``num_ctx: 8192`` — um valor que nenhuma chamada usou.
    """


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
                grounding_sources=list(metrics.grounding_sources) if metrics else [],
                bsdd_source_status=metrics.bsdd_source_status if metrics else None,
                bsdd_class_uri=metrics.bsdd_class_uri if metrics else None,
                has_official_candidates=(
                    metrics.has_official_candidates if metrics else False
                ),
                thermal_recomputed=metrics.thermal_recomputed if metrics else False,
                num_ctx_effective=metrics.num_ctx_effective if metrics else 0,
                error_pct=(
                    _relative_error_pct(suggestions[0].value, item.expected_value)
                    if suggestions
                    else None
                ),
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
        linha: dict[str, Any] = {
            "stratum": stratum,
            "n": n,
            "estimulos": sum(1 for o in items if o.reused_from is None),
            "top1": sum(o.match_top1 for o in items) / n,
            "top3": sum(o.match_top3 for o in items) / n,
            "abstencao": sum(o.abstained for o in items) / n,
            "acertos_top1": sum(o.match_top1 for o in items),
        }

        # Grandeza continua: reportar so acerto binario esconde a diferenca entre
        # errar 5% e errar 300%.
        erros = [o.error_pct for o in items if o.error_pct is not None]
        if erros:
            linha["mape"] = sum(erros) / len(erros)
            linha["dentro_10pct"] = sum(1 for e in erros if e <= 10.0) / n
            linha["dentro_20pct"] = sum(1 for e in erros if e <= 20.0) / n

        linhas.append(linha)

    return sorted(linhas, key=lambda row: -row["n"])


def mcnemar_exact(b: int, c: int) -> float:
    """p-valor bilateral do teste de McNemar exato (binomial com p=0,5).

    ``b`` = acertos só do modelo A; ``c`` = só do B. Concordâncias não carregam
    informação sobre a diferença e ficam fora do teste.
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    cauda = sum(comb(n, i) for i in range(k + 1)) / (2**n)
    return min(1.0, 2 * cauda)


def paired_comparison(
    outcomes_a: list[IssueOutcome],
    outcomes_b: list[IssueOutcome],
    unit: Literal["stimulus", "issue"] = "stimulus",
) -> dict[str, Any]:
    """Compara dois modelos nas mesmas observações, com McNemar exato.

    ``unit="stimulus"`` (default) conta **uma observação por chamada real ao
    LLM**: com ``--reuse-equivalent`` uma resposta é copiada para todas as issues
    equivalentes, e contar as cópias trata replicação como evidência. No prédio,
    6 estímulos de ``FireRating`` respondem por 1020 issues — no nível de issue,
    2 respostas de diferença viram "p < 0,0001".

    ``unit="issue"`` existe para mostrar essa inflação, não para reportar.
    """

    def indexar(outcomes: list[IssueOutcome]) -> dict[str, IssueOutcome]:
        if unit == "issue":
            return {o.issue_id: o for o in outcomes}
        # Um representante por estimulo: a primaria e suas copias compartilham
        # a mesma resposta do LLM, entao qualquer uma serve.
        por_estimulo: dict[str, IssueOutcome] = {}
        for o in outcomes:
            por_estimulo.setdefault(o.reused_from or o.issue_id, o)
        return por_estimulo

    mapa_a = indexar(outcomes_a)
    mapa_b = indexar(outcomes_b)
    comuns = sorted(set(mapa_a) & set(mapa_b))

    so_a = sum(1 for k in comuns if mapa_a[k].match_top1 and not mapa_b[k].match_top1)
    so_b = sum(1 for k in comuns if mapa_b[k].match_top1 and not mapa_a[k].match_top1)
    ambos = sum(1 for k in comuns if mapa_a[k].match_top1 and mapa_b[k].match_top1)

    return {
        "unit": unit,
        "n": len(comuns),
        "ambos": ambos,
        "so_a": so_a,
        "so_b": so_b,
        "p_value": mcnemar_exact(so_a, so_b),
    }


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
