"""Avaliação E4 integrada ao reader real (``open_catalog``/``resolve_binding``) (M1-15).

Pacotes SINTÉTICOS gravados em ``tmp_path`` por ``factories``. Pacote inválido é
aberto pelo wrapper e não gera resolução fabricada. Condição esperada divergente
impede scoring. O rascunho real do perfil só recebe cobertura documental.
"""

import hashlib
from pathlib import Path
from typing import Any

import pytest

from src.domain_catalog import evaluation as evaluation_module
from src.domain_catalog.contracts import CatalogReleaseRef
from src.domain_catalog.evaluation import (
    EvaluationError,
    benchmark_catalog_queries,
    run_catalog_evaluation,
    summarize_profile_coverage,
)
from src.domain_catalog.evaluation_models import (
    EVALUATION_CONDITION_ID,
    CatalogEvaluationCorpus,
    CatalogEvaluationInputs,
)
from src.domain_catalog.importers.daiane import MATRIX_PATH, import_appendix_a, load_matrix
from src.domain_catalog.importers.daiane_b import APPENDIX_B_PATH, load_appendix_b
from src.domain_catalog.operations import OperationRegistry
from src.domain_catalog.profile import (
    CANDIDATES_PATH,
    PDF_SHA256,
    RECONCILIATION_PATH,
    build_daiane_profile,
    load_candidates,
    load_reconciliation,
    summarize_daiane_profile,
)
from src.domain_catalog.profile_models import ProfileCapabilityEvidence
from src.validation.analysis_identity import ExecutionProfile
from tests.domain_catalog import factories as f
from tests.domain_catalog.test_catalog_evaluation import corpus

REGISTRY = OperationRegistry()


def queries() -> CatalogEvaluationCorpus:
    return corpus(
        {**_case("exato", "Status", "SYN_PsetA", "IfcWall")},
        {**_case("exato-dup", "Status", "SYN_PsetA", "IfcWall"), "source_refs": ["synthetic:dup"]},
        _case("ausente", "Inexistente", "SYN_PsetA", "IfcWall"),
        _case("metodo-laje", "SYN_Metodo", "SYN_Conjunto", "IfcSlab"),
    )


def _case(case_id: str, field: str, set_name: str, entity: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "request": {
            "ifc_schema": "IFC4",
            "facet": "property",
            "set_name": set_name,
            "field_name": field,
            "entity": entity,
        },
        "origin": "synthetic",
        "stratum": "propriedade",
        "family": "SYN",
        "facet": "property",
        "split": "evaluation",
        "source_refs": [f"synthetic:{case_id}"],
    }


def inputs(protocol: bytes = b"protocolo sintetico v1") -> CatalogEvaluationInputs:
    return CatalogEvaluationInputs.model_validate(
        {
            "artifacts": [
                {
                    "role": "protocol",
                    "label": "protocolo sintético",
                    "sha256": hashlib.sha256(protocol).hexdigest(),
                    "data": protocol,
                },
            ],
            "runtime": {"python": "fixture", "pydantic": "fixture"},
        }
    )


@pytest.fixture
def release(tmp_path: Path) -> tuple[CatalogReleaseRef, Path]:
    return f.write_synthetic_release(tmp_path / "rel")


def _tree_hash(path: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(path.iterdir())}


def test_completed_run_resolves_unique_queries_with_the_real_reader(
    release: tuple[CatalogReleaseRef, Path],
) -> None:
    ref, path = release
    before = _tree_hash(path)
    report = run_catalog_evaluation(ref, path, queries(), inputs=inputs(), registry=REGISTRY)

    assert report.run_status == "completed"
    assert report.condition is not None
    assert report.condition.condition_id == EVALUATION_CONDITION_ID
    assert (report.executed_cases, report.not_executed_cases, report.package_open_errors) == (
        3,
        0,
        0,
    )
    assert (report.corpus.total_cases, report.corpus.total_unique) == (4, 3)
    statuses = {r.case_ids: r.status for r in report.results}
    assert statuses[("exato", "exato-dup")] == "exact"
    assert statuses[("ausente",)] == "unmapped"
    assert report.summary.metrics_label == "synthetic_contract"
    assert _tree_hash(path) == before


def test_same_inputs_same_results_and_condition(release: tuple[CatalogReleaseRef, Path]) -> None:
    ref, path = release
    one = run_catalog_evaluation(ref, path, queries(), inputs=inputs(), registry=REGISTRY)
    two = run_catalog_evaluation(ref, path, queries(), inputs=inputs(), registry=REGISTRY)

    assert one.results == two.results
    assert one.condition == two.condition
    assert one.condition is not None
    fields = set(one.condition.model_dump())
    assert not {
        f for f in fields if any(t in f for t in ("timestamp", "created", "latency", "_ns"))
    }
    assert str(path) not in one.condition.model_dump_json()


def test_condition_changes_with_corpus_inputs_and_release(
    tmp_path: Path, release: tuple[CatalogReleaseRef, Path]
) -> None:
    ref, path = release
    base = run_catalog_evaluation(
        ref, path, queries(), inputs=inputs(), registry=REGISTRY
    ).condition
    other_corpus = run_catalog_evaluation(
        ref,
        path,
        corpus(_case("x", "Status", "SYN_PsetA", "IfcWall")),
        inputs=inputs(),
        registry=REGISTRY,
    ).condition
    other_inputs = run_catalog_evaluation(
        ref, path, queries(), inputs=inputs(b"protocolo v2"), registry=REGISTRY
    ).condition
    content = f.resolution_content()
    changed = content.model_copy(
        update={
            "concepts": tuple(
                c.model_copy(update={"definition": f.pt("Outra.")}) for c in content.concepts
            )
        }
    )
    ref_b, path_b = f.write_synthetic_release(tmp_path / "relb", changed, version="1.1.0")
    other_release = run_catalog_evaluation(
        ref_b, path_b, queries(), inputs=inputs(), registry=REGISTRY
    ).condition

    hashes = {
        c.condition_sha256
        for c in (base, other_corpus, other_inputs, other_release)
        if c is not None
    }
    assert len(hashes) == 4


@pytest.mark.parametrize("variant", ["corpus", "inputs", "release"])
def test_expected_condition_mismatch_refuses_scoring(
    tmp_path: Path, release: tuple[CatalogReleaseRef, Path], variant: str
) -> None:
    ref, path = release
    expected = run_catalog_evaluation(
        ref, path, queries(), inputs=inputs(), registry=REGISTRY
    ).condition
    run_ref, run_path, run_corpus, run_inputs = ref, path, queries(), inputs()
    if variant == "corpus":
        run_corpus = corpus(_case("x", "Status", "SYN_PsetA", "IfcWall"))
    elif variant == "inputs":
        run_inputs = inputs(b"outra referencia")
    else:
        content = f.resolution_content()
        changed = content.model_copy(
            update={
                "concepts": tuple(
                    c.model_copy(update={"definition": f.pt("Outra.")}) for c in content.concepts
                )
            }
        )
        run_ref, run_path = f.write_synthetic_release(tmp_path / "relb", changed, version="1.1.0")

    with pytest.raises(EvaluationError) as error:
        run_catalog_evaluation(
            run_ref,
            run_path,
            run_corpus,
            inputs=run_inputs,
            registry=REGISTRY,
            expected_condition=expected,
        )
    assert error.value.code == "condition_mismatch"


def test_input_bytes_that_differ_from_declared_hash_are_refused(
    release: tuple[CatalogReleaseRef, Path],
) -> None:
    ref, path = release
    bad = inputs().model_copy(
        update={"artifacts": (inputs().artifacts[0].model_copy(update={"data": b"adulterado"}),)}
    )

    with pytest.raises(EvaluationError) as error:
        run_catalog_evaluation(ref, path, queries(), inputs=bad, registry=REGISTRY)
    assert error.value.code == "input_integrity"


def test_invalid_package_executes_nothing_and_reports_null_rates(
    release: tuple[CatalogReleaseRef, Path],
) -> None:
    ref, path = release
    wrong = ref.model_copy(update={"manifest_sha256": "0" * 64})
    report = run_catalog_evaluation(wrong, path, queries(), inputs=inputs(), registry=REGISTRY)

    assert report.run_status == "package_error"
    assert (report.executed_cases, report.not_executed_cases, report.package_open_errors) == (
        0,
        3,
        1,
    )
    assert report.results == ()
    assert report.condition is None
    assert report.summary.rates["resolved"].value is None
    assert report.package_error_reason
    assert "integrity" in report.package_error_reason
    assert report.attempt_sha256


def test_unexpected_error_propagates_as_technical_failure(
    monkeypatch: pytest.MonkeyPatch, release: tuple[CatalogReleaseRef, Path]
) -> None:
    ref, path = release

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("falha técnica simulada")

    monkeypatch.setattr(evaluation_module, "open_catalog", boom)
    with pytest.raises(RuntimeError, match="falha técnica"):
        run_catalog_evaluation(ref, path, queries(), inputs=inputs(), registry=REGISTRY)


def test_legacy_execution_condition_is_untouched() -> None:
    assert ExecutionProfile.model_fields["condition_id"].default == "m1-e3-evidence-v1"
    assert EVALUATION_CONDITION_ID == "m1-e4-catalog-eval-v1"


def test_benchmark_separates_new_opens_from_warm_queries(
    release: tuple[CatalogReleaseRef, Path],
) -> None:
    ref, path = release
    perf = benchmark_catalog_queries(
        ref, path, queries(), inputs=inputs(), registry=REGISTRY, repetitions=4, open_repetitions=2
    )

    assert perf.os_cache_control == "not_controlled"
    assert len(perf.open_samples_ns) == 2
    assert len(perf.query_samples) == 3
    assert all(
        len(sample.samples_ns) == 4 and sample.warmup_ns > 0 for sample in perf.query_samples
    )
    assert perf.peak_python_heap_bytes > 0
    assert perf.condition_sha256
    assert perf.environment["python"]
    assert not {f for f in perf.model_dump() if "sla" in f.lower() or "threshold" in f.lower()}


def test_benchmark_on_invalid_package_raises_typed_error(
    release: tuple[CatalogReleaseRef, Path],
) -> None:
    ref, path = release
    with pytest.raises(EvaluationError) as error:
        benchmark_catalog_queries(
            ref.model_copy(update={"manifest_sha256": "0" * 64}),
            path,
            queries(),
            inputs=inputs(),
            registry=REGISTRY,
            repetitions=1,
            open_repetitions=1,
        )
    assert error.value.code == "package_error"


@pytest.mark.external_data
def test_draft_profile_gets_documentary_coverage_only() -> None:
    appendix_a = import_appendix_a(load_matrix(MATRIX_PATH))
    appendix_b = load_appendix_b(APPENDIX_B_PATH, expected_pdf_sha256=PDF_SHA256)
    profile = build_daiane_profile(
        appendix_a,
        appendix_b,
        load_reconciliation(RECONCILIATION_PATH),
        load_candidates(CANDIDATES_PATH, appendix_a, appendix_b),
        capabilities=ProfileCapabilityEvidence(),
    )
    summary = summarize_profile_coverage(profile, summarize_daiane_profile(profile))

    assert summary.evaluation_mode == "documentary_coverage_only"
    assert summary.catalog_ref is None
    assert summary.draft_content_sha256 == profile.reconciliation.bases.candidates_content_sha256
    assert sum(sum(v.values()) for v in summary.by_family_destination.values()) == 589
    assert summary.curation_effort.human_duration == "not_measured"
    assert summary.curation_effort.recorded_actions["transcription_reviews"] == 3


def test_condition_changes_with_labels_and_reference(
    release: tuple[CatalogReleaseRef, Path],
) -> None:
    ref, path = release
    base = queries()
    relabeled = corpus(
        *[
            {**c.model_dump(mode="json"), "expectation": {"allowed_statuses": ["ambiguous"]}}
            if c.case_id == "ausente"
            else c.model_dump(mode="json")
            for c in base.cases
        ]
    )
    one = run_catalog_evaluation(ref, path, base, inputs=inputs(), registry=REGISTRY).condition
    two = run_catalog_evaluation(ref, path, relabeled, inputs=inputs(), registry=REGISTRY).condition

    assert one is not None
    assert two is not None
    assert one.condition_sha256 != two.condition_sha256
    with pytest.raises(EvaluationError) as error:
        run_catalog_evaluation(
            ref, path, relabeled, inputs=inputs(), registry=REGISTRY, expected_condition=one
        )
    assert error.value.code == "condition_mismatch"


def test_wrapper_verifies_the_reference_review_itself(
    release: tuple[CatalogReleaseRef, Path],
) -> None:
    from src.domain_catalog.evaluation import corpus_sha256, dedupe_corpus, labels_sha256
    from src.domain_catalog.evaluation_models import ReferenceReview

    ref, path = release
    real = corpus(
        {
            **_case("exato", "Status", "SYN_PsetA", "IfcWall"),
            "origin": "expert_reference",
            "expectation": {
                "allowed_statuses": ["exact"],
                "binding_id": "urn:uuid:00000000-0000-4000-8000-000000001040",
                "concept_id": "urn:uuid:00000000-0000-4000-8000-000000001020",
            },
        },
    )
    evidence = b"registro local"
    review = ReferenceReview.model_validate(
        {
            "format": "ifcqc-catalog-reference-review-1",
            "format_version": 1,
            "corpus_sha256": corpus_sha256(dedupe_corpus(real)),
            "labels_sha256": labels_sha256(real),
            "case_ids": ["exato"],
            "reviewer_declared": "Pessoa Revisora Sintética",
            "generator_declared": "gerador",
            "date": "2026-10-22",
            "method": "teste",
            "evidence_file": "rev.txt",
            "evidence_sha256": hashlib.sha256(evidence).hexdigest(),
            "status": "accepted",
        }
    )
    ok = run_catalog_evaluation(
        ref,
        path,
        real,
        inputs=inputs(),
        registry=REGISTRY,
        reference_review=review,
        reference_evidence={"rev.txt": evidence},
    )
    tampered = run_catalog_evaluation(
        ref,
        path,
        real,
        inputs=inputs(),
        registry=REGISTRY,
        reference_review=review,
        reference_evidence={"rev.txt": b"outro"},
    )

    assert ok.summary.domain_quality == "declared_reference_agreement"
    assert ok.condition is not None
    assert ok.condition.reference_review_sha256
    assert tampered.summary.domain_quality == "not_measured"
    assert tampered.condition is not None
    assert tampered.condition.condition_sha256 != ok.condition.condition_sha256


# --- Retomada 23/10: condição do benchmark, tracemalloc externo, runtime medido -----------


def test_benchmark_accepts_the_matching_condition(
    release: tuple[CatalogReleaseRef, Path],
) -> None:
    ref, path = release
    expected = run_catalog_evaluation(
        ref, path, queries(), inputs=inputs(), registry=REGISTRY
    ).condition
    assert expected is not None
    perf = benchmark_catalog_queries(
        ref,
        path,
        queries(),
        inputs=inputs(),
        registry=REGISTRY,
        repetitions=1,
        open_repetitions=1,
        expected_condition=expected,
    )

    assert perf.condition_sha256 == expected.condition_sha256


@pytest.mark.parametrize("variant", ["corpus", "inputs"])
def test_benchmark_with_divergent_condition_measures_nothing(
    monkeypatch: pytest.MonkeyPatch, release: tuple[CatalogReleaseRef, Path], variant: str
) -> None:
    """M20: condição esperada divergente é recusada antes de medir consultas."""
    ref, path = release
    expected = run_catalog_evaluation(
        ref, path, queries(), inputs=inputs(), registry=REGISTRY
    ).condition
    run_corpus = (
        corpus(_case("x", "Status", "SYN_PsetA", "IfcWall")) if variant == "corpus" else queries()
    )
    run_inputs = inputs(b"outra referencia") if variant == "inputs" else inputs()
    resolved: list[object] = []
    real_resolve = evaluation_module.CatalogReader.resolve_binding

    def counting(self: Any, request: Any) -> Any:
        resolved.append(request)
        return real_resolve(self, request)

    monkeypatch.setattr(evaluation_module.CatalogReader, "resolve_binding", counting)
    with pytest.raises(EvaluationError) as error:
        benchmark_catalog_queries(
            ref,
            path,
            run_corpus,
            inputs=run_inputs,
            registry=REGISTRY,
            repetitions=2,
            open_repetitions=1,
            expected_condition=expected,
        )
    assert error.value.code == "condition_mismatch"
    assert resolved == []


def test_benchmark_keeps_an_outer_tracemalloc_trace(
    release: tuple[CatalogReleaseRef, Path],
) -> None:
    """M20: rastreamento iniciado por quem chama continua ativo depois da medição."""
    import tracemalloc

    ref, path = release
    tracemalloc.start()
    try:
        perf = benchmark_catalog_queries(
            ref,
            path,
            queries(),
            inputs=inputs(),
            registry=REGISTRY,
            repetitions=1,
            open_repetitions=1,
        )
        assert tracemalloc.is_tracing()
        assert perf.peak_python_heap_bytes > 0
    finally:
        tracemalloc.stop()


def test_benchmark_started_without_trace_leaves_none_running(
    release: tuple[CatalogReleaseRef, Path],
) -> None:
    import tracemalloc

    ref, path = release
    assert not tracemalloc.is_tracing()
    benchmark_catalog_queries(
        ref, path, queries(), inputs=inputs(), registry=REGISTRY, repetitions=1, open_repetitions=1
    )
    assert not tracemalloc.is_tracing()


def test_condition_records_the_measured_interpreter_besides_the_declared_runtime(
    release: tuple[CatalogReleaseRef, Path],
) -> None:
    """M21: Python/dependência medidos no processo, separados do runtime declarado."""
    import platform
    from importlib.metadata import version

    ref, path = release
    condition = run_catalog_evaluation(
        ref, path, queries(), inputs=inputs(), registry=REGISTRY
    ).condition
    assert condition is not None

    assert condition.measured_runtime == {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "pydantic": version("pydantic"),
    }
    assert sorted(condition.code_sha256) == ["evaluation", "reader", "resolver"]
