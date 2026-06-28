"""Modelos e agregação de métricas dos experimentos (Fase 0.5 / F2+F6+F7+F12).

Define o ``ExperimentResult`` Pydantic versionável que agrega:

- **metadados do run** (F7): modelo/digest, Ollama, seed/temperatura/top_p/num_ctx/
  num_predict, hash do IFC e do IDS, versão do prompt e commit do repositório;
- **avaliação vs ground truth** (Evaluator da Fase 0.3): top-1/top-3 e precision/recall/f1;
- **revisor simulado** (F6): accepted/edited/rejected/review + conformidade IDS
  pós-correção medida em cópia descartável (rotulada como simulação);
- **estabilidade da saída estruturada** (F12): % JSON válido na 1ª tentativa, média de
  tentativas, taxa de reparo de truncamento, falhas por motivo;
- **eficiência**: latência (p50/p95) e tokens por amostra.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.experiment.evaluator import EvaluationMetrics
from src.models import Issue, SuggestionMetrics


# ---------------------------------------------------------------------------
# Métricas simples por lote (compat — usada pelo runner legado e pela UI)
# ---------------------------------------------------------------------------


def calculate_metrics(issues: list[Issue]) -> dict[str, Any]:
    """Calcula métricas simples por lote de issues (taxas de decisão e contagens)."""
    total = len(issues)
    decisions = Counter(issue.status for issue in issues)
    accepted = decisions.get("accepted", 0)
    edited = decisions.get("edited", 0)
    rejected = decisions.get("rejected", 0)
    resolved = accepted + edited
    return {
        "total_issues": total,
        "accepted": accepted,
        "edited": edited,
        "rejected": rejected,
        "acceptance_rate": (accepted / total) if total else 0.0,
        "edit_rate": (edited / total) if total else 0.0,
        "resolution_rate": (resolved / total) if total else 0.0,
        "issues_by_type": dict(Counter(issue.issue_type for issue in issues)),
        "issues_by_severity": dict(Counter(issue.severity for issue in issues)),
    }


# ---------------------------------------------------------------------------
# Metadados do run (F7)
# ---------------------------------------------------------------------------


class RunMetadata(BaseModel):
    """Metadados de reprodutibilidade de uma execução (um modelo, uma réplica)."""

    model_name: str
    model_digest: str | None = None
    ollama_version: str | None = None
    seed: int | None = None
    temperature: float = 0.0
    top_p: float = 0.0
    num_ctx: int = 0
    num_predict: int = 0
    repeat_penalty: float = 0.0
    ifc_sha256: str = ""
    ids_sha256: str | None = None
    ground_truth_sha256: str | None = None
    prompt_version: str = ""
    repo_commit: str | None = None
    cache_enabled: bool = False
    replica_index: int = 0
    timestamp: str | None = None
    """ISO-8601; carimbado externamente (Date.now indisponível no harness)."""


# ---------------------------------------------------------------------------
# Revisor simulado (F6) — proxy de decisão humana
# ---------------------------------------------------------------------------


class ReviewProxyMetrics(BaseModel):
    """Resultado do revisor simulado, explicitamente rotulado como simulação.

    As decisões são derivadas da comparação normalizada com o ground truth; a
    conformidade IDS é medida aplicando as correções aceitas numa **cópia
    descartável** do IFC + PostValidator. O IFC original nunca é alterado.
    """

    simulation: Literal[True] = True
    accepted: int = 0
    edited: int = 0
    rejected: int = 0
    review: int = 0
    total: int = 0
    acceptance_rate: float = 0.0
    edit_rate: float = 0.0
    rejection_rate: float = 0.0
    review_rate: float = 0.0
    # Conformidade IDS pós-correção (PostValidator sobre cópia descartável)
    ids_post_pass: int = 0
    ids_post_fail: int = 0
    ids_post_skip: int = 0
    ids_conformity_rate: float = 0.0
    """pass / (pass + fail); ignora skips."""


# ---------------------------------------------------------------------------
# Estabilidade da saída estruturada (F12)
# ---------------------------------------------------------------------------


class StabilityMetrics(BaseModel):
    """Estabilidade do JSON estruturado produzido pelo LLM, agregada no run."""

    total_generated: int = 0
    """Sugestões geradas com chamada real ao LLM (exclui cache/reuse)."""
    json_valid_first_try: int = 0
    json_valid_first_try_rate: float = 0.0
    avg_attempts: float = 0.0
    json_repaired_count: int = 0
    json_repaired_rate: float = 0.0
    failed_count: int = 0
    failure_rate: float = 0.0
    failure_reasons: dict[str, int] = Field(default_factory=dict)


class TimingMetrics(BaseModel):
    """Eficiência: latência e tokens por amostra (a partir das SuggestionMetrics)."""

    samples: int = 0
    latency_ms_p50: float = 0.0
    latency_ms_p95: float = 0.0
    latency_ms_mean: float = 0.0
    output_tokens_total: int = 0
    output_tokens_per_sample: float = 0.0
    cache_hits: int = 0
    reused: int = 0


# ---------------------------------------------------------------------------
# Resultado agregado
# ---------------------------------------------------------------------------


class ExperimentResult(BaseModel):
    """Agrega metadados + avaliação + proxy de revisão + estabilidade + eficiência."""

    metadata: RunMetadata
    evaluation: EvaluationMetrics
    review_proxy: ReviewProxyMetrics
    stability: StabilityMetrics
    timing: TimingMetrics
    decisions: dict[str, Any] = Field(default_factory=dict)
    issue_counts: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Agregadores
# ---------------------------------------------------------------------------


def _percentile(values: list[float], pct: float) -> float:
    """Percentil por interpolação linear simples; 0.0 para lista vazia."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = pct * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * frac


def aggregate_stability(metrics_list: list[SuggestionMetrics]) -> StabilityMetrics:
    """Consolida estabilidade (F12) a partir das SuggestionMetrics do run.

    Considera apenas sugestões com chamada real ao LLM (``attempts > 0``);
    entradas de cache/reuso não contam para a estabilidade do modelo.
    """
    fresh = [m for m in metrics_list if m.attempts > 0]
    total = len(fresh)
    if total == 0:
        return StabilityMetrics()

    valid_first = sum(1 for m in fresh if m.attempts == 1 and m.final_status == "ready")
    repaired = sum(1 for m in fresh if m.json_repaired)
    failed = sum(1 for m in fresh if m.final_status == "failed")
    reasons = Counter(m.failure_reason for m in fresh if m.failure_reason)

    return StabilityMetrics(
        total_generated=total,
        json_valid_first_try=valid_first,
        json_valid_first_try_rate=valid_first / total,
        avg_attempts=sum(m.attempts for m in fresh) / total,
        json_repaired_count=repaired,
        json_repaired_rate=repaired / total,
        failed_count=failed,
        failure_rate=failed / total,
        failure_reasons=dict(reasons),
    )


def aggregate_timing(metrics_list: list[SuggestionMetrics]) -> TimingMetrics:
    """Consolida latência e tokens por amostra a partir das SuggestionMetrics."""
    fresh = [m for m in metrics_list if m.attempts > 0]
    latencies = [m.llm_total_ms for m in fresh if m.llm_total_ms > 0]
    output_tokens = sum(m.output_tokens for m in fresh)
    cache_hits = sum(1 for m in metrics_list if m.cache_hit)
    reused = sum(1 for m in metrics_list if m.reused_from_issue_id)

    return TimingMetrics(
        samples=len(fresh),
        latency_ms_p50=_percentile(latencies, 0.50),
        latency_ms_p95=_percentile(latencies, 0.95),
        latency_ms_mean=(sum(latencies) / len(latencies)) if latencies else 0.0,
        output_tokens_total=output_tokens,
        output_tokens_per_sample=(output_tokens / len(fresh)) if fresh else 0.0,
        cache_hits=cache_hits,
        reused=reused,
    )
