"""Validação pura de um valor candidato contra o esperado IDS (A21), sem IFC fictício."""

import pytest

pytest.importorskip("xmlschema", reason="extra e3 não instalado (xmlschema==4.3.2)")

from src.ifc_analyzer.observations import BooleanValue, IntegerValue, TextValue
from src.translator.ids_document import parse_ids_document
from src.validation.analysis_identity import current_execution_profile
from src.validation.candidate_validation import validate_candidate
from src.validation.diagnostic_models import ExpectedField
from src.validation.ids_engine import expected_field
from tests.validation import ids_builders as x
from tests.validation.engine_helpers import bundle


def _expected(requirement: str) -> ExpectedField:
    document = parse_ids_document(x.ids(x.spec("S", x.entity("IFCWALL"), requirement)), bundle())
    return expected_field(document.specifications[0].requirements[0])


VERIFIER = current_execution_profile().verifier


@pytest.mark.parametrize(
    ("requirement", "candidate", "status"),
    [
        (x.prop("P", "A"), TextValue(value="qualquer"), "satisfied"),
        (x.prop("P", "A"), TextValue(value="  "), "satisfied"),
        (x.prop("P", "A"), TextValue(value=""), "violates"),
        (x.prop("P", "A", value=x.simple("Café")), TextValue(value="Café"), "satisfied"),
        (x.prop("P", "A", value=x.simple("Café")), TextValue(value="Café"), "violates"),
        (x.prop("P", "A", value=x.simple("Café")), TextValue(value="café"), "violates"),
        (x.prop("P", "A", value=x.enum("A", "B")), TextValue(value="B"), "satisfied"),
        (x.prop("P", "A", value=x.enum("A", "B")), TextValue(value="b"), "violates"),
        (x.prop("P", "A", value=x.enum("A", "B")), TextValue(value=" B"), "violates"),
        (x.prop("P", "A", cardinality="optional"), TextValue(value="x"), "satisfied"),
        (x.prop("P", "A", data_type="IFCIDENTIFIER"), TextValue(value="ID-1"), "satisfied"),
        (x.prop("P", "A", cardinality="prohibited"), TextValue(value="x"), "unsupported"),
        (x.prop("P", "A", value=x.simple("")), TextValue(value=""), "unsupported"),
        (x.prop("P", "A", value=x.pattern("A.*")), TextValue(value="AB"), "unsupported"),
        (x.prop("P", "A", data_type="IFCBOOLEAN"), BooleanValue(value=True), "unsupported"),
        (x.prop("P", "A", data_type="IFCINTEGER"), IntegerValue(value=1), "unsupported"),
        (x.prop("P", "A"), IntegerValue(value=1), "unsupported"),
        (x.prop("P", "A", data_type="IFCLENGTHMEASURE"), TextValue(value="1"), "unsupported"),
        (x.prop("P", "A", data_type=None), TextValue(value="x"), "unsupported"),
        (x.attribute("Name"), TextValue(value="x"), "unsupported"),
    ],
)
def test_candidate_validation_is_strict_and_independent(
    requirement: str, candidate: object, status: str
) -> None:
    result = validate_candidate(_expected(requirement), candidate, VERIFIER)  # type: ignore[arg-type]
    assert result.status == status
    assert result.verifier_capability_sha256 == VERIFIER.capability_manifest_sha256
    if status != "satisfied":
        assert result.reasons


def test_candidate_validation_cites_the_exact_rule() -> None:
    expected = _expected(x.prop("P", "A", value=x.enum("A", "B")))
    result = validate_candidate(expected, TextValue(value="A"), VERIFIER)
    assert result.rule_refs == (expected.requirement.key(), expected.fragment_sha256)
    assert result.capability_id == "candidate:text:enumeration"


def test_incoherent_expected_is_error_not_satisfied() -> None:
    expected = _expected(x.prop("P", "A"))
    broken = expected.model_copy(update={"field_name": None})
    result = validate_candidate(broken, TextValue(value="x"), VERIFIER)
    assert result.status == "error"
