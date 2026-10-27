"""Avaliação E4, parte pura: deduplicação, agregador, denominadores e referência (M1-15).

Tudo SINTÉTICO. O agregador de seis estados é ensaio aritmético de
``score_catalog_results``; não representa seis consultas a um pacote quebrado (isso
fica no teste de integração). Nome declarado não autentica pessoa: a referência só
habilita "concordância com referência humana declarada", nunca qualidade aceita.
"""

import hashlib
from typing import Any

import pytest

from src.domain_catalog.contracts import BindingRequest
from src.domain_catalog.evaluation import (
    EvaluationError,
    corpus_sha256,
    dedupe_corpus,
    labels_sha256,
    load_reference_review,
    nearest_rank_p95,
    score_catalog_results,
)
from src.domain_catalog.evaluation_models import (
    CatalogCaseResult,
    CatalogEvaluationCorpus,
    ReferenceEligibility,
    ReferenceReview,
)

B1 = "urn:uuid:00000000-0000-4000-8000-000000000101"
B2 = "urn:uuid:00000000-0000-4000-8000-000000000102"
C1 = "urn:uuid:00000000-0000-4000-8000-000000000201"
C2 = "urn:uuid:00000000-0000-4000-8000-000000000202"


def case(
    case_id: str,
    field: str,
    *,
    split: str = "evaluation",
    origin: str = "synthetic",
    expectation: dict[str, Any] | None = None,
    exclusion_reason: str | None = None,
    **request: Any,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "case_id": case_id,
        "request": {
            "ifc_schema": "IFC4",
            "facet": "property",
            "set_name": "SYN_Conjunto",
            "field_name": field,
            "entity": "IfcSlab",
            **request,
        },
        "origin": origin,
        "stratum": "propriedade",
        "family": "SYN",
        "facet": "property",
        "split": split,
        "source_refs": [f"synthetic:{case_id}"],
    }
    if expectation is not None:
        data["expectation"] = expectation
    if exclusion_reason is not None:
        data["exclusion_reason"] = exclusion_reason
    return data


def corpus(*cases: dict[str, Any]) -> CatalogEvaluationCorpus:
    return CatalogEvaluationCorpus.model_validate(
        {
            "format": "ifcqc-catalog-evaluation-1",
            "format_version": 1,
            "corpus_id": "syn-corpus",
            "generated_by": "teste automatizado (gerador sintético)",
            "generation_method": "casos escritos à mão no teste",
            "cases": list(cases),
        }
    )


def result(
    key: str,
    status: str,
    case_ids: tuple[str, ...],
    binding: str | None = None,
    concept: str | None = None,
) -> CatalogCaseResult:
    return CatalogCaseResult(
        query_key=key, case_ids=case_ids, status=status, binding_id=binding, concept_id=concept
    )


# --- Deduplicação e split -------------------------------------------------------------


def test_semantic_duplicates_aggregate_provenance_and_do_not_inflate_corpus() -> None:
    dedup = dedupe_corpus(
        corpus(
            case("c1", "Metodo", requirement_ref="IDS-1"),
            case("c2", "Metodo", requirement_ref="IDS-2"),
            case("c3", "Outro"),
        )
    )

    assert (dedup.total_cases, dedup.total_unique, dedup.included) == (3, 2, 2)
    merged = next(q for q in dedup.queries if "c1" in q.case_ids)
    assert merged.case_ids == ("c1", "c2")
    assert merged.source_refs == ("synthetic:c1", "synthetic:c2")
    assert "requirement_ref" not in merged.query_key


def test_duplicate_case_id_is_an_input_error() -> None:
    with pytest.raises(EvaluationError) as error:
        dedupe_corpus(corpus(case("c1", "A"), case("c1", "B")))
    assert error.value.code == "duplicate_case_id"


def test_same_query_in_development_and_evaluation_is_split_leakage() -> None:
    with pytest.raises(EvaluationError) as error:
        dedupe_corpus(corpus(case("c1", "A", split="development"), case("c2", "A")))
    assert error.value.code == "split_leakage"


def test_conflicting_references_for_the_same_query_are_flagged() -> None:
    dedup = dedupe_corpus(
        corpus(
            case(
                "c1",
                "A",
                expectation={"allowed_statuses": ["exact"], "binding_id": B1, "concept_id": C1},
            ),
            case("c2", "A", expectation={"allowed_statuses": ["unmapped"]}),
        )
    )

    assert dedup.queries[0].reference_conflict is True
    assert dedup.conflicts == (dedup.queries[0].query_key,)


def test_excluded_cases_are_explicit_with_reason() -> None:
    dedup = dedupe_corpus(
        corpus(case("c1", "A"), case("c2", "B", exclusion_reason="fora do recorte IFC4"))
    )

    assert (dedup.included, dedup.excluded) == (1, 1)
    assert dedup.excluded_cases == (("c2", "fora do recorte IFC4"),)


# --- Agregador puro: seis estados -------------------------------------------------------


def six_state_fixture() -> tuple[list[CatalogCaseResult], CatalogEvaluationCorpus]:
    exp_b1 = {"allowed_statuses": ["exact"], "binding_id": B1, "concept_id": C1}
    exp_b2 = {"allowed_statuses": ["exact"], "binding_id": B2, "concept_id": C2}
    cases = corpus(
        case("ok", "A", expectation=exp_b1),
        case("falso", "B", expectation=exp_b2),
        case("amb", "C", expectation={"allowed_statuses": ["ambiguous"]}),
        case("unm", "D", expectation={"allowed_statuses": ["unmapped"]}),
        case("uns", "E", expectation={"allowed_statuses": ["unsupported"]}),
        case(
            "pkg",
            "F",
            expectation={"allowed_statuses": ["exact"], "binding_id": B1, "concept_id": C1},
        ),
    )
    keys = {q.case_ids[0]: q.query_key for q in dedupe_corpus(cases).queries}
    results = [
        result(keys["ok"], "exact", ("ok",), B1, C1),
        result(keys["falso"], "exact", ("falso",), B1, C1),
        result(keys["amb"], "ambiguous", ("amb",)),
        result(keys["unm"], "unmapped", ("unm",)),
        result(keys["uns"], "unsupported", ("uns",)),
        result(keys["pkg"], "package_error", ("pkg",)),
    ]
    return results, cases


def test_six_states_are_counted_separately() -> None:
    results, cases = six_state_fixture()
    summary = score_catalog_results(results, corpus=cases)

    assert summary.result_count == 6
    assert (summary.resolved, summary.abstentions, summary.errors) == (2, 3, 1)
    assert summary.by_status == {
        "ambiguous": 1,
        "approved_mapping": 0,
        "exact": 1 + 1,
        "package_error": 1,
        "unmapped": 1,
        "unsupported": 1,
    }
    assert summary.rates["resolved"].value == pytest.approx(2 / 6)
    assert summary.rates["resolved"].denominator == 6
    assert summary.denominator_label == "resultados fornecidos ao agregador (fixture)"


def test_quality_on_synthetic_reference_counts_false_mapping_and_stays_labeled() -> None:
    results, cases = six_state_fixture()
    summary = score_catalog_results(results, corpus=cases)
    quality = summary.quality

    assert quality.block == "synthetic_reference"
    assert quality.false_mapping == 1
    assert quality.mapping_precision.value == pytest.approx(1 / 2)
    assert quality.mapping_recall.value == pytest.approx(1 / 3)
    assert quality.status_accuracy.value == pytest.approx(5 / 6)
    assert summary.domain_quality == "not_measured"


def test_resolving_where_reference_requires_abstention_is_false_mapping() -> None:
    cases = corpus(case("x", "A", expectation={"allowed_statuses": ["unmapped"]}))
    key = dedupe_corpus(cases).queries[0].query_key
    summary = score_catalog_results([result(key, "exact", ("x",), B1, C1)], corpus=cases)

    assert summary.quality.false_mapping == 1
    assert summary.quality.mapping_precision.value == 0.0


def test_zero_denominators_are_null_with_reason_never_100_percent() -> None:
    cases = corpus(case("x", "A"))
    summary = score_catalog_results([], corpus=cases)

    assert summary.rates["resolved"].value is None
    assert summary.rates["resolved"].reason
    assert summary.quality.block == "not_measured"
    assert summary.quality.mapping_precision.value is None
    assert summary.quality.mapping_precision.reason


def test_cases_without_reference_never_count_as_hits() -> None:
    cases = corpus(case("x", "A"))
    key = dedupe_corpus(cases).queries[0].query_key
    summary = score_catalog_results([result(key, "exact", ("x",), B1, C1)], corpus=cases)

    assert summary.quality.eligible_cases == 0
    assert summary.quality.mapping_precision.value is None


def test_conflicting_reference_blocks_quality_for_that_query() -> None:
    cases = corpus(
        case(
            "c1",
            "A",
            expectation={"allowed_statuses": ["exact"], "binding_id": B1, "concept_id": C1},
        ),
        case("c2", "A", expectation={"allowed_statuses": ["unmapped"]}),
    )
    key = dedupe_corpus(cases).queries[0].query_key
    summary = score_catalog_results([result(key, "exact", ("c1", "c2"), B1, C1)], corpus=cases)

    assert summary.quality.eligible_cases == 0
    assert summary.quality.blocked_by_conflict == 1


def test_nearest_rank_p95() -> None:
    assert nearest_rank_p95([5, 1, 4, 2, 3]) == 5
    assert nearest_rank_p95(list(range(1, 21))) == 19
    assert nearest_rank_p95([]) is None


# --- Referência humana declarada ---------------------------------------------------------


def review(cases: CatalogEvaluationCorpus, evidence: bytes, **changes: Any) -> ReferenceReview:
    data: dict[str, Any] = {
        "format": "ifcqc-catalog-reference-review-1",
        "format_version": 1,
        "corpus_sha256": corpus_sha256(dedupe_corpus(cases)),
        "labels_sha256": labels_sha256(cases),
        "case_ids": [c.case_id for c in cases.cases],
        "reviewer_declared": "Pessoa Revisora Sintética",
        "generator_declared": "teste automatizado (gerador sintético)",
        "date": "2026-10-22",
        "method": "revisão sintética de teste",
        "evidence_file": "revisao.txt",
        "evidence_sha256": hashlib.sha256(evidence).hexdigest(),
        "status": "accepted",
    }
    data.update(changes)
    return ReferenceReview.model_validate(data)


def labeled(origin: str = "expert_reference", split: str = "evaluation") -> CatalogEvaluationCorpus:
    return corpus(
        case(
            "r1",
            "A",
            origin=origin,
            split=split,
            expectation={"allowed_statuses": ["exact"], "binding_id": B1, "concept_id": C1},
        )
    )


def test_eligible_reference_only_authorizes_declared_agreement() -> None:
    cases, evidence = labeled(), b"registro local da revisao"
    eligibility = load_reference_review(
        review(cases, evidence), cases, evidence={"revisao.txt": evidence}
    )

    assert eligibility.eligible_case_ids == ("r1",)
    assert eligibility.block == "declared_reference_agreement"
    assert eligibility.identity_assurance == "unverified_local"


@pytest.mark.parametrize(
    ("changes", "evidence_map", "reason"),
    [
        ({}, {}, "evidência"),
        ({"evidence_sha256": "0" * 64}, None, "evidência"),
        ({"status": "pending"}, None, "status"),
        ({"reviewer_declared": "teste automatizado (gerador sintético)"}, None, "gerador"),
        ({"labels_sha256": "0" * 64}, None, "rótulos"),
        ({"corpus_sha256": "0" * 64}, None, "corpus"),
        ({"case_ids": ["r1", "r9"]}, None, "casos"),
    ],
)
def test_reference_is_ineligible_when_any_check_fails(
    changes: dict[str, Any], evidence_map: dict[str, bytes] | None, reason: str
) -> None:
    cases, evidence = labeled(), b"registro local da revisao"
    eligibility = load_reference_review(
        review(cases, evidence, **changes),
        cases,
        evidence={"revisao.txt": evidence} if evidence_map is None else evidence_map,
    )

    assert eligibility.eligible_case_ids == ()
    assert eligibility.block == "not_measured"
    assert any(reason in item for item in eligibility.reasons)


def test_accepted_flag_alone_never_enables_domain_quality_for_synthetic_or_development() -> None:
    evidence = b"registro"
    for cases in (labeled(origin="synthetic"), labeled(split="development")):
        eligibility = load_reference_review(
            review(cases, evidence), cases, evidence={"revisao.txt": evidence}
        )
        assert eligibility.eligible_case_ids == ()


def test_declared_reference_quality_is_reported_as_agreement_not_acceptance() -> None:
    cases, evidence = labeled(), b"registro"
    eligibility = load_reference_review(
        review(cases, evidence), cases, evidence={"revisao.txt": evidence}
    )
    key = dedupe_corpus(cases).queries[0].query_key
    summary = score_catalog_results(
        [result(key, "exact", ("r1",), B1, C1)], corpus=cases, reference=eligibility
    )

    assert summary.quality.block == "declared_reference_agreement"
    assert summary.domain_quality == "declared_reference_agreement"
    assert summary.quality.mapping_precision.value == 1.0


def test_request_model_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        BindingRequest.model_validate(
            {"ifc_schema": "IFC4", "facet": "property", "field_name": "A", "extra": 1}
        )


# --- Correções da revisão independente final (I1–I6) ------------------------------------


def test_fabricated_eligibility_is_refused_and_synthetic_never_counts_as_agreement() -> None:
    cases = corpus(
        case(
            "e",
            "A",
            expectation={"allowed_statuses": ["exact"], "binding_id": B1, "concept_id": C1},
        )
    )
    key = dedupe_corpus(cases).queries[0].query_key
    made_up = ReferenceEligibility(
        eligible_case_ids=("e",),
        block="declared_reference_agreement",
        corpus_sha256="0" * 64,
        labels_sha256="0" * 64,
        review_sha256="0" * 64,
    )
    with pytest.raises(EvaluationError) as error:
        score_catalog_results(
            [result(key, "exact", ("e",), B1, C1)], corpus=cases, reference=made_up
        )
    assert error.value.code == "reference_mismatch"

    bound = made_up.model_copy(
        update={
            "corpus_sha256": corpus_sha256(dedupe_corpus(cases)),
            "labels_sha256": labels_sha256(cases),
        }
    )
    summary = score_catalog_results(
        [result(key, "exact", ("e",), B1, C1)], corpus=cases, reference=bound
    )
    assert summary.domain_quality == "not_measured"
    assert summary.quality.eligible_cases == 0


def test_case_record_change_after_review_is_detected() -> None:
    cases, evidence = labeled(origin="synthetic"), b"registro"
    reviewed = review(cases, evidence)
    flipped = corpus(
        case(
            "r1",
            "A",
            origin="expert_reference",
            expectation={"allowed_statuses": ["exact"], "binding_id": B1, "concept_id": C1},
        )
    )
    eligibility = load_reference_review(reviewed, flipped, evidence={"revisao.txt": evidence})

    assert eligibility.eligible_case_ids == ()
    assert any("rótulos" in reason for reason in eligibility.reasons)


def test_strata_count_unique_queries_and_list_shared_ones() -> None:
    cases = corpus(
        case("a", "A"),
        {**case("b", "A"), "stratum": "outro"},
        {**case("c", "A"), "stratum": "propriedade"},
        case("d", "B"),
    )
    dedup = dedupe_corpus(cases)

    assert dedup.strata == {"propriedade": 1}
    assert dedup.strata_only_in_shared_queries == ("outro",)
    assert len(dedup.multi_stratum_queries) == 1


def test_mixed_synthetic_and_real_corpus_is_refused() -> None:
    cases = corpus(case("s", "A"), case("r", "B", origin="daiane_source"))

    with pytest.raises(EvaluationError) as error:
        score_catalog_results([], corpus=cases)
    assert error.value.code == "mixed_origins"


def test_excluded_case_label_is_not_scored() -> None:
    cases = corpus(
        case("in", "A"),
        case(
            "out",
            "A",
            exclusion_reason="fora do recorte",
            expectation={"allowed_statuses": ["exact"], "binding_id": B2, "concept_id": C2},
        ),
    )
    key = dedupe_corpus(cases).queries[0].query_key
    summary = score_catalog_results([result(key, "exact", ("in", "out"), B1, C1)], corpus=cases)

    assert summary.quality.eligible_cases == 0
    assert summary.quality.false_mapping == 0


def test_reviewer_equal_to_generator_modulo_whitespace_and_case_is_refused() -> None:
    cases, evidence = labeled(), b"registro"
    eligibility = load_reference_review(
        review(cases, evidence, reviewer_declared="  TESTE automatizado   (gerador sintético) "),
        cases,
        evidence={"revisao.txt": evidence},
    )

    assert eligibility.eligible_case_ids == ()
    assert any("gerador" in reason for reason in eligibility.reasons)
