"""Regressões E3-REV-01: referências do envelope em pacotes sintéticos reais."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.domain_catalog.content import CatalogContent
from src.domain_catalog.context_builder import LocalCatalogContextBuilder
from src.domain_catalog.models import AllowedValue, EvidencePolicy
from src.domain_catalog.operations import OperationRegistry, OperationSpec
from src.domain_catalog.projection_contracts import CatalogProjection, LocalCatalogContext
from src.domain_catalog.reader import open_catalog
from tests.domain_catalog import factories as f
from tests.domain_catalog.test_legacy_adapters import request

LOCAL_VALUE_SET_ID = "urn:uuid:00000000-0000-4000-8000-000000000101"
POLICY_ID = "urn:uuid:00000000-0000-4000-8000-000000000102"
FOREIGN_ID = "urn:uuid:00000000-0000-4000-8000-000000000103"


def _context(
    tmp_path: Path, content: CatalogContent, registry: OperationRegistry | None = None
) -> LocalCatalogContext:
    ref, folder = f.write_synthetic_release(tmp_path, content)
    reader = open_catalog(ref, folder, registry=registry or OperationRegistry())
    return LocalCatalogContextBuilder(reader, catalog=ref).build(request())


def _restricted_content() -> CatalogContent:
    local = f.value_set().model_copy(
        update={
            "id": LOCAL_VALUE_SET_ID,
            "values": (AllowedValue(code="B"),),
            "restricts_value_set_id": f.VALUE_SET_ID,
        }
    )
    return f.minimal_content().model_copy(
        update={
            "value_sets": (f.value_set(), local),
            "bindings": (f.binding().model_copy(update={"value_set_id": LOCAL_VALUE_SET_ID}),),
        }
    )


def _physical_content(version: str | None = "1") -> CatalogContent:
    policy = EvidencePolicy(
        id=POLICY_ID,
        operation_id="synthetic.read",
        operation_version=version,
        admissible_channels=("P",),
        on_missing="abstain",
        on_conflict="abstain",
        lifecycle="approved",
    )
    return f.minimal_content().model_copy(
        update={
            "concepts": (
                f.concept().model_copy(
                    update={
                        "logical_type": "decimal",
                        "dimension": "length",
                        "unit_id": f.UNIT_ID,
                        "value_set_id": None,
                    }
                ),
            ),
            "bindings": (
                f.binding().model_copy(
                    update={"ifc_type": "IfcLengthMeasure", "evidence_policy_id": POLICY_ID}
                ),
            ),
            "units": (f.length_unit(),),
            "value_sets": (),
            "evidence_policies": (policy,),
        }
    )


@pytest.mark.parametrize("change", ["missing", "foreign_id", "global_instead_of_local"])
def test_context_rejects_replaced_or_removed_local_enum(tmp_path: Path, change: str) -> None:
    result = _context(tmp_path, _restricted_content())
    assert result.status == "available"
    assert result.properties[0].allowed_values == ("B",)
    data = result.model_dump(mode="json")
    if change == "missing":
        data["projection"]["effective_value_set"] = None
        data["properties"][0]["allowed_values"] = None
    elif change == "foreign_id":
        data["projection"]["effective_value_set"]["id"] = FOREIGN_ID
    else:
        data["projection"]["effective_value_set"] = f.value_set().model_dump(mode="json")
        data["properties"][0]["allowed_values"] = ["A", "B"]
    with pytest.raises(ValidationError, match="enum"):
        LocalCatalogContext.model_validate(data)


@pytest.mark.parametrize("field", ["effective_value_set", "unit", "evidence_policy"])
@pytest.mark.parametrize("change", ["missing", "foreign_id"])
def test_projection_rejects_missing_or_foreign_reference(
    tmp_path: Path, field: str, change: str
) -> None:
    content = f.minimal_content() if field == "effective_value_set" else _physical_content()
    result = _context(tmp_path, content)
    assert result.projection is not None
    data = result.projection.model_dump(mode="json")
    if change == "missing":
        data[field] = None
    else:
        data[field]["id"] = FOREIGN_ID
    with pytest.raises(ValidationError):
        CatalogProjection.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("field", ["effective_value_set", "unit", "evidence_policy"])
def test_projection_rejects_entity_without_declared_reference(tmp_path: Path, field: str) -> None:
    content = f.minimal_content().model_copy(
        update={
            "concepts": (f.concept().model_copy(update={"value_set_id": None}),),
            "value_sets": (),
        }
    )
    result = _context(tmp_path, content)
    assert result.projection is not None
    data = result.projection.model_dump(mode="json")
    entities = {
        "effective_value_set": f.value_set(),
        "unit": f.length_unit(),
        "evidence_policy": _physical_content().evidence_policies[0],
    }
    data[field] = entities[field].model_dump(mode="json")
    with pytest.raises(ValidationError):
        CatalogProjection.model_validate(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [("operation_id", "synthetic.other"), ("requested_version", "2"), ("requested_version", None)],
)
def test_projection_rejects_capability_for_another_operation_or_version(
    tmp_path: Path, field: str, value: str | None
) -> None:
    result = _context(tmp_path, _physical_content())
    assert result.projection is not None
    data = result.projection.model_dump(mode="json")
    data["capability"][field] = value
    with pytest.raises(ValidationError, match="capacidade"):
        CatalogProjection.model_validate(data)


@pytest.mark.parametrize("has_policy", [True, False])
def test_projection_requires_capability_exactly_when_policy_is_present(
    tmp_path: Path, has_policy: bool
) -> None:
    result = _context(tmp_path, _physical_content())
    assert result.projection is not None
    data = result.projection.model_dump(mode="json")
    if has_policy:
        data["capability"] = None
    else:
        data["binding"]["evidence_policy_id"] = None
        data["evidence_policy"] = None
    with pytest.raises(ValidationError, match="capacidade"):
        CatalogProjection.model_validate(data)


@pytest.mark.parametrize("local", [False, True])
def test_enum_roundtrip_preserves_declared_global_or_local_restriction(
    tmp_path: Path, local: bool
) -> None:
    result = _context(tmp_path, _restricted_content() if local else f.minimal_content())
    restored = LocalCatalogContext.model_validate_json(result.model_dump_json())
    assert restored == result
    assert restored.projection is not None
    assert restored.projection.effective_value_set is not None
    assert restored.projection.effective_value_set.id == (
        LOCAL_VALUE_SET_ID if local else f.VALUE_SET_ID
    )
    assert restored.properties[0].allowed_values == (("B",) if local else ("A", "B"))


@pytest.mark.parametrize(
    ("requested", "installed", "status"),
    [
        ("1", None, "unsupported"),
        ("1", "1", "available"),
        ("1", "2", "version_mismatch"),
        (None, None, "unsupported"),
        (None, "2", "available"),
    ],
)
def test_physical_roundtrip_keeps_policy_and_real_registry_response(
    tmp_path: Path, requested: str | None, installed: str | None, status: str
) -> None:
    specs = (
        (
            OperationSpec(
                operation_id="synthetic.read",
                version=installed,
                description="Fixture de capacidade, sem execução de operação.",
                inputs=("synthetic_input",),
                output="synthetic_output",
                implementation="synthetic:read",
                tests=("synthetic:test_read",),
            ),
        )
        if installed is not None
        else ()
    )
    result = _context(tmp_path, _physical_content(requested), OperationRegistry(specs))
    restored = LocalCatalogContext.model_validate_json(result.model_dump_json())
    assert restored == result
    assert restored.status == "available"
    projection = restored.projection
    assert projection is not None
    assert projection.unit is not None
    assert projection.unit.id == f.UNIT_ID
    assert restored.properties[0].unit == "m"
    assert projection.effective_value_set is None
    assert projection.evidence_policy is not None
    assert projection.evidence_policy.id == POLICY_ID
    assert projection.capability is not None
    assert projection.capability.operation_id == "synthetic.read"
    assert projection.capability.requested_version == requested
    assert projection.capability.status == status
    assert projection.capability.available_version == installed
