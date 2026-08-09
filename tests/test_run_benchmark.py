"""Contratos do orquestrador retomável do benchmark portátil."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.run_benchmark as module
from src.experiment.execution_identity import (
    DatasetIdentity,
    ExecutionIdentity,
    canonical_identity_sha256,
)


def _ground_truth_identity_fields(key: str) -> dict[str, object]:
    items, equivalences = (4720, 202) if key == "predio" else (263, 101)
    return {
        "ground_truth_policy_version": "full-coverage-equivalent-v1",
        "ground_truth_items": items,
        "equivalence_classes": equivalences,
        "confidence_counts": (("high", items - 2), ("medium", 1), ("low", 1)),
    }


def official_identity(**overrides: object) -> ExecutionIdentity:
    values: dict[str, object] = {
        "release_id": "ifcqc-r1",
        "project_sha256": "1" * 64,
        "models_lock_sha256": "2" * 64,
        "datasets": (
            DatasetIdentity(
                key="predio",
                ifc_sha256="3" * 64,
                ground_truth_sha256="4" * 64,
                ids_sha256="d" * 64,
                building_context=(
                    ("bioclimatic_zone", "4A"),
                    ("building_type", "Residencial multifamiliar"),
                ),
                **_ground_truth_identity_fields("predio"),
            ),
            DatasetIdentity(
                key="casa",
                ifc_sha256="b" * 64,
                ground_truth_sha256="c" * 64,
                ids_sha256="d" * 64,
                building_context=(
                    ("bioclimatic_zone", "4A"),
                    ("building_type", "Residencial unifamiliar"),
                ),
                **_ground_truth_identity_fields("casa"),
            ),
        ),
        "replica_count": 1,
        "cache_enabled": False,
        "prompt_version": "v7.2",
        "prompt_sha256": "8" * 64,
        "reuse_equivalent": True,
    }
    values.update(overrides)
    return ExecutionIdentity(**values)  # type: ignore[arg-type]


def _expectation(
    *,
    dataset_key: str = "casa",
    model_name: str = "m:test",
    model_digest: str = "a" * 64,
    replica_index: int = 0,
    identity: ExecutionIdentity | None = None,
) -> module.StageExpectation:
    identity = identity or official_identity()
    dataset = next(item for item in identity.datasets if item.key == dataset_key)
    return module.StageExpectation(
        dataset_key=dataset_key,
        model_name=model_name,
        model_digest=model_digest,
        replica_index=replica_index,
        execution_identity=asdict(identity),
        execution_identity_sha256=canonical_identity_sha256(identity),
        ifc_sha256=dataset.ifc_sha256,
        ground_truth_sha256=dataset.ground_truth_sha256,
        ids_sha256=dataset.ids_sha256,
        prompt_version=identity.prompt_version,
        cache_enabled=identity.cache_enabled,
        reuse_equivalent=identity.reuse_equivalent,
        building_context=dict(dataset.building_context),
        ground_truth_policy_version=dataset.ground_truth_policy_version,
        ground_truth_items=dataset.ground_truth_items,
        ground_truth_equivalence_classes=dataset.equivalence_classes,
        ground_truth_confidence_counts=dict(dataset.confidence_counts),
    )


def _write_stage_pair(
    path: Path,
    metadata: dict[str, object],
    outcomes: list[dict[str, object]] | None = None,
) -> None:
    rows = outcomes or [{"issue_id": "issue-1"}]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"metadata": metadata, "issue_counts": {"total_issues": len(rows)}}) + "\n",
        encoding="utf-8",
    )
    _, issues_path = module._stage_artifact_paths(path)
    issues_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def write_valid_matrix(
    results_root: Path,
    identity: ExecutionIdentity,
    models: list[tuple[str, str]],
) -> None:
    for dataset in identity.datasets:
        for model_name, model_digest in models:
            for replica in range(identity.replica_count):
                expectation = _expectation(
                    dataset_key=dataset.key,
                    model_name=model_name,
                    model_digest=model_digest,
                    replica_index=replica,
                    identity=identity,
                )
                _write_stage_pair(
                    module._stage_path(results_root, dataset.key, model_name, replica),
                    asdict(expectation),
                )


def install_fake_runner(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[dict]:
    calls: list[dict[str, object]] = []
    valid_export_paths: set[Path] = set()
    datasets = []
    for key, building_type in (
        ("predio", "Residencial multifamiliar"),
        ("casa", "Residencial unifamiliar"),
    ):
        ifc = tmp_path / f"{key}.ifc"
        gt = tmp_path / f"{key}.yaml"
        ifc.write_bytes(key.encode())
        metadata = _ground_truth_identity_fields(key)
        counts = dict(metadata["confidence_counts"])
        gt.write_text(
            "metadata:\n"
            "  protocol: full-coverage-equivalent-v1\n"
            f"  total_items: {metadata['ground_truth_items']}\n"
            f"  equivalence_class_count: {metadata['equivalence_classes']}\n"
            "  confidence_counts:\n"
            f"    high: {counts['high']}\n"
            f"    medium: {counts['medium']}\n"
            f"    low: {counts['low']}\n"
            "items: []\nskipped: []\n",
            encoding="utf-8",
        )
        datasets.append(
            {
                "key": key,
                "ifc": ifc,
                "gt": gt,
                "issue_types": None,
                "building_context": {
                    "building_type": building_type,
                    "bioclimatic_zone": "4A",
                },
            }
        )

    class FakeRunner:
        def run_single(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                metadata=SimpleNamespace(
                    model_name=kwargs["model_name"],
                    replica_index=kwargs["replica_index"],
                ),
                evaluation=SimpleNamespace(accuracy_top1=1.0, accuracy_top3=1.0),
                stability=SimpleNamespace(failed_count=0),
            )

        @staticmethod
        def _export(result, output_root):
            path = (
                Path(output_root)
                / module._sanitize(result.metadata.model_name)
                / f"run_{result.metadata.replica_index}.json"
            )
            valid_export_paths.add(path)
            return str(path)

    monkeypatch.setattr(module, "DATASETS", datasets)
    monkeypatch.setattr(module, "PID_FILE", tmp_path / "RUNNING")
    monkeypatch.setattr(module, "STOP_FILE", tmp_path / "STOP")
    monkeypatch.setattr(module, "ExperimentRunner", FakeRunner)
    monkeypatch.setattr(module, "_locked_models", lambda: ["m:test"])
    monkeypatch.setattr(module, "_locked_digests", lambda: {"m:test": "a" * 64})
    monkeypatch.setattr(module, "_installed_digest", lambda model: "a" * 64)
    monkeypatch.setattr(module, "_unload_model", lambda model: None)
    monkeypatch.setattr(
        module,
        "_load_and_validate_execution_identity",
        lambda path: official_identity(),
    )
    monkeypatch.setattr(module, "_stage_done", lambda path, expectation: path in valid_export_paths)
    monkeypatch.setattr(module, "_invalid_matrix_stages", lambda *args, **kwargs: [])
    return calls


def _main_args(tmp_path: Path, results_name: str = "results") -> list[str]:
    return [
        "--only-model",
        "m:test",
        "--no-cache",
        "--reuse-equivalent",
        "--execution-identity",
        str(tmp_path / "identity.json"),
        "--results-root",
        str(tmp_path / results_name),
    ]


def _journal_for_sources(
    results_root: Path,
    transaction_id,
    sources: list[tuple[str, Path]],
) -> tuple[Path, Path, module.QuarantineJournal]:
    base = results_root.parent
    root = base / ".invalid-stage-artifacts"
    journal_path = root / ".transactions" / f"{transaction_id}.journal.json"
    staging = root / ".transactions" / f"{transaction_id}.partial"
    final = root / "quarantine" / str(transaction_id)
    members = tuple(
        module.QuarantineMember(
            kind=kind,
            source_relative=source.relative_to(base).as_posix(),
            size_bytes=source.stat().st_size,
            sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        )
        for kind, source in sources
    )
    journal = module.QuarantineJournal(
        transaction_id=transaction_id,
        state="moving",
        results_root_relative=results_root.relative_to(base).as_posix(),
        staging_relative=staging.relative_to(base).as_posix(),
        final_relative=final.relative_to(base).as_posix(),
        members=members,
    )
    staging.mkdir(parents=True)
    module._persist_journal(journal_path, journal)
    return journal_path, staging, journal


def _install_identity_fixture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[Path, ExecutionIdentity]:
    lock = tmp_path / "models.lock.json"
    prompt = tmp_path / "prompt_templates.py"
    ids = tmp_path / "profile.ids"
    shutil.copyfile(module.LOCK_FILE, lock)
    prompt.write_text('PROMPT_VERSION = "v7.2"\n', encoding="utf-8")
    ids.write_text("<ids/>\n", encoding="utf-8")
    datasets = []
    identities = []
    for key, building_type in (
        ("predio", "Residencial multifamiliar"),
        ("casa", "Residencial unifamiliar"),
    ):
        ifc = tmp_path / f"{key}.ifc"
        gt = tmp_path / f"{key}.yaml"
        ifc.write_bytes(key.encode("utf-8"))
        metadata = _ground_truth_identity_fields(key)
        counts = dict(metadata["confidence_counts"])
        gt.write_text(
            "metadata:\n"
            "  protocol: full-coverage-equivalent-v1\n"
            f"  total_items: {metadata['ground_truth_items']}\n"
            f"  equivalence_class_count: {metadata['equivalence_classes']}\n"
            "  confidence_counts:\n"
            f"    high: {counts['high']}\n"
            f"    medium: {counts['medium']}\n"
            f"    low: {counts['low']}\n"
            "items: []\nskipped: []\n",
            encoding="utf-8",
        )
        context = {
            "building_type": building_type,
            "bioclimatic_zone": "4A",
        }
        datasets.append(
            {
                "key": key,
                "ifc": ifc,
                "gt": gt,
                "issue_types": None,
                "building_context": context,
            }
        )
        identities.append(
            DatasetIdentity(
                key=key,
                ifc_sha256=hashlib.sha256(ifc.read_bytes()).hexdigest(),
                ground_truth_sha256=hashlib.sha256(gt.read_bytes()).hexdigest(),
                ids_sha256=hashlib.sha256(ids.read_bytes()).hexdigest(),
                building_context=tuple(sorted(context.items())),
                **_ground_truth_identity_fields(key),
            )
        )
    identity = ExecutionIdentity(
        release_id="ifcqc-r1",
        project_sha256="1" * 64,
        models_lock_sha256=hashlib.sha256(lock.read_bytes()).hexdigest(),
        datasets=tuple(identities),
        replica_count=1,
        cache_enabled=False,
        prompt_version="v7.2",
        prompt_sha256=hashlib.sha256(prompt.read_bytes()).hexdigest(),
        reuse_equivalent=True,
    )
    identity_path = tmp_path / "identity.json"
    identity_path.write_text(json.dumps(asdict(identity)), encoding="utf-8")
    monkeypatch.setattr(module, "LOCK_FILE", lock)
    monkeypatch.setattr(module, "PROMPT_FILE", prompt)
    monkeypatch.setattr(module, "IDS_PATH", ids)
    monkeypatch.setattr(module, "DATASETS", datasets)
    return identity_path, identity


def test_dataset_registry_has_predio_and_casa_only():
    assert [item["key"] for item in module.DATASETS] == ["predio", "casa"]
    assert module.DATASETS[0]["building_context"]["building_type"] == ("Residencial multifamiliar")
    assert module.DATASETS[1]["building_context"]["building_type"] == ("Residencial unifamiliar")
    assert {item["building_context"]["bioclimatic_zone"] for item in module.DATASETS} == {"4A"}


def test_main_forwards_context_identity_no_cache_and_reuse(monkeypatch, tmp_path):
    calls = install_fake_runner(monkeypatch, tmp_path)

    assert module.main(_main_args(tmp_path)) == 0

    assert [call["building_context"] for call in calls] == [
        module.DATASETS[0]["building_context"],
        module.DATASETS[1]["building_context"],
    ]
    assert all(call["reuse_equivalent"] is True for call in calls)
    assert all(call["cache_enabled"] is False for call in calls)
    assert all(call["dataset_key"] in {"predio", "casa"} for call in calls)
    assert all(isinstance(call["execution_identity"], ExecutionIdentity) for call in calls)


def test_main_revalidates_pair_immediately_after_export(monkeypatch, tmp_path):
    calls = install_fake_runner(monkeypatch, tmp_path)
    monkeypatch.setattr(module.ExperimentRunner, "_export", lambda *args: None)

    assert module.main(_main_args(tmp_path)) == 1
    assert calls


def test_official_main_rejects_two_replicas_before_any_stage(monkeypatch, tmp_path):
    calls = install_fake_runner(monkeypatch, tmp_path)
    monkeypatch.setattr(
        module,
        "_load_and_validate_execution_identity",
        lambda path: official_identity(replica_count=2),
    )
    args = _main_args(tmp_path)
    args.extend(["--replicas", "2"])

    assert module.main(args) == 1
    assert calls == []


def test_official_main_rejects_reuse_disabled_in_identity_and_cli(monkeypatch, tmp_path):
    calls = install_fake_runner(monkeypatch, tmp_path)
    monkeypatch.setattr(
        module,
        "_load_and_validate_execution_identity",
        lambda path: official_identity(reuse_equivalent=False),
    )
    args = _main_args(tmp_path)
    args.remove("--reuse-equivalent")

    assert module.main(args) == 1
    assert calls == []


def test_matrix_validator_rejects_nonofficial_replica_count(tmp_path):
    identity = official_identity(replica_count=2)
    models = [(f"model:{index}", f"{index:064x}") for index in range(10)]
    write_valid_matrix(tmp_path, identity, models)

    with pytest.raises(RuntimeError, match="replica"):
        module._invalid_matrix_stages(tmp_path, identity, models)


def test_only_model_limits_execution_but_final_gate_still_uses_full_lock(monkeypatch, tmp_path):
    calls = install_fake_runner(monkeypatch, tmp_path)
    monkeypatch.setattr(module, "_locked_models", lambda: ["m:test", "m:other"])
    monkeypatch.setattr(
        module,
        "_locked_digests",
        lambda: {"m:test": "a" * 64, "m:other": "c" * 64},
    )
    captured: list[list[tuple[str, str]]] = []

    def capture_final_matrix(results_root, identity, models):
        captured.append(models)
        return []

    monkeypatch.setattr(module, "_invalid_matrix_stages", capture_final_matrix)

    assert module.main(_main_args(tmp_path)) == 0
    assert {call["model_name"] for call in calls} == {"m:test"}
    assert captured == [[("m:test", "a" * 64), ("m:other", "c" * 64)]]


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("release_id", 1),
        ("replica_count", True),
        ("cache_enabled", 0),
        ("reuse_equivalent", 1),
    ],
)
def test_execution_identity_rejects_json_type_coercion(field, invalid):
    payload = asdict(official_identity())
    payload[field] = invalid
    payload = json.loads(json.dumps(payload))

    with pytest.raises((TypeError, ValueError)):
        module._parse_execution_identity(payload)


def test_load_execution_identity_recomputes_all_local_inputs(monkeypatch, tmp_path):
    identity_path, expected = _install_identity_fixture(monkeypatch, tmp_path)

    actual = module._load_and_validate_execution_identity(identity_path)

    assert actual == expected


def test_load_execution_identity_rejects_duplicate_context_key(monkeypatch, tmp_path):
    identity_path, _ = _install_identity_fixture(monkeypatch, tmp_path)
    payload = json.loads(identity_path.read_text(encoding="utf-8"))
    payload["datasets"][1]["building_context"].append(["building_type", "Residencial unifamiliar"])
    identity_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="building_context"):
        module._load_and_validate_execution_identity(identity_path)


def test_stage_done_rejects_corrupt_json(tmp_path):
    path = tmp_path / "run_0.json"
    _write_stage_pair(path, asdict(_expectation()))
    path.write_text("{", encoding="utf-8")
    assert not module._stage_done(path, _expectation())


def test_stage_done_rejects_symlink_member_without_windows_privilege(monkeypatch, tmp_path):
    expectation = _expectation()
    path = tmp_path / "run_0.json"
    _write_stage_pair(path, asdict(expectation))
    _, issues_path = module._stage_artifact_paths(path)
    real_is_symlink = Path.is_symlink

    def report_issues_as_symlink(candidate):
        return candidate == issues_path or real_is_symlink(candidate)

    monkeypatch.setattr(Path, "is_symlink", report_issues_as_symlink)

    assert not module._stage_done(path, expectation)


def test_containment_rejects_base_symlink_without_following(monkeypatch, tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    candidate = base / "child" / "run_0.json"
    real_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda self: self == base or real_is_symlink(self),
    )

    with pytest.raises(module.QuarantineRecoveryError, match="recovery_required"):
        module._validate_contained_path(base, candidate)


def test_containment_rejects_parent_junction_without_privilege(monkeypatch, tmp_path):
    base = tmp_path / "base"
    parent = base / "dataset"
    parent.mkdir(parents=True)
    candidate = parent / "run_0.json"
    real_is_junction = getattr(Path, "is_junction", lambda self: False)
    monkeypatch.setattr(
        Path,
        "is_junction",
        lambda self: self == parent or real_is_junction(self),
        raising=False,
    )

    with pytest.raises(module.QuarantineRecoveryError, match="recovery_required"):
        module._validate_contained_path(base, candidate)


def test_containment_rejects_windows_reparse_attribute(monkeypatch, tmp_path):
    base = tmp_path / "base"
    parent = base / "dataset"
    parent.mkdir(parents=True)
    candidate = parent / "run_0.json"
    real_lstat = os.lstat

    def reparse_lstat(path):
        result = real_lstat(path)
        if Path(path) == parent:
            return SimpleNamespace(
                st_mode=result.st_mode,
                st_file_attributes=0x400,
            )
        return result

    monkeypatch.setattr(os, "lstat", reparse_lstat)

    with pytest.raises(module.QuarantineRecoveryError, match="recovery_required"):
        module._validate_contained_path(base, candidate)


def test_containment_rejects_resolved_target_outside_base(monkeypatch, tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    candidate = base / "missing" / "run_0.json"
    outside = tmp_path / "outside" / "run_0.json"
    real_resolve = Path.resolve

    def escape_resolve(self, *args, **kwargs):
        if self == candidate:
            return outside
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", escape_resolve)

    with pytest.raises(module.QuarantineRecoveryError, match="recovery_required"):
        module._validate_contained_path(base, candidate)


def test_main_rejects_reparse_results_root_before_run_single(monkeypatch, tmp_path):
    calls = install_fake_runner(monkeypatch, tmp_path)
    results_root = tmp_path / "results"
    real_is_junction = getattr(Path, "is_junction", lambda self: False)
    monkeypatch.setattr(
        Path,
        "is_junction",
        lambda self: self == results_root or real_is_junction(self),
        raising=False,
    )

    assert module.main(_main_args(tmp_path)) == 1
    assert calls == []


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "empty",
        "invalid_utf8",
        "truncated",
        "invalid_json",
        "blank_line",
        "missing_final_newline",
        "count_mismatch",
    ],
)
def test_stage_done_rejects_invalid_issues_jsonl(tmp_path, damage):
    expectation = _expectation()
    path = tmp_path / "run_0.json"
    _write_stage_pair(path, asdict(expectation))
    _, issues_path = module._stage_artifact_paths(path)
    if damage == "missing":
        issues_path.unlink()
    elif damage == "empty":
        issues_path.write_bytes(b"")
    elif damage == "invalid_utf8":
        issues_path.write_bytes(b"\xff\n")
    elif damage == "truncated":
        issues_path.write_text('{"issue_id":"issue-1"}\n{"issue_id":', encoding="utf-8")
    elif damage == "invalid_json":
        issues_path.write_text("not-json\n", encoding="utf-8")
    elif damage == "blank_line":
        issues_path.write_text('{"issue_id":"issue-1"}\n\n', encoding="utf-8")
    elif damage == "missing_final_newline":
        issues_path.write_text('{"issue_id":"issue-1"}', encoding="utf-8")
    else:
        issues_path.write_text('{"issue_id":"issue-1"}\n{"issue_id":"extra"}\n', encoding="utf-8")
    assert not module._stage_done(path, expectation)


@pytest.mark.parametrize(
    ("field", "wrong"),
    [
        ("dataset_key", "predio"),
        ("ifc_sha256", "e" * 64),
        ("ground_truth_sha256", "f" * 64),
        ("ground_truth_policy_version", "full-coverage-equivalent-v0"),
        ("ground_truth_items", 1),
        ("ground_truth_equivalence_classes", 1),
        ("ground_truth_confidence_counts", {"high": 1, "medium": 0, "low": 0}),
        ("ids_sha256", "0" * 64),
        ("model_name", "other"),
        ("model_digest", "f" * 64),
        ("replica_index", 2),
        ("reuse_equivalent", False),
        ("cache_enabled", True),
        ("prompt_version", "v-next"),
        ("execution_identity_sha256", "1" * 64),
        ("building_context", {"bioclimatic_zone": "3"}),
    ],
)
def test_stage_done_rejects_any_metadata_mismatch(tmp_path, field, wrong):
    expectation = _expectation()
    metadata = asdict(expectation)
    metadata[field] = wrong
    path = tmp_path / "run_0.json"
    _write_stage_pair(path, metadata)
    assert not module._stage_done(path, expectation)


def test_stage_done_accepts_exact_metadata_and_json_arrays(tmp_path):
    expectation = _expectation()
    path = tmp_path / "run_0.json"
    metadata = asdict(expectation)
    metadata["telemetry_extension"] = {"allowed": True}
    _write_stage_pair(path, metadata)
    assert module._stage_done(path, expectation)


def test_stage_done_rejects_nested_execution_identity_change(tmp_path):
    expectation = _expectation()
    metadata = asdict(expectation)
    metadata["execution_identity"]["project_sha256"] = "9" * 64
    path = tmp_path / "run_0.json"
    _write_stage_pair(path, metadata)
    assert not module._stage_done(path, expectation)


def test_invalid_stage_pair_is_quarantined_as_a_unit_before_rerun(tmp_path):
    expectation = _expectation()
    results_root = tmp_path / "results"
    path = results_root / "casa" / "m_test" / "run_0.json"
    _write_stage_pair(path, asdict(expectation))
    _, issues_path = module._stage_artifact_paths(path)
    issues_path.write_text('{"issue_id":', encoding="utf-8")

    quarantine = module._quarantine_invalid_stage_pair(path, results_root)

    assert quarantine is not None
    assert not path.exists()
    assert not issues_path.exists()
    assert (quarantine / path.name).is_file()
    assert (quarantine / issues_path.name).is_file()


def test_journal_atomic_replace_retries_one_transient_windows_denial(monkeypatch, tmp_path):
    results_root = tmp_path / "results"
    path = results_root / "casa" / "m_test" / "run_0.json"
    _write_stage_pair(path, asdict(_expectation()))
    real_replace = os.replace
    denied = False

    def deny_first_journal_replacement(source, destination):
        nonlocal denied
        destination = Path(destination)
        if destination.name.endswith(".journal.json") and destination.exists() and not denied:
            denied = True
            raise PermissionError(5, "temporarily busy")
        return real_replace(source, destination)

    monkeypatch.setattr(os, "replace", deny_first_journal_replacement)

    quarantine = module._quarantine_invalid_stage_pair(path, results_root)

    assert denied
    assert quarantine is not None
    assert (quarantine / path.name).is_file()


def test_unregistered_file_injected_during_move_blocks_transaction(monkeypatch, tmp_path):
    results_root = tmp_path / "results"
    path = results_root / "casa" / "m_test" / "run_0.json"
    _write_stage_pair(path, asdict(_expectation()))
    real_rename = os.rename
    injected = False

    def inject_after_first_member_move(source, destination):
        nonlocal injected
        result = real_rename(source, destination)
        if Path(source) == path and not injected:
            injected = True
            (Path(destination).parent / "surprise.bin").write_bytes(b"foreign")
        return result

    monkeypatch.setattr(os, "rename", inject_after_first_member_move)

    with pytest.raises(module.QuarantineRecoveryError, match="recovery_required"):
        module._quarantine_invalid_stage_pair(path, results_root)

    journals = list((tmp_path / ".invalid-stage-artifacts").rglob("*.journal.json"))
    assert injected
    assert len(journals) == 1
    assert json.loads(journals[0].read_text(encoding="utf-8"))["state"] == ("recovery_required")


@pytest.mark.parametrize("missing_member", ["json", "jsonl"])
def test_partial_stage_quarantines_whichever_member_exists(tmp_path, missing_member):
    results_root = tmp_path / "results"
    path = results_root / "casa" / "m_test" / "run_0.json"
    _write_stage_pair(path, asdict(_expectation()))
    _, issues_path = module._stage_artifact_paths(path)
    missing_path = path if missing_member == "json" else issues_path
    existing_path = issues_path if missing_member == "json" else path
    missing_path.unlink()

    quarantine = module._quarantine_invalid_stage_pair(path, results_root)

    assert quarantine is not None
    assert not path.exists()
    assert not issues_path.exists()
    assert (quarantine / existing_path.name).is_file()
    assert not (quarantine / missing_path.name).exists()


def test_first_move_failure_keeps_pair_co_located_active(monkeypatch, tmp_path):
    results_root = tmp_path / "results"
    path = results_root / "casa" / "m_test" / "run_0.json"
    _write_stage_pair(path, asdict(_expectation()))
    _, issues_path = module._stage_artifact_paths(path)
    before = (path.read_bytes(), issues_path.read_bytes())
    real_rename = os.rename
    failed = False

    def fail_first_active_move_once(source, destination):
        nonlocal failed
        if Path(source) == path and not failed:
            failed = True
            raise OSError("busy")
        return real_rename(source, destination)

    monkeypatch.setattr(os, "rename", fail_first_active_move_once)
    with pytest.raises(RuntimeError, match="quarentena"):
        module._quarantine_invalid_stage_pair(path, results_root)

    assert (path.read_bytes(), issues_path.read_bytes()) == before
    quarantine_root = results_root.parent / ".invalid-stage-artifacts"
    assert not list(quarantine_root.rglob("*.journal.json"))


def test_second_move_failure_rolls_back_pair_to_active_paths(monkeypatch, tmp_path):
    results_root = tmp_path / "results"
    path = results_root / "casa" / "m_test" / "run_0.json"
    _write_stage_pair(path, asdict(_expectation()))
    _, issues_path = module._stage_artifact_paths(path)
    before = (path.read_bytes(), issues_path.read_bytes())
    real_rename = os.rename
    failed_second_move = False

    def fail_second_active_move_once(source, destination):
        nonlocal failed_second_move
        if Path(source) == issues_path and not failed_second_move:
            failed_second_move = True
            raise OSError("busy")
        return real_rename(source, destination)

    monkeypatch.setattr(os, "rename", fail_second_active_move_once)
    with pytest.raises(RuntimeError, match="quarentena"):
        module._quarantine_invalid_stage_pair(path, results_root)

    assert (path.read_bytes(), issues_path.read_bytes()) == before
    quarantine_root = results_root.parent / ".invalid-stage-artifacts"
    assert not list(quarantine_root.rglob(path.name))
    assert not list(quarantine_root.rglob(issues_path.name))
    assert not list(quarantine_root.rglob("*.journal.json"))


def test_destination_collision_during_member_move_preserves_both_files(monkeypatch, tmp_path):
    results_root = tmp_path / "results"
    path = results_root / "casa" / "m_test" / "run_0.json"
    _write_stage_pair(path, asdict(_expectation()))
    source_before = path.read_bytes()
    collision = b"collision-must-survive"
    real_rename = os.rename
    collision_path: Path | None = None

    def collide_immediately_before_rename(source, destination):
        nonlocal collision_path
        if Path(source) == path and collision_path is None:
            collision_path = Path(destination)
            collision_path.write_bytes(collision)
        return real_rename(source, destination)

    monkeypatch.setattr(os, "rename", collide_immediately_before_rename)

    with pytest.raises(module.QuarantineRecoveryError, match="recovery_required"):
        module._quarantine_invalid_stage_pair(path, results_root)

    assert path.read_bytes() == source_before
    assert collision_path is not None
    assert collision_path.read_bytes() == collision


def test_rollback_failure_finishes_quarantine_before_raising(monkeypatch, tmp_path):
    results_root = tmp_path / "results"
    path = results_root / "casa" / "m_test" / "run_0.json"
    _write_stage_pair(path, asdict(_expectation()))
    _, issues_path = module._stage_artifact_paths(path)
    before = (path.read_bytes(), issues_path.read_bytes())
    before_sha256 = tuple(hashlib.sha256(payload).hexdigest() for payload in before)
    real_rename = os.rename
    failed = {"second_move": False, "rollback": False}

    def fail_once_then_allow_forward_recovery(source, destination):
        source = Path(source)
        destination = Path(destination)
        if source == issues_path and not failed["second_move"]:
            failed["second_move"] = True
            raise OSError("second move")
        if destination == path and not failed["rollback"]:
            failed["rollback"] = True
            raise OSError("rollback")
        return real_rename(source, destination)

    monkeypatch.setattr(os, "rename", fail_once_then_allow_forward_recovery)
    with pytest.raises(RuntimeError, match="quarentena"):
        module._quarantine_invalid_stage_pair(path, results_root)

    quarantine_root = results_root.parent / ".invalid-stage-artifacts"
    json_copies = list(quarantine_root.rglob(path.name))
    jsonl_copies = list(quarantine_root.rglob(issues_path.name))
    assert len(json_copies) == len(jsonl_copies) == 1
    assert json_copies[0].parent == jsonl_copies[0].parent
    assert not json_copies[0].parent.name.endswith(".partial")
    after = (json_copies[0].read_bytes(), jsonl_copies[0].read_bytes())
    after_sha256 = tuple(hashlib.sha256(payload).hexdigest() for payload in after)
    assert after == before
    assert after_sha256 == before_sha256
    assert not path.exists()
    assert not issues_path.exists()
    assert not list(quarantine_root.rglob("*.journal.json"))


def _leave_unresolved_split_transaction(monkeypatch, path, results_root):
    _, issues_path = module._stage_artifact_paths(path)
    real_rename = os.rename

    def fail_second_move_and_rollback(source, destination):
        source = Path(source)
        destination = Path(destination)
        if source == issues_path or destination == path:
            raise OSError("locked")
        return real_rename(source, destination)

    monkeypatch.setattr(os, "rename", fail_second_move_and_rollback)
    with pytest.raises(module.QuarantineRecoveryError, match="recovery_required"):
        module._quarantine_invalid_stage_pair(path, results_root)
    return issues_path


def test_rollback_failure_persists_recovery_journal_and_blocks_runner(monkeypatch, tmp_path):
    calls = install_fake_runner(monkeypatch, tmp_path)
    results_root = tmp_path / "results"
    path = module._stage_path(results_root, "casa", "m:test", 0)
    _write_stage_pair(path, asdict(_expectation()))
    issues_path = _leave_unresolved_split_transaction(monkeypatch, path, results_root)
    quarantine_root = results_root.parent / ".invalid-stage-artifacts"
    journals = list(quarantine_root.rglob("*.journal.json"))
    assert len(journals) == 1
    assert json.loads(journals[0].read_text(encoding="utf-8"))["state"] == ("recovery_required")
    assert not path.exists()
    assert issues_path.exists()

    assert module.main(_main_args(tmp_path)) == 1
    assert calls == []
    journals_after = list(quarantine_root.rglob("*.journal.json"))
    assert journals_after == journals
    assert json.loads(journals_after[0].read_text(encoding="utf-8"))["state"] == (
        "recovery_required"
    )


def test_reconcile_rejects_journal_pair_with_different_stems(tmp_path):
    from uuid import uuid4

    results_root = tmp_path / "results"
    aggregate = results_root / "casa" / "m_test" / "run_0.json"
    issues = results_root / "casa" / "m_test" / "run_1_issues.jsonl"
    aggregate.parent.mkdir(parents=True)
    aggregate.write_text("{}\n", encoding="utf-8")
    issues.write_text("{}\n", encoding="utf-8")
    journal_path, _, _ = _journal_for_sources(
        results_root,
        uuid4(),
        [("aggregate", aggregate), ("issues", issues)],
    )

    with pytest.raises(module.QuarantineRecoveryError, match="recovery_required"):
        module._reconcile_quarantine_transactions(results_root)

    assert journal_path.exists()


def test_reconcile_rejects_unregistered_file_in_staging(tmp_path):
    from uuid import uuid4

    results_root = tmp_path / "results"
    aggregate = results_root / "casa" / "m_test" / "run_0.json"
    aggregate.parent.mkdir(parents=True)
    aggregate.write_text("{}\n", encoding="utf-8")
    journal_path, staging, _ = _journal_for_sources(
        results_root, uuid4(), [("aggregate", aggregate)]
    )
    os.replace(aggregate, staging / aggregate.name)
    (staging / "surprise.bin").write_bytes(b"not-registered")

    with pytest.raises(module.QuarantineRecoveryError, match="recovery_required"):
        module._reconcile_quarantine_transactions(results_root)

    assert journal_path.exists()
    assert json.loads(journal_path.read_text(encoding="utf-8"))["state"] == ("recovery_required")


def test_reconcile_rejects_coerced_journal_scalar_type(tmp_path):
    from uuid import uuid4

    results_root = tmp_path / "results"
    aggregate = results_root / "casa" / "m_test" / "run_0.json"
    aggregate.parent.mkdir(parents=True)
    aggregate.write_text("{}\n", encoding="utf-8")
    journal_path, _, _ = _journal_for_sources(results_root, uuid4(), [("aggregate", aggregate)])
    payload = json.loads(journal_path.read_text(encoding="utf-8"))
    payload["members"][0]["size_bytes"] = str(payload["members"][0]["size_bytes"])
    journal_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(module.QuarantineRecoveryError, match="recovery_required"):
        module._reconcile_quarantine_transactions(results_root)

    assert journal_path.exists()


def test_reconcile_normalizes_permission_error_to_recovery_required(monkeypatch, tmp_path):
    from uuid import uuid4

    results_root = tmp_path / "results"
    aggregate = results_root / "casa" / "m_test" / "run_0.json"
    aggregate.parent.mkdir(parents=True)
    aggregate.write_text("{}\n", encoding="utf-8")
    journal_path, _, _ = _journal_for_sources(results_root, uuid4(), [("aggregate", aggregate)])
    monkeypatch.setattr(
        module,
        "_member_location",
        lambda *args: (_ for _ in ()).throw(PermissionError("locked")),
    )

    with pytest.raises(module.QuarantineRecoveryError, match="recovery_required"):
        module._reconcile_quarantine_transactions(results_root)

    assert journal_path.exists()


def test_reconcile_normalizes_initial_path_io_error(monkeypatch, tmp_path):
    monkeypatch.setattr(
        module,
        "_validate_contained_path",
        lambda *args: (_ for _ in ()).throw(PermissionError("locked")),
    )

    with pytest.raises(module.QuarantineRecoveryError, match="recovery_required"):
        module._reconcile_quarantine_transactions(tmp_path / "results")


@pytest.mark.parametrize("reparse_target", ["transaction_root", "journal"])
def test_reconcile_rejects_reparse_before_loading_journal(monkeypatch, tmp_path, reparse_target):
    results_root = tmp_path / "results"
    transaction_root = tmp_path / ".invalid-stage-artifacts" / ".transactions"
    transaction_root.mkdir(parents=True)
    journal_path = transaction_root / f"{'0' * 32}.journal.json"
    journal_path.write_text("{}\n", encoding="utf-8")
    target = transaction_root if reparse_target == "transaction_root" else journal_path
    real_is_junction = getattr(Path, "is_junction", lambda self: False)
    monkeypatch.setattr(
        Path,
        "is_junction",
        lambda self: self == target or real_is_junction(self),
        raising=False,
    )
    loaded: list[Path] = []

    def forbid_load(path):
        loaded.append(path)
        raise AssertionError("journal lido antes da validação do reparse point")

    monkeypatch.setattr(module, "_load_journal", forbid_load)

    with pytest.raises(module.QuarantineRecoveryError, match="recovery_required"):
        module._reconcile_quarantine_transactions(results_root)

    assert loaded == []


def test_quarantine_rejects_symlink_transaction_root(monkeypatch, tmp_path):
    results_root = tmp_path / "results"
    path = results_root / "casa" / "m_test" / "run_0.json"
    _write_stage_pair(path, asdict(_expectation()))
    transaction_root = tmp_path / ".invalid-stage-artifacts"
    real_is_symlink = Path.is_symlink

    def report_transaction_root_as_symlink(candidate):
        return candidate == transaction_root or real_is_symlink(candidate)

    monkeypatch.setattr(Path, "is_symlink", report_transaction_root_as_symlink)

    with pytest.raises((RuntimeError, module.QuarantineRecoveryError)):
        module._quarantine_invalid_stage_pair(path, results_root)

    assert path.exists()
    assert not list(tmp_path.rglob("*.journal.json"))


def test_next_invocation_reconciles_split_before_any_run_single(monkeypatch, tmp_path):
    results_root = tmp_path / "results"
    path = module._stage_path(results_root, "casa", "m:test", 0)
    _write_stage_pair(path, asdict(_expectation()))
    _, original_issues_path = module._stage_artifact_paths(path)
    before = (path.read_bytes(), original_issues_path.read_bytes())
    before_sha256 = tuple(hashlib.sha256(payload).hexdigest() for payload in before)
    with monkeypatch.context() as transaction_fault:
        issues_path = _leave_unresolved_split_transaction(transaction_fault, path, results_root)

    calls = install_fake_runner(monkeypatch, tmp_path)
    original_run_single = module.ExperimentRunner.run_single
    original_acquire_pidfile = module._acquire_pidfile
    original_reconcile = module._reconcile_quarantine_transactions
    quarantine_root = results_root.parent / ".invalid-stage-artifacts"
    acquired_tokens: list[str] = []
    reconcile_tokens: list[str] = []

    def capture_owned_pid_lease(pid_path):
        lease = original_acquire_pidfile(pid_path)
        assert lease is not None
        acquired_tokens.append(lease.token)
        return lease

    def assert_owned_pid_lease_during_reconcile(root):
        assert acquired_tokens
        record = json.loads(module.PID_FILE.read_text(encoding="utf-8"))
        assert record["pid"] == os.getpid()
        assert record["token"] == acquired_tokens[-1]
        reconcile_tokens.append(record["token"])
        return original_reconcile(root)

    def assert_reconciled_before_runner(self, **kwargs):
        json_copies = list(quarantine_root.rglob(path.name))
        jsonl_copies = list(quarantine_root.rglob(issues_path.name))
        assert len(json_copies) == len(jsonl_copies) == 1
        assert json_copies[0].parent == jsonl_copies[0].parent
        assert not json_copies[0].parent.name.endswith(".partial")
        after = (json_copies[0].read_bytes(), jsonl_copies[0].read_bytes())
        after_sha256 = tuple(hashlib.sha256(payload).hexdigest() for payload in after)
        assert after == before
        assert after_sha256 == before_sha256
        assert not path.exists()
        assert not issues_path.exists()
        assert not list(quarantine_root.rglob("*.journal.json"))
        return original_run_single(self, **kwargs)

    monkeypatch.setattr(module, "_acquire_pidfile", capture_owned_pid_lease)
    monkeypatch.setattr(
        module,
        "_reconcile_quarantine_transactions",
        assert_owned_pid_lease_during_reconcile,
    )
    monkeypatch.setattr(module.ExperimentRunner, "run_single", assert_reconciled_before_runner)
    assert module.main(_main_args(tmp_path)) == 0
    assert reconcile_tokens == acquired_tokens
    assert not module.PID_FILE.exists()
    assert {call["dataset_key"] for call in calls} == {"predio", "casa"}


def test_main_quarantines_both_old_members_before_rerun(monkeypatch, tmp_path):
    calls = install_fake_runner(monkeypatch, tmp_path)
    results_root = tmp_path / "results"
    path = module._stage_path(results_root, "casa", "m:test", 0)
    _write_stage_pair(path, asdict(_expectation()))
    _, issues_path = module._stage_artifact_paths(path)
    issues_path.write_text('{"issue_id":', encoding="utf-8")
    original_run_single = module.ExperimentRunner.run_single

    def assert_isolated_before_rerun(self, **kwargs):
        if kwargs["dataset_key"] == "casa":
            assert not path.exists()
            assert not issues_path.exists()
        return original_run_single(self, **kwargs)

    monkeypatch.setattr(module.ExperimentRunner, "run_single", assert_isolated_before_rerun)
    assert module.main(_main_args(tmp_path)) == 0
    quarantine_root = results_root.parent / ".invalid-stage-artifacts"
    assert len(list(quarantine_root.rglob(path.name))) == 1
    assert len(list(quarantine_root.rglob(issues_path.name))) == 1
    assert {call["dataset_key"] for call in calls} == {"predio", "casa"}


def test_main_never_reruns_stage_when_quarantine_fails(monkeypatch, tmp_path):
    calls = install_fake_runner(monkeypatch, tmp_path)
    results_root = tmp_path / "results"
    path = module._stage_path(results_root, "casa", "m:test", 0)
    _write_stage_pair(path, asdict(_expectation()))
    real_quarantine = module._quarantine_invalid_stage_pair

    def fail_target_stage(json_path, root):
        if json_path == path:
            raise RuntimeError("quarentena indisponível")
        return real_quarantine(json_path, root)

    monkeypatch.setattr(module, "_quarantine_invalid_stage_pair", fail_target_stage)
    assert module.main(_main_args(tmp_path)) == 1
    assert all(call["dataset_key"] != "casa" for call in calls)


def test_pid_lease_uses_exclusive_create(monkeypatch, tmp_path):
    seen_flags = []
    real_open = os.open
    monkeypatch.setattr(
        os,
        "open",
        lambda path, flags, mode=0o777: (
            seen_flags.append(flags),
            real_open(path, flags, mode),
        )[1],
    )
    lease = module._acquire_pidfile(tmp_path / "running.json")
    assert lease is not None
    assert seen_flags[0] & os.O_EXCL


def test_stale_pid_is_reaped_but_live_matching_pid_blocks(monkeypatch, tmp_path):
    path = tmp_path / "running.json"
    path.write_text('{"pid":7,"create_time":1.0,"token":"old"}', encoding="utf-8")
    monkeypatch.setattr(module, "_pid_record_is_live", lambda record: False)
    lease = module._acquire_pidfile(path)
    assert lease is not None
    assert lease.token != "old"
    monkeypatch.setattr(module, "_pid_record_is_live", lambda record: True)
    assert module._acquire_pidfile(path) is None


def test_stale_reap_lease_is_recovered(monkeypatch, tmp_path):
    path = tmp_path / "running.json"
    reap = path.with_name(f"{path.name}.reap")
    stale = '{"pid":7,"create_time":1.0,"token":"stale"}'
    path.write_text(stale, encoding="utf-8")
    reap.write_text(stale, encoding="utf-8")
    monkeypatch.setattr(module, "_pid_record_is_live", lambda record: False)

    lease = module._acquire_pidfile(path)

    assert lease is not None
    assert lease.token != "stale"


def test_pid_record_is_published_only_after_owner_record_is_complete(monkeypatch, tmp_path):
    path = tmp_path / "running.json"
    real_link = os.link
    published: list[dict[str, object]] = []

    def inspect_complete_owner_before_publish(source, destination, *args, **kwargs):
        if Path(destination) == path:
            published.append(json.loads(Path(source).read_text(encoding="utf-8")))
        return real_link(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "link", inspect_complete_owner_before_publish)

    lease = module._acquire_pidfile(path)

    assert lease is not None
    assert published == [asdict(lease)]


def test_main_maps_pid_acquisition_io_error_to_failure(monkeypatch, tmp_path):
    calls = install_fake_runner(monkeypatch, tmp_path)
    monkeypatch.setattr(
        module,
        "_acquire_pidfile",
        lambda path: (_ for _ in ()).throw(PermissionError("denied")),
    )

    assert module.main(_main_args(tmp_path)) == 1
    assert calls == []


def test_release_restores_foreign_record_replaced_at_cleanup_boundary(monkeypatch, tmp_path):
    path = tmp_path / "running.json"
    lease = module._acquire_pidfile(path)
    assert lease is not None
    foreign = {"pid": 999, "create_time": 2.0, "token": "foreign"}
    real_move = module._move_no_replace
    replaced = False

    def replace_immediately_before_cleanup(source, destination):
        nonlocal replaced
        if Path(source) == path and not replaced:
            replaced = True
            path.unlink()
            path.write_text(json.dumps(foreign), encoding="utf-8")
        return real_move(source, destination)

    monkeypatch.setattr(module, "_move_no_replace", replace_immediately_before_cleanup)

    module._release_pidfile(path, lease)

    assert replaced
    assert json.loads(path.read_text(encoding="utf-8")) == foreign


def test_release_pidfile_preserves_foreign_token(tmp_path):
    path = tmp_path / "running.json"
    lease = module._acquire_pidfile(path)
    assert lease is not None
    record = json.loads(path.read_text(encoding="utf-8"))
    record["token"] = "foreign"
    path.write_text(json.dumps(record), encoding="utf-8")

    module._release_pidfile(path, lease)

    assert path.exists()


def test_stop_existing_at_launch_is_ignored_but_rewrite_is_interruption(tmp_path):
    path = tmp_path / "STOP"
    path.write_text("stop", encoding="utf-8")
    baseline = module._capture_stop_baseline(path)
    assert not module._stop_requested(path, baseline)
    path.write_text("stop-new", encoding="utf-8")
    assert module._stop_requested(path, baseline)


def test_new_stop_and_keyboard_interrupt_return_130(monkeypatch, tmp_path):
    install_fake_runner(monkeypatch, tmp_path)
    original_run_single = module.ExperimentRunner.run_single

    def stop_during_first_stage(self, **kwargs):
        result = original_run_single(self, **kwargs)
        module.STOP_FILE.write_text("novo", encoding="utf-8")
        return result

    monkeypatch.setattr(module.ExperimentRunner, "run_single", stop_during_first_stage)
    assert module.main(_main_args(tmp_path)) == 130
    module.STOP_FILE.unlink()
    monkeypatch.setattr(
        module.ExperimentRunner,
        "run_single",
        lambda self, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    assert module.main(_main_args(tmp_path, "results2")) == 130


def test_model_digest_mismatch_aborts():
    with pytest.raises(RuntimeError, match="digest"):
        module._assert_model_digest("m:test", expected="a" * 64, actual="b" * 64)


def test_digest_mismatch_aborts_before_later_model_runs(monkeypatch, tmp_path):
    calls = install_fake_runner(monkeypatch, tmp_path)
    monkeypatch.setattr(module, "_locked_models", lambda: ["m:test", "m:later"])
    monkeypatch.setattr(
        module,
        "_locked_digests",
        lambda: {"m:test": "a" * 64, "m:later": "c" * 64},
    )
    monkeypatch.setattr(
        module,
        "_installed_digest",
        lambda model: "b" * 64 if model == "m:test" else "c" * 64,
    )
    args = _main_args(tmp_path)
    del args[:2]

    assert module.main(args) == 1
    assert calls == []


@pytest.mark.parametrize("missing_member", ["json", "jsonl"])
def test_complete_requires_exact_twenty_valid_stage_pairs(tmp_path, missing_member):
    identity = official_identity()
    models = [(f"model:{index}", f"{index:064x}") for index in range(10)]
    write_valid_matrix(tmp_path, identity, models)
    assert module._invalid_matrix_stages(tmp_path, identity, models) == []
    stage = module._stage_path(tmp_path, "casa", "model:9", 0)
    _, issues_path = module._stage_artifact_paths(stage)
    (stage if missing_member == "json" else issues_path).unlink()
    assert module._invalid_matrix_stages(tmp_path, identity, models) == ["casa/model:9/run_0"]


@pytest.mark.parametrize("extra_shape", ["pair", "json_only", "jsonl_only"])
def test_complete_rejects_unexpected_stage_pair_or_orphan(tmp_path, extra_shape):
    identity = official_identity()
    models = [(f"model:{index}", f"{index:064x}") for index in range(10)]
    write_valid_matrix(tmp_path, identity, models)
    extra = module._stage_path(tmp_path, "casa", "model:9", 1)
    _write_stage_pair(extra, asdict(_expectation()))
    _, extra_jsonl = module._stage_artifact_paths(extra)
    if extra_shape == "json_only":
        extra_jsonl.unlink()
    elif extra_shape == "jsonl_only":
        extra.unlink()
    relative_stem = extra.relative_to(tmp_path).as_posix().removesuffix(".json")

    assert module._invalid_matrix_stages(tmp_path, identity, models) == [
        f"unexpected:{relative_stem}"
    ]
