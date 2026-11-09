"""Registro de capacidades de operação (M1-05); especificações SINTÉTICAS.

O cadastro só referencia operações por ID/versão. Quem declara que uma operação
existe é o código (M2/M3); o registro informa disponibilidade e nunca executa nada.
"""

import pytest
from pydantic import ValidationError

from src.domain_catalog.models import EvidencePolicy
from src.domain_catalog.operations import OperationRegistry, OperationSpec


def _spec(operation_id: str = "literal_read", version: str = "1") -> OperationSpec:
    return OperationSpec(
        operation_id=operation_id,
        version=version,
        description="Leitura literal sintética para teste do registro.",
        inputs=("binding",),
        output="observação tipada",
        preconditions=("portador aprovado",),
        implementation="tests.sintetico:leitura",
        tests=("tests/domain_catalog/test_capabilities.py",),
    )


def test_unknown_operation_is_unsupported() -> None:
    capability = OperationRegistry([_spec()]).capability("formwork_area_from_geometry")

    assert capability.status == "unsupported"
    assert capability.available_version is None
    assert "não implementada" in capability.reason


def test_registered_operation_is_available() -> None:
    capability = OperationRegistry([_spec()]).capability("literal_read", "1")

    assert (capability.status, capability.available_version) == ("available", "1")


def test_unpinned_request_reports_registered_version() -> None:
    capability = OperationRegistry([_spec(version="2")]).capability("literal_read")

    assert (capability.status, capability.available_version) == ("available", "2")


def test_other_version_is_not_available() -> None:
    capability = OperationRegistry([_spec(version="2")]).capability("literal_read", "1")

    assert capability.status == "version_mismatch"
    assert capability.available_version == "2"


def test_registry_refuses_duplicate_operation_ids() -> None:
    with pytest.raises(ValueError, match="duplicad"):
        OperationRegistry([_spec(), _spec()])


@pytest.mark.parametrize(
    "extra",
    [
        {"implementation": "os:system"},
        {"formula": "__import__('os').system('dir')"},
    ],
)
def test_evidence_policy_cannot_carry_code(extra: dict[str, str]) -> None:
    data = {
        "id": "urn:uuid:00000000-0000-4000-8000-0000000000d1",
        "operation_id": "literal_read",
        "admissible_channels": ["P"],
        "on_missing": "abstain",
        "on_conflict": "abstain",
        "lifecycle": "draft",
        **extra,
    }

    with pytest.raises(ValidationError, match="Extra inputs"):
        EvidencePolicy.model_validate(data)


def test_operation_id_is_an_identifier_not_an_expression() -> None:
    with pytest.raises(ValidationError, match="operation_id"):
        EvidencePolicy(
            id="urn:uuid:00000000-0000-4000-8000-0000000000d1",
            operation_id="os.system('dir')",
            admissible_channels=("P",),
            on_missing="abstain",
            on_conflict="abstain",
            lifecycle="draft",
        )
