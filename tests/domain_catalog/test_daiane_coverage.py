"""Relatório do perfil E4: inventário coberto ≠ perfil aceito ≠ perfil operacional (M1-04).

Usa os artefatos REAIS da E4. Os denominadores esperados vêm da contagem visual do
Apêndice B (registrada na transcrição) e da tabela M3 do Apêndice A, não do código.
"""

import pytest

from src.domain_catalog.importers.daiane import MATRIX_PATH, import_appendix_a, load_matrix
from src.domain_catalog.importers.daiane_b import APPENDIX_B_PATH, load_appendix_b
from src.domain_catalog.profile import (
    CANDIDATES_PATH,
    PDF_SHA256,
    RECONCILIATION_PATH,
    build_daiane_profile,
    load_candidates,
    load_reconciliation,
    summarize_daiane_profile,
)
from src.domain_catalog.profile_models import ProfileCapabilityEvidence, ProfileReport


@pytest.fixture(scope="module")
def report() -> ProfileReport:
    appendix_a = import_appendix_a(load_matrix(MATRIX_PATH))
    appendix_b = load_appendix_b(APPENDIX_B_PATH, expected_pdf_sha256=PDF_SHA256)
    profile = build_daiane_profile(
        appendix_a,
        appendix_b,
        load_reconciliation(RECONCILIATION_PATH),
        load_candidates(CANDIDATES_PATH, appendix_a, appendix_b),
        capabilities=ProfileCapabilityEvidence(),
    )
    return summarize_daiane_profile(profile)


@pytest.mark.external_data
def test_inventory_is_accounted_for_but_domain_is_not_accepted(report: ProfileReport) -> None:
    assert report.inventory_accounted_for is True
    assert report.appendix_b_transcription_complete is True
    assert report.appendix_b_research_checked is True
    assert report.appendix_b_check_level == "assistant_only"
    assert report.domain_review_complete is False
    assert report.original_instrument_equivalence_verified is False
    assert report.profile_operational is False
    assert report.human_gates


@pytest.mark.external_data
def test_denominators_are_separate_and_closed(report: ProfileReport) -> None:
    assert (report.a_total, report.a_alphanumeric, report.a_auxiliary) == (313, 203, 110)
    assert report.b_total == 276
    assert report.b_by_role == {
        "applicability": 10,
        "requirement": 184,
        "specification_metadata": 82,
    }
    assert sum(report.by_destination["A"].values()) == 313
    assert sum(report.by_destination["B"].values()) == 276
    assert sum(sum(v.values()) for v in report.by_family_destination.values()) == 589


@pytest.mark.external_data
def test_matrix_findings_and_historical_counts_are_not_summed(report: ProfileReport) -> None:
    labels = {c.value: c for c in report.historical_counts}

    assert (report.matrix_divergence_items, report.matrix_divergence_records) == (147, 112)
    assert report.divergences["matrix_finding"] == 147
    assert report.divergences["ab_comparison"] >= 1
    assert (
        labels["34"].status == labels["195/88"].status == labels["133"].status == "not_reconciled"
    )


@pytest.mark.external_data
def test_capability_axes_are_not_evaluated_without_evidence(report: ProfileReport) -> None:
    assert report.verified_capabilities == ()
    assert set(report.by_axis["validation"]) <= {"not_evaluated", "unsupported"}
    assert set(report.by_axis["enrichment"]) <= {"not_evaluated", "unsupported"}
    assert set(report.by_axis["catalog"]) == {"candidate_draft", "not_registered", "outside_scope"}


@pytest.mark.external_data
def test_every_pending_has_a_localized_reason_code(report: ProfileReport) -> None:
    assert "pending" not in report.pending_by_reason
    assert sum(report.pending_by_reason.values()) == (
        report.by_destination["A"].get("pending", 0) + report.by_destination["B"].get("pending", 0)
    )
    assert report.correspondences_by_review_state == {
        "assistant_proposal": sum(report.correspondences_by_relation.values())
    }
