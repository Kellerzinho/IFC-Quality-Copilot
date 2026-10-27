"""Avaliador reproduzível da condição ``m1-e4-catalog-eval-v1`` (M1-15).

O wrapper recebe referência exata, pasta e registro de operações, abre o release por
``open_catalog`` e resolve cada consulta única com ``reader.resolve_binding`` real.
Falha de abertura (``CatalogPackageError``) vira relatório de erro de pacote com zero
consultas executadas e taxas nulas; erro inesperado propaga como falha técnica. A
condição deriva do que foi efetivamente aberto e usado (ref, conteúdo, manifesto,
corpus deduplicado, artefatos, código e runtime); condição esperada divergente impede
o scoring. Não executa LLM, não usa rede e não altera instrumento ou GT legados.
"""

import hashlib
import math
import os
import platform
import statistics
import sys
import time
import tracemalloc
from collections import Counter
from collections.abc import Mapping, Sequence
from importlib.metadata import version as package_version
from pathlib import Path

from src.domain_catalog import reader as reader_module
from src.domain_catalog import resolver as resolver_module
from src.domain_catalog.canonical import canonical_json_bytes, canonical_json_text
from src.domain_catalog.contracts import RESOLVED_STATUSES, BindingRequest, CatalogReleaseRef
from src.domain_catalog.curation_models import content_sha256
from src.domain_catalog.errors import CatalogPackageError
from src.domain_catalog.evaluation_models import (
    EVALUATION_CONDITION_ID,
    EVALUATOR_VERSION,
    CaseExpectation,
    CatalogCaseResult,
    CatalogEvaluationCase,
    CatalogEvaluationCondition,
    CatalogEvaluationCorpus,
    CatalogEvaluationInputs,
    CatalogEvaluationReport,
    CatalogPerformanceReport,
    CatalogScoreSummary,
    CurationEffort,
    DeduplicatedCorpus,
    ProfileEvaluationSummary,
    QualityBlock,
    QuerySample,
    RateValue,
    ReferenceEligibility,
    ReferenceReview,
    UniqueQuery,
)
from src.domain_catalog.operations import OperationRegistry
from src.domain_catalog.profile_models import DaianeProfileInventory, ProfileReport
from src.domain_catalog.reader import CatalogReader, open_catalog

_STATUSES = ("exact", "approved_mapping", "ambiguous", "unmapped", "unsupported", "package_error")
_ABSTENTIONS = frozenset({"ambiguous", "unmapped", "unsupported"})


class EvaluationError(ValueError):
    """Entrada de avaliação recusada, com causa estável em ``code``."""

    def __init__(self, code: str, message: str) -> None:
        """Guarda a causa estável e a mensagem legível."""
        self.code = code
        super().__init__(f"[{code}] {message}")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_sha256(value: object) -> str:
    return _sha256(canonical_json_bytes(value))


# --- Corpus e referência ----------------------------------------------------------------


def query_key(case_request: BindingRequest) -> str:
    """Chave da consulta: JSON canônico do pedido sem ``requirement_ref``."""
    dump = case_request.model_dump(mode="json", exclude={"requirement_ref"})
    return canonical_json_text(dump)


def dedupe_corpus(corpus: CatalogEvaluationCorpus) -> DeduplicatedCorpus:
    """Agrega duplicatas semânticas, recusa ID repetido e vazamento entre splits."""
    ids = Counter(case.case_id for case in corpus.cases)
    repeated = sorted(k for k, v in ids.items() if v > 1)
    if repeated:
        raise EvaluationError("duplicate_case_id", f"case_id repetido: {repeated}")
    groups: dict[str, list[CatalogEvaluationCase]] = {}
    for case in corpus.cases:
        groups.setdefault(query_key(case.request), []).append(case)
    queries: list[UniqueQuery] = []
    excluded_cases: list[tuple[str, str]] = []
    strata: Counter[str] = Counter()
    shared: set[str] = set()
    multi: list[str] = []
    for key in sorted(groups):
        cases = groups[key]
        splits = {case.split for case in cases}
        if len(splits) > 1:
            raise EvaluationError(
                "split_leakage",
                f"consulta presente em development e evaluation: {[c.case_id for c in cases]}",
            )
        expectations = {
            canonical_json_text(case.expectation.model_dump(mode="json"))
            for case in cases
            if case.expectation is not None
        }
        excluded = all(case.exclusion_reason is not None for case in cases)
        excluded_cases.extend(
            (case.case_id, case.exclusion_reason) for case in cases if case.exclusion_reason
        )
        if not excluded:
            own = {case.stratum for case in cases if case.exclusion_reason is None}
            if len(own) == 1:
                strata[own.pop()] += 1
            else:
                multi.append(key)
                shared.update(own)
        queries.append(
            UniqueQuery(
                query_key=key,
                request=cases[0].request,
                case_ids=tuple(case.case_id for case in cases),
                source_refs=tuple(ref for case in cases for ref in case.source_refs),
                split=cases[0].split,
                origins=tuple(sorted({case.origin for case in cases})),
                excluded=excluded,
                reference_conflict=len(expectations) > 1,
            )
        )
    return DeduplicatedCorpus(
        total_cases=len(corpus.cases),
        total_unique=len(queries),
        included=sum(1 for q in queries if not q.excluded),
        excluded=sum(1 for q in queries if q.excluded),
        excluded_cases=tuple(excluded_cases),
        queries=tuple(queries),
        conflicts=tuple(q.query_key for q in queries if q.reference_conflict),
        strata=dict(sorted(strata.items())),
        multi_stratum_queries=tuple(multi),
        strata_only_in_shared_queries=tuple(sorted(shared - set(strata))),
    )


def corpus_sha256(dedup: DeduplicatedCorpus) -> str:
    """Hash do corpus deduplicado (consultas, split e exclusão), sem proveniência variável."""
    return _canonical_sha256(
        [
            {"query_key": q.query_key, "split": q.split, "excluded": q.excluded}
            for q in dedup.queries
        ]
    )


def labels_sha256(corpus: CatalogEvaluationCorpus) -> str:
    """Hash dos registros completos de caso (pedido, origem, split, estrato, exclusão e
    rótulo): qualquer alteração feita depois da revisão é detectada."""
    return _canonical_sha256({case.case_id: case.model_dump(mode="json") for case in corpus.cases})


def _normalized_name(text: str) -> str:
    """Nome declarado sem diferença de caixa e de espaços, para comparar revisor e gerador."""
    return " ".join(text.split()).casefold()


def _origin_label(corpus: CatalogEvaluationCorpus) -> str:
    """Rótulo das métricas; corpus que mistura casos sintéticos e reais é recusado."""
    origins = {case.origin == "synthetic" for case in corpus.cases}
    if len(origins) > 1:
        raise EvaluationError(
            "mixed_origins",
            "corpus mistura casos sintéticos e reais; avalie-os em corpora separados",
        )
    return "synthetic_contract" if origins == {True} else "real_corpus"


def load_reference_review(
    review: ReferenceReview, corpus: CatalogEvaluationCorpus, *, evidence: Mapping[str, bytes]
) -> ReferenceEligibility:
    """Confere a revisão de referência; qualquer falha torna os casos inelegíveis.

    Recalcula hashes de corpus, rótulos e evidência fornecida explicitamente; exige
    status ``accepted``, revisor declarado distinto do gerador, split ``evaluation`` e
    origem não sintética. Mesmo elegível, só autoriza concordância com referência
    declarada (``identity_assurance = unverified_local``).
    """
    reasons: list[str] = []
    hashes = {
        "corpus_sha256": corpus_sha256(dedupe_corpus(corpus)),
        "labels_sha256": labels_sha256(corpus),
        "review_sha256": _canonical_sha256(review.model_dump(mode="json")),
    }
    data = evidence.get(review.evidence_file)
    if data is None:
        reasons.append(f"evidência {review.evidence_file} não fornecida")
    elif _sha256(data) != review.evidence_sha256:
        reasons.append("evidência com hash divergente do registro de revisão")
    if review.status != "accepted":
        reasons.append(f"status {review.status}; só accepted habilita a referência")
    generator = {_normalized_name(review.generator_declared), _normalized_name(corpus.generated_by)}
    if _normalized_name(review.reviewer_declared) in generator:
        reasons.append("revisor declarado igual ao gerador do corpus")
    if hashes["labels_sha256"] != review.labels_sha256:
        reasons.append("rótulos ou registros de caso alterados após a revisão (hash divergente)")
    if hashes["corpus_sha256"] != review.corpus_sha256:
        reasons.append("corpus difere do revisado (hash divergente)")
    by_id = {case.case_id: case for case in corpus.cases}
    missing = sorted(set(review.case_ids) - set(by_id))
    if missing:
        reasons.append(f"casos revisados ausentes do corpus: {missing}")
    if reasons:
        return ReferenceEligibility(
            eligible_case_ids=(),
            block="not_measured",
            reasons=tuple(reasons),
            corpus_sha256=hashes["corpus_sha256"],
            labels_sha256=hashes["labels_sha256"],
            review_sha256=hashes["review_sha256"],
        )
    eligible: list[str] = []
    for case_id in review.case_ids:
        case = by_id[case_id]
        if case.split != "evaluation":
            reasons.append(f"{case_id}: split {case.split}")
        elif case.origin == "synthetic":
            reasons.append(f"{case_id}: origem sintética não mede qualidade de domínio")
        elif case.expectation is None or case.exclusion_reason is not None:
            reasons.append(f"{case_id}: sem rótulo ou excluído")
        else:
            eligible.append(case_id)
    return ReferenceEligibility(
        eligible_case_ids=tuple(eligible),
        block="declared_reference_agreement" if eligible else "not_measured",
        reasons=tuple(reasons),
        corpus_sha256=hashes["corpus_sha256"],
        labels_sha256=hashes["labels_sha256"],
        review_sha256=hashes["review_sha256"],
    )


# --- Agregador puro -------------------------------------------------------------------------


def _rate(numerator: int, denominator: int, empty: str) -> RateValue:
    if denominator == 0:
        return RateValue(value=None, numerator=numerator, denominator=0, reason=empty)
    return RateValue(value=numerator / denominator, numerator=numerator, denominator=denominator)


def _quality(
    results: Sequence[CatalogCaseResult],
    corpus: CatalogEvaluationCorpus,
    dedup: DeduplicatedCorpus,
    reference: ReferenceEligibility | None,
) -> QualityBlock:
    by_case = {case.case_id: case for case in corpus.cases}
    conflict = {q.query_key for q in dedup.queries if q.reference_conflict}
    usable = {c.case_id for c in corpus.cases if c.expectation and c.exclusion_reason is None}
    if reference is not None:
        if (reference.corpus_sha256, reference.labels_sha256) != (
            corpus_sha256(dedup),
            labels_sha256(corpus),
        ):
            raise EvaluationError(
                "reference_mismatch",
                "elegibilidade de referência não corresponde a este corpus e a estes rótulos",
            )
        eligible_ids = usable & {
            cid
            for cid in reference.eligible_case_ids
            if cid in by_case
            and by_case[cid].origin != "synthetic"
            and by_case[cid].split == "evaluation"
        }
        block = reference.block
    else:
        eligible_ids = usable & {c.case_id for c in corpus.cases if c.origin == "synthetic"}
        block = "synthetic_reference"
    counts: Counter[str] = Counter()
    for result in results:
        expectations: list[CaseExpectation] = [
            by_case[cid].expectation  # type: ignore[misc]
            for cid in result.case_ids
            if cid in eligible_ids and by_case[cid].expectation is not None
        ]
        if not expectations:
            continue
        if result.query_key in conflict:
            counts["blocked"] += 1
            continue
        expected = expectations[0]
        counts["eligible"] += 1
        counts["status"] += int(result.status in expected.allowed_statuses)
        if expected.resolvable:
            counts["resolvable"] += 1
        if result.status in RESOLVED_STATUSES:
            counts["resolved"] += 1
            correct = expected.resolvable and (result.binding_id, result.concept_id) == (
                expected.binding_id,
                expected.concept_id,
            )
            counts["correct" if correct else "false"] += 1
    if counts["eligible"] == 0:
        block = "not_measured"
    no_ref = "sem casos com referência elegível executados"
    return QualityBlock(
        block=block,
        eligible_cases=counts["eligible"],
        blocked_by_conflict=counts["blocked"],
        resolved_with_reference=counts["resolved"],
        correct_resolved=counts["correct"],
        false_mapping=counts["false"],
        reference_resolvable=counts["resolvable"],
        status_matches=counts["status"],
        mapping_precision=_rate(
            counts["correct"], counts["resolved"], f"{no_ref} ou nenhum resolvido"
        ),
        mapping_recall=_rate(
            counts["correct"], counts["resolvable"], f"{no_ref} ou nenhum resolvível"
        ),
        status_accuracy=_rate(counts["status"], counts["eligible"], no_ref),
    )


def score_catalog_results(
    results: Sequence[CatalogCaseResult],
    *,
    corpus: CatalogEvaluationCorpus,
    reference: ReferenceEligibility | None = None,
    denominator_label: str = "resultados fornecidos ao agregador (fixture)",
) -> CatalogScoreSummary:
    """Contagens por estado, taxas sobre ``len(results)`` e qualidade só com referência.

    ``resolved = exact + approved_mapping``; abstenção semântica = ``ambiguous +
    unmapped + unsupported``; ``package_error`` conta à parte. Denominador zero devolve
    taxa nula com motivo, nunca 100%.
    """
    dedup = dedupe_corpus(corpus)
    label = _origin_label(corpus)
    by_status: Counter[str] = Counter(str(result.status) for result in results)
    total = len(results)
    resolved = sum(by_status[s] for s in RESOLVED_STATUSES)
    abstentions = sum(by_status[s] for s in _ABSTENTIONS)
    errors = by_status["package_error"]
    empty = "nenhum resultado executado"
    rates = {
        "resolved": _rate(resolved, total, empty),
        "abstention": _rate(abstentions, total, empty),
        "package_error": _rate(errors, total, empty),
        **{status: _rate(by_status[status], total, empty) for status in _STATUSES},
    }
    quality = _quality(results, corpus, dedup, reference)
    return CatalogScoreSummary(
        result_count=total,
        denominator_label=denominator_label,
        metrics_label="synthetic_contract" if label == "synthetic_contract" else "real_corpus",
        by_status={status: by_status[status] for status in sorted(_STATUSES)},
        resolved=resolved,
        abstentions=abstentions,
        errors=errors,
        rates=rates,
        quality=quality,
        domain_quality=(
            "declared_reference_agreement"
            if quality.block == "declared_reference_agreement"
            else "not_measured"
        ),
    )


# --- Condição e wrapper ------------------------------------------------------------------


def _verified_inputs(inputs: CatalogEvaluationInputs) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    for artifact in inputs.artifacts:
        if _sha256(artifact.data) != artifact.sha256:
            raise EvaluationError(
                "input_integrity", f"{artifact.role}:{artifact.label} difere do hash declarado"
            )
        artifacts[f"{artifact.role}:{artifact.label}"] = artifact.sha256
    return dict(sorted(artifacts.items()))


def _measured_runtime() -> dict[str, str]:
    """Interpretador e Pydantic medidos no processo (não declarados por quem chama)."""
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "pydantic": package_version("pydantic"),
    }


def _code_sha256() -> dict[str, str]:
    """Hash do código que executa a avaliação (avaliador, reader e resolver).

    Escopo deliberado: os três módulos que decidem resolução e pontuação. Módulos
    transitivos (contratos, modelos, leitor de pacote) não entram; mudança neles muda a
    condição só se mudar conteúdo/manifesto do release lido. Ver protocolo §1.
    """
    modules = {
        "evaluation": sys.modules[__name__],
        "reader": reader_module,
        "resolver": resolver_module,
    }
    return {
        name: _sha256(Path(str(module.__file__)).read_bytes().replace(b"\r\n", b"\n"))
        for name, module in sorted(modules.items())
    }


def derive_condition(
    reader: CatalogReader,
    corpus: CatalogEvaluationCorpus,
    inputs: CatalogEvaluationInputs,
    registry: OperationRegistry,
    reference: ReferenceEligibility | None = None,
) -> CatalogEvaluationCondition:
    """Condição a partir do reader aberto, do corpus (consultas e registros completos de
    caso), da referência conferida e dos artefatos efetivamente usados."""
    dedup = dedupe_corpus(corpus)
    fields = {
        "condition_id": EVALUATION_CONDITION_ID,
        "evaluator_version": EVALUATOR_VERSION,
        "catalog_ref": reader.ref.model_dump(mode="json"),
        "content_sha256": content_sha256(reader.content),
        "manifest_sha256": _canonical_sha256(reader.describe().model_dump(mode="json")),
        "corpus_sha256": corpus_sha256(dedup),
        "input_artifacts": _verified_inputs(inputs),
        "case_records_sha256": labels_sha256(corpus),
        "reference_review_sha256": None if reference is None else reference.review_sha256,
        "reference_eligible_case_ids": (
            [] if reference is None else list(reference.eligible_case_ids)
        ),
        "code_sha256": _code_sha256(),
        "operation_ids": list(registry.operation_ids),
        "runtime": dict(sorted(inputs.runtime.items())),
        "measured_runtime": _measured_runtime(),
    }
    return CatalogEvaluationCondition.model_validate(
        {**fields, "condition_sha256": _canonical_sha256(fields)}
    )


def _attempt(ref: CatalogReleaseRef, dedup: DeduplicatedCorpus) -> str:
    return _canonical_sha256({"ref": ref.model_dump(mode="json"), "corpus": corpus_sha256(dedup)})


def run_catalog_evaluation(
    ref: CatalogReleaseRef,
    release_dir: Path,
    corpus: CatalogEvaluationCorpus,
    *,
    inputs: CatalogEvaluationInputs,
    registry: OperationRegistry,
    expected_condition: CatalogEvaluationCondition | None = None,
    reference_review: ReferenceReview | None = None,
    reference_evidence: Mapping[str, bytes] | None = None,
) -> CatalogEvaluationReport:
    """Abre o release fixado, confere a condição e resolve as consultas únicas incluídas.

    A referência é conferida aqui mesmo (``load_reference_review`` sobre a revisão e os
    bytes de evidência fornecidos); elegibilidade pronta não é aceita pelo wrapper.
    """
    dedup = dedupe_corpus(corpus)
    _origin_label(corpus)
    _verified_inputs(inputs)
    reference = (
        None
        if reference_review is None
        else load_reference_review(reference_review, corpus, evidence=reference_evidence or {})
    )
    included = [q for q in dedup.queries if not q.excluded]
    try:
        reader = open_catalog(ref, release_dir, registry=registry)
    except CatalogPackageError as exc:
        return CatalogEvaluationReport(
            run_status="package_error",
            requested_ref=ref,
            attempt_sha256=_attempt(ref, dedup),
            condition=None,
            corpus=dedup,
            executed_cases=0,
            not_executed_cases=len(included),
            package_open_errors=1,
            package_error_reason=str(exc),
            results=(),
            summary=score_catalog_results(
                (),
                corpus=corpus,
                denominator_label="nenhuma consulta executada (pacote não aberto)",
            ),
        )
    condition = derive_condition(reader, corpus, inputs, registry, reference)
    if expected_condition is not None and expected_condition != condition:
        raise EvaluationError(
            "condition_mismatch",
            f"condição esperada {expected_condition.condition_sha256} difere da derivada "
            f"{condition.condition_sha256}; nenhum scoring executado",
        )
    results = []
    for query in included:
        resolution = reader.resolve_binding(query.request)
        results.append(
            CatalogCaseResult(
                query_key=query.query_key,
                case_ids=query.case_ids,
                status=resolution.status,
                binding_id=resolution.binding_id,
                concept_id=resolution.concept_id,
                reasons=resolution.reasons,
            )
        )
    return CatalogEvaluationReport(
        run_status="completed",
        requested_ref=ref,
        attempt_sha256=_attempt(ref, dedup),
        condition=condition,
        corpus=dedup,
        executed_cases=len(results),
        not_executed_cases=0,
        package_open_errors=0,
        results=tuple(results),
        summary=score_catalog_results(
            results,
            corpus=corpus,
            reference=reference,
            denominator_label="consultas únicas executadas",
        ),
    )


# --- Medição de recurso -------------------------------------------------------------------


def nearest_rank_p95(samples: Sequence[int]) -> int | None:
    """Percentil 95 pelo método nearest-rank: elemento ``ceil(0,95·n)`` da amostra ordenada."""
    if not samples:
        return None
    ordered = sorted(samples)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def _environment(dedup: DeduplicatedCorpus) -> dict[str, str]:
    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or "não informado",
        "cpu_count": str(os.cpu_count() or 0),
        "corpus_unique_queries": str(dedup.total_unique),
    }


def benchmark_catalog_queries(
    ref: CatalogReleaseRef,
    release_dir: Path,
    corpus: CatalogEvaluationCorpus,
    *,
    inputs: CatalogEvaluationInputs,
    registry: OperationRegistry,
    repetitions: int = 20,
    open_repetitions: int = 5,
    expected_condition: CatalogEvaluationCondition | None = None,
) -> CatalogPerformanceReport:
    """Mede aberturas em novas instâncias e consultas em reader aquecido.

    ``os_cache_control = not_controlled``: nova instância não significa cache de SO frio.
    Memória é o pico do heap Python (``tracemalloc``) alocado durante a medição, não RSS.
    Sem limiar nem SLA. ``expected_condition`` divergente da condição derivada na
    primeira abertura é recusada (``condition_mismatch``) antes de medir consultas.
    Rastreamento ``tracemalloc`` iniciado por quem chama continua ativo (seu pico é
    reiniciado para a medição); sem rastreamento prévio, o benchmark inicia e encerra o seu.
    """
    if open_repetitions < 1:
        raise EvaluationError("invalid_benchmark", "open_repetitions precisa ser ≥ 1")
    dedup = dedupe_corpus(corpus)
    _verified_inputs(inputs)
    open_samples: list[int] = []
    outer_trace = tracemalloc.is_tracing()
    if outer_trace:
        baseline = tracemalloc.get_traced_memory()[0]
        tracemalloc.reset_peak()
    else:
        baseline = 0
        tracemalloc.start()
    try:
        reader: CatalogReader | None = None
        condition: CatalogEvaluationCondition | None = None
        for _ in range(open_repetitions):
            start = time.perf_counter_ns()
            try:
                reader = open_catalog(ref, release_dir, registry=registry)
            except CatalogPackageError as exc:
                raise EvaluationError("package_error", str(exc)) from exc
            open_samples.append(time.perf_counter_ns() - start)
            if condition is None:
                condition = derive_condition(reader, corpus, inputs, registry)
                if expected_condition is not None and expected_condition != condition:
                    raise EvaluationError(
                        "condition_mismatch",
                        f"condição esperada {expected_condition.condition_sha256} difere da "
                        f"derivada {condition.condition_sha256}; nenhuma consulta medida",
                    )
        if reader is None or condition is None:
            raise EvaluationError("invalid_benchmark", "nenhuma abertura medida")
        query_samples: list[QuerySample] = []
        for query in (q for q in dedup.queries if not q.excluded):
            start = time.perf_counter_ns()
            reader.resolve_binding(query.request)
            warmup = max(time.perf_counter_ns() - start, 1)
            samples: list[int] = []
            for _ in range(repetitions):
                start = time.perf_counter_ns()
                reader.resolve_binding(query.request)
                samples.append(time.perf_counter_ns() - start)
            query_samples.append(
                QuerySample(
                    query_key=query.query_key,
                    warmup_ns=warmup,
                    samples_ns=tuple(samples),
                    median_ns=float(statistics.median(samples)),
                    p95_ns=nearest_rank_p95(samples) or 0,
                )
            )
        peak = max(tracemalloc.get_traced_memory()[1] - baseline, 0)
    finally:
        if not outer_trace:
            tracemalloc.stop()
    return CatalogPerformanceReport(
        condition_sha256=condition.condition_sha256,
        corpus_sha256=condition.corpus_sha256,
        os_cache_control="not_controlled",
        open_samples_ns=tuple(open_samples),
        open_median_ns=float(statistics.median(open_samples)),
        open_p95_ns=nearest_rank_p95(open_samples) or 0,
        query_samples=tuple(query_samples),
        peak_python_heap_bytes=peak,
        percentile_method="nearest_rank",
        environment=_environment(dedup),
    )


# --- Cobertura documental do perfil em rascunho ---------------------------------------------


def summarize_profile_coverage(
    profile: DaianeProfileInventory, report: ProfileReport
) -> ProfileEvaluationSummary:
    """Cobertura documental por família/categoria e eixos; nenhum reader é simulado."""
    recon = profile.reconciliation
    by_family: dict[str, Counter[str]] = {}
    by_category: dict[str, Counter[str]] = {}
    for item in recon.dispositions:
        by_family.setdefault(item.family_id or "documento", Counter())[item.destination] += 1
        by_category.setdefault(item.category or "sem_categoria", Counter())[item.destination] += 1
    effort = CurationEffort(
        recorded_actions={
            "transcription_reviews": len(profile.b_inventory.reviews),
            "transcription_corrections": len(profile.b_inventory.changes),
            "decisions_referenced": len(recon.decisions),
            "assistant_correspondence_proposals": sum(
                1 for c in recon.correspondences if c.review_state == "assistant_proposal"
            ),
            "human_decided_correspondences": sum(
                1 for c in recon.correspondences if c.review_state == "human_decided"
            ),
        },
        human_duration="not_measured",
        instrument="docs/catalogo/protocolo-avaliacao.md (seção Esforço de curadoria)",
    )
    return ProfileEvaluationSummary(
        evaluation_mode="documentary_coverage_only",
        draft_content_sha256=recon.bases.candidates_content_sha256,
        reconciliation_sha256=profile.reconciliation_sha256,
        by_family_destination={k: dict(sorted(v.items())) for k, v in sorted(by_family.items())},
        by_category_destination={
            k: dict(sorted(v.items())) for k, v in sorted(by_category.items())
        },
        by_axis=report.by_axis,
        inventory_accounted_for=report.inventory_accounted_for,
        domain_review_complete=report.domain_review_complete,
        profile_operational=report.profile_operational,
        curation_effort=effort,
    )
