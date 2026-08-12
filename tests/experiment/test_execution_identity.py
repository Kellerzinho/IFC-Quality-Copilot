"""Contratos da identidade canônica de uma execução oficial."""

from dataclasses import FrozenInstanceError, replace

import pytest

from src.experiment.execution_identity import (
    DatasetIdentity,
    ExecutionIdentity,
    canonical_identity_sha256,
    load_ground_truth_identity_metadata,
)


def dataset_metadata(*, items: int, equivalences: int):
    return {
        "ground_truth_policy_version": "full-coverage-equivalent-v1",
        "ground_truth_items": items,
        "equivalence_classes": equivalences,
        "confidence_counts": (
            ("high", items - 2),
            ("medium", 1),
            ("low", 1),
        ),
    }


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
                **dataset_metadata(items=4720, equivalences=202),
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
                **dataset_metadata(items=263, equivalences=101),
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
                replace(
                    identity().datasets[0],
                    ground_truth_items=4719,
                    confidence_counts=(("high", 4717), ("medium", 1), ("low", 1)),
                ),
                identity().datasets[1],
            )
        },
        {
            "datasets": (
                replace(identity().datasets[0], equivalence_classes=201),
                identity().datasets[1],
            )
        },
        {
            "datasets": (
                replace(
                    identity().datasets[0],
                    confidence_counts=(("high", 4716), ("medium", 3), ("low", 1)),
                ),
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
    # Recalculado em 2026-08-12, quando os parametros de geracao entraram na
    # identidade (source_commit, num_ctx_policy, num_ctx, num_predict, seed,
    # temperature, top_p, repeat_penalty): antes, dois runs com janela de
    # contexto ou seed diferentes produziam o mesmo hash.
    # Anterior: 36cb1d2fa29f…59468a48f6768.
    assert canonical_identity_sha256(identity()) == (
        "9a5f8bd0c99ebfa182740e5355cdc521ddcd542457b4076c0c4960e2067bf7e3"
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


def test_dataset_identity_rejects_non_integral_policy_and_invalid_counts():
    dataset = identity().datasets[0]
    with pytest.raises(ValueError, match="politica integral"):
        replace(dataset, ground_truth_policy_version="evidence-audited-v1")
    with pytest.raises(ValueError, match="confidence_counts"):
        replace(
            dataset,
            confidence_counts=(("high", 1), ("medium", 1), ("unknown", 4718)),
        )
    with pytest.raises(ValueError, match="somatorio"):
        replace(
            dataset,
            confidence_counts=(("high", 1), ("medium", 1), ("low", 1)),
        )
    with pytest.raises(ValueError, match="equivalence_classes"):
        replace(dataset, equivalence_classes=4721)


def test_load_ground_truth_identity_metadata_requires_exact_integral_metadata(tmp_path):
    path = tmp_path / "ground_truth.yaml"
    path.write_text(
        """
metadata:
  protocol: full-coverage-equivalent-v1
  total_items: 263
  equivalence_class_count: 101
  confidence_counts: {high: 52, medium: 132, low: 79}
items: []
skipped: []
""",
        encoding="utf-8",
    )

    metadata = load_ground_truth_identity_metadata(path)

    assert metadata.ground_truth_policy_version == "full-coverage-equivalent-v1"
    assert metadata.ground_truth_items == 263
    assert metadata.equivalence_classes == 101
    assert metadata.confidence_counts == (("high", 52), ("medium", 132), ("low", 79))

    path.write_text(path.read_text(encoding="utf-8").replace("low: 79", "low: 78"))
    with pytest.raises(ValueError, match="somatorio"):
        load_ground_truth_identity_metadata(path)
