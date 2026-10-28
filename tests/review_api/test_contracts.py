"""Contratos de transporte M4: identidade, valores tipados e provisórios."""

import pytest
from pydantic import TypeAdapter, ValidationError

from src.review_api.schemas import (
    PROVISIONAL_STATUS,
    AbstainedSuggestion,
    ElementRef,
    Gap,
    GapRequirement,
    ModelPairBinding,
    ObservedValue,
    ProposedValue,
    SourceArtifactRef,
    Suggestion,
)

REV_A = "a" * 64
REV_B = "b" * 64
FIELD = {
    "element": {"model_id": "m1", "ifc_revision_id": REV_A, "express_id": 10},
    "property_set": "Pset_WallCommon",
    "property_name": "FireRating",
}
SUGGESTIONS = TypeAdapter(Suggestion)


@pytest.mark.parametrize(
    "extra",
    [
        {"value": "EI 60"},
        {"value": None},
        {"alternatives": [{"alternative_id": "x"}]},
    ],
)
def test_abstention_never_carries_value(extra: dict) -> None:
    payload = {"outcome": "abstained", "field": FIELD, "reason": "sem evidência", **extra}
    with pytest.raises(ValidationError):
        SUGGESTIONS.validate_python(payload)
    with pytest.raises(ValidationError):
        AbstainedSuggestion.model_validate(payload)


def test_abstention_is_provisional_and_valueless() -> None:
    parsed = SUGGESTIONS.validate_python(
        {"outcome": "abstained", "field": FIELD, "reason": "sem evidência"}
    )
    assert isinstance(parsed, AbstainedSuggestion)
    assert parsed.schema_status == PROVISIONAL_STATUS
    assert "value" not in parsed.model_dump()


def test_proposal_requires_at_least_one_alternative() -> None:
    with pytest.raises(ValidationError):
        SUGGESTIONS.validate_python({"outcome": "proposed", "field": FIELD, "alternatives": []})


@pytest.mark.parametrize("text", ["A definir", " a DEFINIR "])
def test_placeholder_text_is_not_a_proposed_value(text: str) -> None:
    with pytest.raises(ValidationError):
        ProposedValue(kind="string", value=text)


@pytest.mark.parametrize(
    ("kind", "value"),
    [("integer", 0), ("real", 0.0), ("boolean", False), ("string", "0")],
)
def test_zero_false_and_text_survive_json_roundtrip(kind: str, value: object) -> None:
    """T4-26: zero e FALSE continuam valores, com o tipo preservado."""
    observed = ObservedValue(state="present", kind=kind, value=value)
    back = ObservedValue.model_validate_json(observed.model_dump_json())
    assert back.value == value
    assert type(back.value) is type(value)


def test_empty_string_is_distinct_from_absent() -> None:
    empty = ObservedValue(state="empty", kind="string", value="")
    assert empty.value == ""
    with pytest.raises(ValidationError):
        ObservedValue(state="property_absent", value="")
    with pytest.raises(ValidationError):
        ObservedValue(state="present", kind="string", value=None)


def test_element_ref_key_is_not_the_global_id() -> None:
    a = ElementRef(model_id="arq", ifc_revision_id=REV_A, express_id=7)
    b = ElementRef(model_id="est", ifc_revision_id=REV_B, express_id=7)
    assert a != b
    assert a.key == f"arq:{REV_A}:7"
    assert "global_id" not in ElementRef.model_fields


def test_ambiguous_gap_cannot_choose_an_element() -> None:
    requirement = GapRequirement(
        property_set="P", property_name="X", check="exists", specification="s"
    )
    candidates = [
        ElementRef(model_id="arq", ifc_revision_id=REV_A, express_id=i) for i in (1, 2)
    ]
    with pytest.raises(ValidationError):
        Gap(
            gap_id="g",
            origin="legacy_ifc_analyzer",
            resolution="ambiguous",
            element=candidates[0],
            candidates=candidates,
            ifc_class="IfcWindow",
            requirement=requirement,
        )
    gap = Gap(
        gap_id="g",
        origin="legacy_ifc_analyzer",
        resolution="ambiguous",
        candidates=candidates,
        ifc_class="IfcWindow",
        requirement=requirement,
    )
    assert gap.schema_status == PROVISIONAL_STATUS


def test_binding_confirmation_must_match_current_revisions() -> None:
    ifc = SourceArtifactRef(role="ifc", revision_id=REV_A, size_bytes=1, display_name="a.ifc")
    ids = SourceArtifactRef(role="ids", revision_id=REV_B, size_bytes=1, display_name="a.ids")
    base = {
        "project_id": "p", "model_id": "m", "discipline": "architecture", "ifc": ifc, "ids": ids
    }
    with pytest.raises(ValidationError):
        ModelPairBinding(
            **base, confirmed=True, confirmed_ifc_revision_id=REV_B, confirmed_ids_revision_id=REV_B
        )
    ok = ModelPairBinding(
        **base, confirmed=True, confirmed_ifc_revision_id=REV_A, confirmed_ids_revision_id=REV_B
    )
    assert ok.confirmed
