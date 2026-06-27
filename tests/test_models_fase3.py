from src.models import (
    AuditEntry,
    BSDDClassification,
    BSDDContext,
    BSDDProperty,
    Suggestion,
    ValidationResult,
)


def test_bsdd_property_creation_and_serialization() -> None:
    prop = BSDDProperty(
        name="ThermalTransmittance",
        uri="https://example.org/prop",
        data_type="real",
        unit="W/(m²·K)",
        allowed_values=["2.48", "3.00"],
        description="Transmitância térmica",
    )

    payload = prop.model_dump()

    assert payload["name"] == "ThermalTransmittance"
    assert payload["data_type"] == "real"
    assert payload["allowed_values"] == ["2.48", "3.00"]
    assert payload["description"] == "Transmitância térmica"


def test_bsdd_classification_creation_and_defaults() -> None:
    classification = BSDDClassification(name="Wall", code="EF_25", system_name="Uniclass 2015")

    assert classification.name == "Wall"
    assert classification.code == "EF_25"
    assert classification.uri is None
    assert classification.system_name == "Uniclass 2015"


def test_bsdd_context_creation_and_serialization() -> None:
    context = BSDDContext(
        class_name="Wall",
        class_uri="https://example.org/classes/wall",
        domain_name="IFC",
        related_properties=[BSDDProperty(name="ThermalTransmittance", data_type="real")],
        classification_suggestions=[BSDDClassification(name="External Wall", code="EF_25")],
        raw_query="IfcWall ThermalTransmittance",
    )

    payload = context.model_dump()

    assert payload["class_name"] == "Wall"
    assert payload["domain_name"] == "IFC"
    assert payload["raw_query"] == "IfcWall ThermalTransmittance"
    assert payload["related_properties"][0]["name"] == "ThermalTransmittance"
    assert payload["classification_suggestions"][0]["code"] == "EF_25"


def test_validation_result_creation_and_defaults() -> None:
    result = ValidationResult(schema_valid=True, ids_compliant=False, errors=["IDS mismatch"])

    payload = result.model_dump()

    assert payload["schema_valid"] is True
    assert payload["ids_compliant"] is False
    assert payload["errors"] == ["IDS mismatch"]
    assert payload["warnings"] == []
    assert result.is_valid is False


def test_suggestion_backward_compatibility_without_new_fields() -> None:
    suggestion = Suggestion(
        label="2.48 W/(m²·K)",
        value=2.48,
        justification="Tabela normativa",
        confidence="alta",
        source="llm",
    )

    assert suggestion.bsdd_uri is None
    assert suggestion.ids_requirement_id is None


def test_audit_entry_backward_compatibility_without_new_fields() -> None:
    entry = AuditEntry(
        element_guid="A" * 22,
        element_class="IfcWall",
        action="preencher_pset",
        field="ThermalTransmittance",
        new_value=2.48,
        decision="accepted",
        confidence="alta",
        source="llm",
    )

    assert entry.grounding_sources == []
    assert entry.bsdd_uri is None
    assert entry.ids_requirement_id is None
    assert entry.post_validation == "skip"


def test_audit_entry_new_fields_serialization() -> None:
    entry = AuditEntry(
        element_guid="B" * 22,
        element_class="IfcWall",
        action="preencher_pset",
        field="ThermalTransmittance",
        new_value=2.48,
        decision="accepted",
        confidence="alta",
        source="llm",
        grounding_sources=["bsdd", "ids"],
        bsdd_uri="https://example.org/prop",
        ids_requirement_id="req-123",
        post_validation="pass",
    )

    payload = entry.model_dump()

    assert payload["grounding_sources"] == ["bsdd", "ids"]
    assert payload["bsdd_uri"] == "https://example.org/prop"
    assert payload["ids_requirement_id"] == "req-123"
    assert payload["post_validation"] == "pass"
