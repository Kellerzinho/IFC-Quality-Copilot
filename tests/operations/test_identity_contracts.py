"""Contratos operacionais: UUID canônico, hash de comando, recibo e referência de fonte."""

import hashlib
import json
import uuid

import pytest
from pydantic import ValidationError

from src.domain_catalog.actor import ActorSnapshot
from src.domain_catalog.canonical import CanonicalJSONError
from src.operations.contracts import (
    OperationalCommand,
    OperationalReceipt,
    ResultingRef,
    SourceArtifactRef,
    canonical_sha256,
    command_payload_sha256,
)

PROJECT = "1111aaaa-1111-4111-8111-111111111111"
MODEL = "22222222-2222-4222-8222-222222222222"
SOURCE = "33333333-3333-4333-8333-333333333333"
ACTOR = "44444444-4444-4444-8444-444444444444"
COMMAND = "55555555-5555-4555-8555-555555555555"
SHA = "a" * 64


def _actor() -> ActorSnapshot:
    return ActorSnapshot(
        actor_context_id=ACTOR,
        installation_id="inst",
        session_id="sess",
        actor_kind="human",
        declared_name="Pessoa Sintética Declarada",
        identity_assurance="unverified_local",
        registered_at_utc="2026-10-22T00:00:00Z",
    )


def _source(**changes: object) -> SourceArtifactRef:
    data: dict[str, object] = {
        "project_id": PROJECT,
        "model_id": MODEL,
        "source_id": SOURCE,
        "revision": 1,
        "role": "ifc",
        "sha256": SHA,
        "size_bytes": 10,
        "display_name": "modelo.ifc",
        "storage_key": f"s/ifc/{SHA}",
    }
    data.update(changes)
    return SourceArtifactRef.model_validate(data)


@pytest.mark.parametrize(
    "value",
    [
        PROJECT.upper(),
        "{" + PROJECT + "}",
        PROJECT.replace("-", ""),
        "urn:uuid:" + PROJECT,
        1,
        True,
        "",
    ],
)
def test_ids_accept_only_canonical_lowercase_uuid(value: object) -> None:
    with pytest.raises(ValidationError):
        _source(project_id=value)


def test_canonical_uuid_round_trips_as_lowercase_text() -> None:
    ref = _source()
    dumped = ref.model_dump(mode="json")

    assert dumped["project_id"] == PROJECT
    assert ref.project_id == uuid.UUID(PROJECT)
    assert SourceArtifactRef.model_validate(dumped) == ref


def test_command_hash_is_canonical_json_of_operation_actor_project_and_arguments() -> None:
    expected_text = (
        '{"actor_context_id":"' + ACTOR + '","arguments":{"n":1,"name":"Obra","ok":true},'
        '"operation":"create_project","project_id":null}\n'
    )
    expected = hashlib.sha256(expected_text.encode("utf-8")).hexdigest()

    digest = command_payload_sha256(
        operation="create_project",
        actor_context_id=ACTOR,
        project_id=None,
        arguments={"ok": True, "name": "Obra", "n": 1},
    )

    assert digest == expected


@pytest.mark.parametrize(
    "arguments",
    [{"value": True}, {"value": 1}, {"value": "1"}, {"value": None}, {"value": "true"}],
)
def test_command_hash_preserves_json_types(arguments: dict[str, object]) -> None:
    variants: list[dict[str, object]] = [
        {"value": True},
        {"value": 1},
        {"value": "1"},
        {"value": None},
        {"value": "true"},
    ]
    hashes = {
        json.dumps(v): command_payload_sha256(
            operation="create_project", actor_context_id=ACTOR, project_id=None, arguments=v
        )
        for v in variants
    }
    assert len(set(hashes.values())) == 5
    assert hashes[json.dumps(arguments)] in hashes.values()


def test_command_hash_refuses_non_finite_numbers() -> None:
    with pytest.raises(CanonicalJSONError):
        canonical_sha256({"x": float("nan")})


def test_command_build_binds_every_argument() -> None:
    def build(**arguments: object) -> OperationalCommand:
        return OperationalCommand.build(
            command_id=uuid.UUID(COMMAND),
            actor_context_id=uuid.UUID(ACTOR),
            operation="create_model",
            project_id=uuid.UUID(PROJECT),
            arguments=arguments,
        )

    base = build(discipline="arquitetura")
    assert base.payload_sha256 != build(discipline="estrutura").payload_sha256
    assert base.payload_sha256 != build(discipline="arquitetura", extra=0).payload_sha256
    assert base == build(discipline="arquitetura")


def test_receipt_requires_increasing_events_and_unique_refs() -> None:
    data: dict[str, object] = {
        "receipt_id": SOURCE,
        "command_id": COMMAND,
        "operation": "create_project",
        "status": "applied",
        "actor_snapshot": _actor(),
        "project_id": PROJECT,
        "resulting_refs": (ResultingRef(kind="project", ref_id=uuid.UUID(PROJECT)),),
        "event_sequence": (3, 7),
        "committed_at_utc": "2026-10-22T00:00:00Z",
        "payload_sha256": SHA,
    }
    assert OperationalReceipt.model_validate(data).event_sequence == (3, 7)
    bad_sequences: list[dict[str, object]] = [
        {"event_sequence": ()},
        {"event_sequence": (7, 3)},
        {"event_sequence": (3, 3)},
    ]
    for bad in bad_sequences:
        with pytest.raises(ValidationError):
            OperationalReceipt.model_validate({**data, **bad})
    duplicated = (data["resulting_refs"][0],) * 2  # type: ignore[index]
    with pytest.raises(ValidationError):
        OperationalReceipt.model_validate({**data, "resulting_refs": duplicated})


@pytest.mark.parametrize(
    "changes",
    [
        {"storage_key": f"s/ids/{SHA}"},
        {"storage_key": f"s/ifc/{'b' * 64}"},
        {"storage_key": "C:/temp/modelo.ifc"},
        {"storage_key": "https://exemplo.invalid/modelo.ifc"},
        {"storage_key": f"s/ifc/../{SHA}"},
        {"display_name": "pasta/modelo.ifc"},
        {"display_name": "C:\\modelo.ifc"},
        {"revision": 0},
        {"revision": True},
        {"size_bytes": -1},
        {"role": "bcf"},
        {"extra": 1},
    ],
)
def test_source_ref_refuses_incoherent_or_free_paths(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _source(**changes)


def test_source_ref_is_immutable() -> None:
    ref = _source()
    with pytest.raises(ValidationError):
        ref.revision = 2
