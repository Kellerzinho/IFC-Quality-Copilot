"""Motor de avaliação de sugestões contra ground truth (Fase 0.3 / F10+F11).

Promovido de ``tests/evaluation/evaluation_framework.py`` para produção. Avalia a
qualidade das sugestões geradas pelo pipeline contra um conjunto de referência
(ground truth), com:

- **Chave natural** ``(element_guid, issue_type, check_property)`` para casar issues
  entre execuções distintas (compatível com IDs determinísticos da Fase 0.2). Mantém
  compatibilidade por ``issue_id`` para os testes legados.
- **Comparação normalizada** (F10): usa ``normalize_value_for_issue`` nos dois lados,
  floats com tolerância relativa, booleanos e strings com casefold/strip
  insensível a acentos. Substitui o frágil ``str(x) == str(y)``.
- **Métricas formalizadas** (F11): top-1/top-3 e precision/recall/f1 com definição
  documentada (ver ``docs/metricas-avaliacao.md``).

As definições de métricas estão nas docstrings de :class:`EvaluationMetrics`.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import yaml
from pydantic import BaseModel, Field, model_validator

from src.experiment.ground_truth_policy import Confidence, SourceKind
from src.models import (
    Issue,
    ProfileRegistry,
    ReadinessProfile,
    ReadinessScore,
    SuggestionSet,
)
from src.suggestion_engine.normalization import (
    _normalize_key,
    normalize_value_for_issue,
    parse_numeric_value,
)

if TYPE_CHECKING:
    from src.pipeline import QualityPipeline

# Tolerância relativa default para comparação de floats (2%).
DEFAULT_FLOAT_TOLERANCE = 0.02

# Banda de equivalência por propriedade, quando 2% não mede o que se quer medir.
#
# ``ThermalTransmittance``: o valor de referência do prédio é ele mesmo **derivado**
# por cálculo (NBR 15220-2) a partir de λ tabelados e resistências superficiais
# assumidas — não é uma medição. Exigir concordância de 2% com uma estimativa
# reprova o que, em projeto, é a mesma parede: medido em 2026-07-27, o modelo
# devolveu 2,48 W/(m²·K) onde o GT calculado é 2,35 (5,5%), e o estrato inteiro
# (548 itens) foi a zero. A banda de 10% é a equivalência usual entre memórias de
# cálculo térmico que diferem nas hipóteses de camada e resistência superficial.
#
# Nada é escondido por isso: o erro relativo de cada issue fica gravado no
# resultado por issue, e o breakdown reporta MAPE e as faixas ±10%/±20%, de modo
# que o top-1 sob qualquer banda pode ser recalculado sem repetir o experimento.
TOLERANCE_BY_PROPERTY: dict[str, float] = {
    "ThermalTransmittance": 0.10,
}


def tolerance_for_issue(issue: Issue, default: float = DEFAULT_FLOAT_TOLERANCE) -> float:
    """Retorna a banda de equivalência aplicável à propriedade da issue."""
    check_property = str(issue.context.get("check_property") or "").strip()
    return TOLERANCE_BY_PROPERTY.get(check_property, default)

_TRUE_TOKENS = {"true", "verdadeiro", "sim", "yes", "y", "1"}
_FALSE_TOKENS = {"false", "falso", "nao", "no", "n", "0"}


# ---------------------------------------------------------------------------
# Comparação normalizada (F10)
# ---------------------------------------------------------------------------


def _coerce_bool(value: Any) -> bool | None:
    """Converte valores booleanos textuais/numéricos para bool, ou None se não for."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        token = value.strip().casefold()
        if token in _TRUE_TOKENS:
            return True
        if token in _FALSE_TOKENS:
            return False
    return None


def _as_float(value: Any) -> float | None:
    """Extrai float de um valor numérico ou textual; bool nunca é tratado como número."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return parse_numeric_value(value)


def _as_scalar_number(value: Any) -> float | None:
    """Float de um valor que É um número — não de um texto que apenas contém um.

    ``"REI 60"`` contém 60 mas é uma **classe** de resistência ao fogo. Tratá-lo
    como número fazia ``EI 60``, ``R 60`` e ``REI 60`` casarem entre si, e o
    estrato de FireRating (40% do ground truth do prédio) passou a medir só a
    duração em minutos — ``EI 60`` não cumpre um requisito ``REI 60``.

    Texto integralmente numérico (``"2.48"``, que é como o LLM devolve grandeza)
    continua sendo número.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        texto = value.strip().replace(",", ".")
        try:
            return float(texto)
        except ValueError:
            return None
    return None


def _compare_normalized(
    candidate: Any,
    expected: Any,
    tolerance: float = DEFAULT_FLOAT_TOLERANCE,
) -> bool:
    """Compara normalizados: número por tolerância; bool/texto por igualdade."""
    # Booleanos primeiro: "true"/"1" devem casar com True, não cair no ramo numérico.
    cand_bool = _coerce_bool(candidate)
    exp_bool = _coerce_bool(expected)
    # Só trata como booleano se algum dos lados for genuinamente booleano
    # (evita que "1" vs "1.0" numéricos caiam aqui de forma indevida).
    if (
        cand_bool is not None
        and exp_bool is not None
        and (isinstance(candidate, bool) or isinstance(expected, bool))
    ):
        return cand_bool == exp_bool

    # Comparacao numerica so quando os DOIS lados sao mesmo numeros: string com
    # numero embutido ("REI 60") e categoria, e comparar categorias pelo numero
    # apagava a distincao entre classes de resistencia ao fogo.
    cand_num = _as_scalar_number(candidate)
    exp_num = _as_scalar_number(expected)
    if cand_num is not None and exp_num is not None:
        if exp_num == 0.0:
            return abs(cand_num) <= 1e-9
        return abs(cand_num - exp_num) <= tolerance * abs(exp_num)

    if cand_bool is not None and exp_bool is not None:
        return cand_bool == exp_bool

    return _normalize_key(str(candidate)) == _normalize_key(str(expected))


def values_match(
    issue: Issue,
    candidate: Any,
    expected: Any,
    tolerance: float = DEFAULT_FLOAT_TOLERANCE,
) -> bool:
    """Indica se ``candidate`` casa com ``expected`` para a issue, após normalização.

    Aplica ``normalize_value_for_issue`` aos dois lados (mesma normalização que o
    pipeline usa antes de escrever no IFC) e então compara com tolerância numérica,
    igualdade booleana ou chave textual insensível a acentos/caixa.
    """
    norm_candidate = normalize_value_for_issue(issue, candidate)
    if norm_candidate is None:
        norm_candidate = candidate
    norm_expected = normalize_value_for_issue(issue, expected)
    if norm_expected is None:
        norm_expected = expected
    return _compare_normalized(norm_candidate, norm_expected, tolerance)


# ---------------------------------------------------------------------------
# Ground truth (v2: chave natural + YAML + accepted_alternatives)
# ---------------------------------------------------------------------------


class GroundTruthItem(BaseModel):
    """Um item de referência: valor esperado para uma issue, com alternativas aceitas.

    A issue é identificada pela **chave natural** ``(element_guid, issue_type,
    check_property)`` quando disponível; ``issue_id`` é mantido como fallback de
    compatibilidade com ground truths antigos baseados em id.
    """

    element_guid: str | None = None
    issue_type: str | None = None
    check_property: str = ""
    issue_id: str | None = None
    expected_value: Any = None
    accepted_alternatives: list[Any] = Field(default_factory=list)
    verified: bool = False
    notes: str | None = None
    equivalence_id: str | None = None
    confidence: Confidence | None = None
    source_kind: SourceKind | None = None
    legacy_reference: bool = False

    @property
    def natural_key(self) -> tuple[str, str, str] | None:
        """Retorna a chave natural ``(guid, issue_type, check_property)`` ou None."""
        if self.element_guid and self.issue_type:
            return (self.element_guid, self.issue_type, self.check_property or "")
        return None

    def all_accepted_values(self) -> list[Any]:
        """Lista o valor esperado seguido das alternativas aceitas."""
        return [self.expected_value, *self.accepted_alternatives]


class GroundTruth(BaseModel):
    """Conjunto de referência versionável para avaliação.

    Aceita três formas de construção:

    - ``GroundTruth(items=[...])`` — forma canônica (v2).
    - ``GroundTruth(corrections={issue_id: valor})`` — forma legada por id (compat).
    - ``GroundTruth.from_yaml(path)`` — carrega de arquivo YAML validado.
    """

    items: list[GroundTruthItem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_corrections(cls, data: Any) -> Any:
        """Converte ``corrections={id: valor}`` (forma legada) em itens por issue_id."""
        if isinstance(data, dict) and data.get("corrections") is not None:
            data = dict(data)
            corrections = data.pop("corrections")
            items = list(data.get("items") or [])
            for issue_id, value in corrections.items():
                items.append({"issue_id": issue_id, "expected_value": value})
            data["items"] = items
        return data

    def model_post_init(self, __context: Any) -> None:
        """Constrói índices de lookup por chave natural e por issue_id."""
        self._by_natural_key: dict[tuple[str, str, str], GroundTruthItem] = {}
        self._by_issue_id: dict[str, GroundTruthItem] = {}
        for item in self.items:
            key = item.natural_key
            if key is not None:
                self._by_natural_key[key] = item
            if item.issue_id:
                self._by_issue_id[item.issue_id] = item

    def get_for_issue(self, issue: Issue) -> GroundTruthItem | None:
        """Recupera o item de GT da issue: chave natural primeiro, issue_id como fallback."""
        check_property = str(issue.context.get("check_property") or "")
        natural = (issue.element_guid, issue.issue_type, check_property)
        item = self._by_natural_key.get(natural)
        if item is not None:
            return item
        return self._by_issue_id.get(issue.id)

    @property
    def corrections(self) -> dict[str, Any]:
        """Mapeamento compat ``{issue_id: expected_value}`` (apenas itens com issue_id)."""
        return {
            item.issue_id: item.expected_value
            for item in self.items
            if item.issue_id is not None
        }

    @classmethod
    def from_yaml(cls, path: str | Path) -> GroundTruth:
        """Carrega e valida um ground truth de arquivo YAML.

        Estrutura esperada::

            metadata: {source: ..., verified_by: ..., date: ...}
            items:
              - element_guid: 3xY...
                issue_type: pset_missing
                check_property: ThermalTransmittance
                expected_value: 2.5
                accepted_alternatives: []
                verified: true
        """
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"YAML de ground truth inválido em {path}: raiz deve ser mapeamento")
        return cls.model_validate(raw)


# ---------------------------------------------------------------------------
# Métricas de avaliação
# ---------------------------------------------------------------------------


class AccuracySlice(BaseModel):
    """Acurácia top-k e contagens de um corte do ground truth."""

    top1: float = 0.0
    top3: float = 0.0
    total: int = 0
    top1_hits: int = 0
    top3_hits: int = 0


@dataclass(frozen=True)
class _AccuracyObservation:
    equivalence_id: str
    confidence: str
    legacy_reference: bool
    top1_hit: bool
    top3_hit: bool
    has_suggestion: bool


class EvaluationMetrics(BaseModel):
    """Métricas de avaliação de um conjunto de sugestões, com suporte a perfis.

    Definições formais (F11 — ver ``docs/metricas-avaliacao.md``). Seja G o conjunto
    de issues avaliadas que possuem entrada no ground truth (após filtro de perfil),
    e S ⊆ G as que receberam ao menos uma sugestão:

    - ``accuracy_top1`` = |{i ∈ G : top-1 casa GT}| / |G|
    - ``accuracy_top3`` = |{i ∈ G : alguma das top-3 casa GT}| / |G|
    - ``precision`` = |{i ∈ S : top-1 casa GT}| / |S| (acurácia top-1 **condicionada à
      geração** — o sistema só "tenta" quando não se abstém; não é precisão no sentido IR).
    - ``recall`` = |{i ∈ G : top-1 casa GT}| / |GT| (cobertura sobre todo o ground truth,
      contando abstenções e issues filtradas como erro).
    - ``f1`` = média harmônica de precision e recall.

    A comparação "casa GT" é **normalizada** (``values_match``), não string exata.
    """

    accuracy_top1: float = 0.0
    """Proporção de issues (com GT) em que a sugestão top-1 casa o ground truth."""

    accuracy_top3: float = 0.0
    """Proporção de issues (com GT) em que alguma das 3 primeiras casa o ground truth."""

    precision: float = 0.0
    """Acurácia top-1 condicionada à geração: acertos / issues que receberam sugestão."""

    recall: float = 0.0
    """Cobertura: acertos top-1 / total de itens no ground truth."""

    f1: float = 0.0
    """Média harmônica entre precision e recall."""

    total_evaluated: int = 0
    """Número de issues avaliadas (presentes no ground truth, após filtro de perfil)."""

    accuracy_all: AccuracySlice = Field(default_factory=AccuracySlice)
    """Microacurácia sobre todas as ocorrências; reproduz os campos legados."""

    accuracy_equivalence: AccuracySlice = Field(default_factory=AccuracySlice)
    """Macroacurácia: média simples da acurácia interna de cada equivalência."""

    accuracy_by_confidence: dict[str, AccuracySlice] = Field(default_factory=dict)
    """Microacurácia separada em high, medium e low."""

    accuracy_legacy: AccuracySlice = Field(default_factory=AccuracySlice)
    """Microacurácia restrita aos itens preservados da base anterior."""

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

    def __init__(self, float_tolerance: float = DEFAULT_FLOAT_TOLERANCE) -> None:
        """Configura a tolerância relativa usada na comparação numérica."""
        self.float_tolerance = float_tolerance

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
            ground_truth: referência com chave natural (e compat por issue_id).
            profile: perfil de prontidão para filtrar issues e calcular readiness.
                     Se None, avalia todas as issues sem cálculo de readiness.

        Returns:
            EvaluationMetrics com acurácia, precision/recall/f1 (normalizados) e,
            quando perfil fornecido, scores de prontidão antes e depois das correções.
        """
        filtered = self._filter_by_profile(results, profile)

        observations, precision, recall, f1 = self._compute_accuracy(filtered, ground_truth)
        accuracy_all = self._micro_accuracy(observations)
        accuracy_equivalence = self._equivalence_accuracy(observations)
        accuracy_by_confidence = {
            confidence: self._micro_accuracy(
                [item for item in observations if item.confidence == confidence]
            )
            for confidence in ("high", "medium", "low")
        }
        accuracy_legacy = self._micro_accuracy(
            [item for item in observations if item.legacy_reference]
        )

        readiness_before, readiness_after, improvement = self._compute_readiness(
            filtered, ground_truth, profile
        )

        return EvaluationMetrics(
            accuracy_top1=accuracy_all.top1,
            accuracy_top3=accuracy_all.top3,
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1=round(f1, 4),
            total_evaluated=accuracy_all.total,
            accuracy_all=accuracy_all,
            accuracy_equivalence=accuracy_equivalence,
            accuracy_by_confidence=accuracy_by_confidence,
            accuracy_legacy=accuracy_legacy,
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
        pipeline: QualityPipeline,
        ground_truth: GroundTruth,
        registry: ProfileRegistry,
    ) -> dict[str, EvaluationMetrics]:
        """Avalia o pipeline para todos os perfis registrados.

        Reutiliza os resultados já gerados pelo pipeline (issues_suggestions)
        sem re-executar diagnóstico ou geração de sugestões.

        Args:
            pipeline: pipeline com diagnóstico e sugestões já executados.
            ground_truth: referência de avaliação.
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
                "accuracy_equivalence_top1": m.accuracy_equivalence.top1,
                "accuracy_equivalence_top3": m.accuracy_equivalence.top3,
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
            "accuracy_equivalence_top1",
            "accuracy_equivalence_top3",
            "accuracy_high_top1",
            "accuracy_medium_top1",
            "accuracy_low_top1",
            "accuracy_legacy_top1",
            "occurrence_count",
            "equivalence_count",
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
                    "accuracy_equivalence_top1": metrics.accuracy_equivalence.top1,
                    "accuracy_equivalence_top3": metrics.accuracy_equivalence.top3,
                    "accuracy_high_top1": metrics.accuracy_by_confidence["high"].top1,
                    "accuracy_medium_top1": metrics.accuracy_by_confidence["medium"].top1,
                    "accuracy_low_top1": metrics.accuracy_by_confidence["low"].top1,
                    "accuracy_legacy_top1": metrics.accuracy_legacy.top1,
                    "occurrence_count": metrics.accuracy_all.total,
                    "equivalence_count": metrics.accuracy_equivalence.total,
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

    def _suggestion_matches(
        self,
        issue: Issue,
        candidate_value: Any,
        item: GroundTruthItem,
    ) -> bool:
        """True se a sugestão casa o valor esperado ou alguma alternativa aceita.

        A banda de equivalência é resolvida por propriedade
        (``TOLERANCE_BY_PROPERTY``), caindo na tolerância do avaliador quando a
        propriedade não tem banda própria.
        """
        tolerance = tolerance_for_issue(issue, self.float_tolerance)
        return any(
            values_match(issue, candidate_value, accepted, tolerance)
            for accepted in item.all_accepted_values()
        )

    def _compute_accuracy(
        self,
        filtered: list[tuple[Issue, SuggestionSet]],
        ground_truth: GroundTruth,
    ) -> tuple[list[_AccuracyObservation], float, float, float]:
        """Calcula acurácia top-1, top-3, precision, recall e f1 (comparação normalizada).

        Ver :class:`EvaluationMetrics` para as definições formais.

        Returns:
            (accuracy_top1, accuracy_top3, precision, recall, f1, total_evaluated)
        """
        observations: list[_AccuracyObservation] = []
        total_with_suggestion = 0

        for issue, suggestion_set in filtered:
            item = ground_truth.get_for_issue(issue)
            if item is None:
                continue

            suggestions = suggestion_set.suggestions
            top1_hit = False

            if suggestions:
                total_with_suggestion += 1
                if self._suggestion_matches(issue, suggestions[0].value, item):
                    top1_hit = True

            top3 = suggestions[:3]
            top3_hit = any(self._suggestion_matches(issue, s.value, item) for s in top3)
            equivalence_id = (
                item.equivalence_id
                or item.issue_id
                or "legacy:" + "|".join(item.natural_key or (issue.id, "", ""))
            )
            observations.append(
                _AccuracyObservation(
                    equivalence_id=equivalence_id,
                    confidence=item.confidence or "",
                    legacy_reference=item.legacy_reference,
                    top1_hit=top1_hit,
                    top3_hit=top3_hit,
                    has_suggestion=bool(suggestions),
                )
            )

        total_gt_items = len(ground_truth.items)
        top1_hits = sum(item.top1_hit for item in observations)
        precision = top1_hits / total_with_suggestion if total_with_suggestion > 0 else 0.0
        recall = top1_hits / total_gt_items if total_gt_items > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        return observations, precision, recall, f1

    @staticmethod
    def _micro_accuracy(observations: list[_AccuracyObservation]) -> AccuracySlice:
        total = len(observations)
        top1_hits = sum(item.top1_hit for item in observations)
        top3_hits = sum(item.top3_hit for item in observations)
        return AccuracySlice(
            top1=round(top1_hits / total, 4) if total else 0.0,
            top3=round(top3_hits / total, 4) if total else 0.0,
            total=total,
            top1_hits=top1_hits,
            top3_hits=top3_hits,
        )

    @staticmethod
    def _equivalence_accuracy(observations: list[_AccuracyObservation]) -> AccuracySlice:
        grouped: dict[str, list[_AccuracyObservation]] = defaultdict(list)
        for item in observations:
            grouped[item.equivalence_id].append(item)
        if not grouped:
            return AccuracySlice()
        top1 = sum(
            sum(item.top1_hit for item in members) / len(members)
            for members in grouped.values()
        ) / len(grouped)
        top3 = sum(
            sum(item.top3_hit for item in members) / len(members)
            for members in grouped.values()
        ) / len(grouped)
        return AccuracySlice(
            top1=round(top1, 4),
            top3=round(top3, 4),
            total=len(grouped),
            top1_hits=sum(item.top1_hit for item in observations),
            top3_hits=sum(item.top3_hit for item in observations),
        )

    @staticmethod
    def _compute_readiness(
        filtered: list[tuple[Issue, SuggestionSet]],
        ground_truth: GroundTruth,
        profile: ReadinessProfile | None,
    ) -> tuple[ReadinessScore | None, ReadinessScore | None, float]:
        """Calcula scores de prontidão antes e depois das correções do ground truth.

        - before: todas as issues do perfil estão presentes (nenhuma corrigida).
        - after: issues com entrada no ground truth são removidas
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

        corrected_ids = {
            issue.id
            for issue, _ in filtered
            if ground_truth.get_for_issue(issue) is not None
        }
        remaining_issues = [i for i in all_issues if i.id not in corrected_ids]
        readiness_after = ReadinessScore.compute(
            profile=profile,
            issues=remaining_issues,
            total_checks=total_checks,
        )

        improvement = readiness_after.score_percent - readiness_before.score_percent
        return readiness_before, readiness_after, improvement
