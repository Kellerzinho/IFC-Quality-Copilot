"""Testes para grounding compacto (prepare_llm_grounding)."""

from __future__ import annotations

from src.models import (
    BSDDClassification,
    BSDDContext,
    BSDDProperty,
    IDSContext,
    Issue,
)
from src.suggestion_engine.grounding import (
    GroundedIssueContext,
    prepare_llm_grounding,
)
from src.suggestion_engine.prompt_templates import build_compact_prompt


def _wall_issue() -> Issue:
    return Issue(
        element_guid="W" * 22,
        element_class="IfcWall",
        element_name="Parede externa",
        issue_type="pset_missing",
        severity="high",
        description="ThermalTransmittance ausente",
        context={
            "check_pset": "Pset_WallCommon",
            "check_property": "ThermalTransmittance",
            "current_value": None,
        },
    )


def test_prepare_grounding_without_sources_is_unground():
    g = prepare_llm_grounding(_wall_issue(), ids_context=None, bsdd_context=None)
    assert isinstance(g, GroundedIssueContext)
    assert g.is_grounded is False
    assert g.has_official_candidates is False
    assert g.requirement_summary is None


def test_prepare_grounding_with_ids_context():
    ids = IDSContext(
        spec_name="NBR15575",
        requirement_description="Pset_WallCommon.ThermalTransmittance must exist and be numeric",
        check_type="is_numeric",
        expected_pset="Pset_WallCommon",
        expected_property="ThermalTransmittance",
        expected_value=None,
        expected_unit="W/(m²·K)",
        severity="high",
        requirement_id="rule-1",
    )
    g = prepare_llm_grounding(_wall_issue(), ids_context=ids, bsdd_context=None)
    assert "ids" in g.grounding_sources
    assert g.canonical_pset == "Pset_WallCommon"
    assert g.canonical_property == "ThermalTransmittance"
    assert g.expected_unit == "W/(m²·K)"
    assert g.requirement_id == "rule-1"
    assert g.requirement_summary is not None


def test_prepare_grounding_with_bsdd_extracts_candidates():
    bsdd = BSDDContext(
        class_name="Wall",
        related_properties=[
            BSDDProperty(
                name="ThermalTransmittance",
                data_type="Real",
                unit="W/(m²·K)",
                allowed_values=["1.8", "2.5", "3.0"],
            )
        ],
        classification_suggestions=[BSDDClassification(name="Wall")],
        source_status="live",
    )
    g = prepare_llm_grounding(_wall_issue(), ids_context=None, bsdd_context=bsdd)
    assert "bsdd" in g.grounding_sources
    assert g.expected_datatype == "Real"
    assert "1.8" in g.official_candidates
    assert g.has_official_candidates


def test_compact_prompt_omits_uri_and_normative_text():
    """Prompt compacto não pede URI e não inclui textos normativos longos."""
    ids = IDSContext(
        spec_name="NBR15575",
        requirement_description="ThermalTransmittance must exist",
        check_type="is_numeric",
        expected_pset="Pset_WallCommon",
        expected_property="ThermalTransmittance",
        expected_unit="W/(m²·K)",
        severity="high",
        requirement_id="rule-1",
    )
    g = prepare_llm_grounding(_wall_issue(), ids_context=ids, bsdd_context=None)
    system, user = build_compact_prompt(g)
    assert "URI" not in system
    assert "URI" not in user.upper() or "NAO RETORNE URI" in user.upper().replace("Ã", "A")
    assert "NBR 15575" not in user  # texto normativo extenso não está
    assert "issue_id" in user
    assert "ThermalTransmittance" in user


def test_compact_prompt_marks_review_required_when_no_candidates():
    g = prepare_llm_grounding(_wall_issue(), ids_context=None, bsdd_context=None)
    _, user = build_compact_prompt(g)
    assert "review_required" in user
