"""Contratos da identidade canônica de uma execução oficial."""

from dataclasses import FrozenInstanceError, replace

import pytest

from src.experiment.execution_identity import (
    DatasetIdentity,
    ExecutionIdentity,
    canonical_identity_sha256,
)


def identity(**overrides) -> ExecutionIdentity:
    values = {
        "release_id": "ifcqc-r1",
        "project_sha256": "1" * 64,
        "models_lock_sha256": "2" * 64,
        "datasets": (
            DatasetIdentity(
                key="predio",
                ifc_sha256="3" * 64,
                ground_truth_sha256="4" * 64,
                ids_sha256="5" * 64,
                building_context=(
                    ("bioclimatic_zone", "4A"),
                    ("building_type", "Residencial multifamiliar"),
                ),
            ),
            DatasetIdentity(
                key="casa",
                ifc_sha256="6" * 64,
                ground_truth_sha256="7" * 64,
                ids_sha256="5" * 64,
                building_context=(
                    ("bioclimatic_zone", "4A"),
                    ("building_type", "Residencial unifamiliar"),
                ),
            ),
        ),
        "replica_count": 1,
        "cache_enabled": False,
        "prompt_version": "v7.2",
        "prompt_sha256": "8" * 64,
        "reuse_equivalent": True,
    }
    values.update(overrides)
    return ExecutionIdentity(**values)


@pytest.mark.parametrize(
    "replacement",
    [
        {"release_id": "ifcqc-r2"},
        {"project_sha256": "9" * 64},
        {"models_lock_sha256": "a" * 64},
        {"replica_count": 2},
        {"cache_enabled": True},
        {"prompt_version": "v-next"},
        {"prompt_sha256": "b" * 64},
        {"reuse_equivalent": False},
        {
            "datasets": (
                replace(identity().datasets[0], ifc_sha256="c" * 64),
                identity().datasets[1],
            )
        },
        {
            "datasets": (
                replace(identity().datasets[0], ground_truth_sha256="d" * 64),
                identity().datasets[1],
            )
        },
        {
            "datasets": (
                replace(identity().datasets[0], ids_sha256="e" * 64),
                identity().datasets[1],
            )
        },
        {
            "datasets": (
                replace(
                    identity().datasets[0],
                    building_context=(
                        ("bioclimatic_zone", "5A"),
                        ("building_type", "Residencial multifamiliar"),
                    ),
                ),
                identity().datasets[1],
            )
        },
    ],
)
def test_every_experimental_input_changes_identity_digest(replacement):
    assert canonical_identity_sha256(identity(**replacement)) != canonical_identity_sha256(
        identity()
    )


def test_digest_is_independent_from_json_mapping_order():
    # Vetor dourado calculado sobre JSON UTF-8 compacto com chaves ordenadas.
    assert canonical_identity_sha256(identity()) == (
        "43a25928ffebc431c047d45bcb420e2e086705d6adda8f33a5d6a7565fc66186"
    )


def test_identity_is_immutable():
    value = identity()

    with pytest.raises(FrozenInstanceError):
        value.release_id = "ifcqc-r2"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        value.datasets[0].key = "outro"  # type: ignore[misc]


@pytest.mark.parametrize("digest", ["A" * 64, "f" * 63, "g" * 64])
def test_sha256_fields_require_lowercase_64hex(digest):
    with pytest.raises(ValueError, match="SHA-256 lowercase"):
        identity(project_sha256=digest)


def test_identity_requires_tuple_inputs_and_canonical_dataset_order():
    with pytest.raises(TypeError, match="datasets deve ser tuple"):
        identity(datasets=list(identity().datasets))
    with pytest.raises(TypeError, match="building_context deve ser tuple"):
        replace(identity().datasets[0], building_context=[])
    with pytest.raises(ValueError, match="building_context deve estar ordenado"):
        replace(
            identity().datasets[0],
            building_context=(("building_type", "x"), ("bioclimatic_zone", "4A")),
        )
    with pytest.raises(ValueError, match="ordem predio,casa"):
        identity(datasets=tuple(reversed(identity().datasets)))


def test_replica_count_must_be_positive():
    with pytest.raises(ValueError, match="replica_count deve ser positivo"):
        identity(replica_count=0)
