"""Caminho feliz e garantias criticas do orquestrador Windows."""

from __future__ import annotations

import hashlib
import json
import subprocess
import zipfile
from contextlib import nullcontext
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts.run_benchmark import _stage_expectation, _stage_path
from scripts.windows_benchmark import (
    BenchmarkArgs,
    build_child_env,
    build_execution_identity,
    load_run_state,
    run_benchmark_release,
    select_or_create_run,
)
from src.experiment.evidence_bundle import EvidencePrivacyError
from src.experiment.execution_identity import DatasetIdentity, ExecutionIdentity
from src.experiment.model_lock import ModelMatrixLock, load_model_lock

ROOT = Path(__file__).resolve().parents[2]
LOCK_SOURCE = ROOT / "src/experiment/results/models.lock.json"
TEMPLATE_SOURCE = ROOT / "windows/release-manifest.template.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record(root: Path, path: Path, *, key: str) -> dict[str, object]:
    return {
        key: path.relative_to(root).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _ground_truth_identity_fields(key: str) -> dict[str, object]:
    items, equivalences = (4720, 202) if key == "predio" else (263, 101)
    return {
        "ground_truth_policy_version": "full-coverage-equivalent-v1",
        "ground_truth_items": items,
        "equivalence_classes": equivalences,
        "confidence_counts": (("high", items - 2), ("medium", 1), ("low", 1)),
    }


def _identity(seed: str = "1") -> ExecutionIdentity:
    datasets = tuple(
        DatasetIdentity(
            key=key,
            ifc_sha256=seed * 64,
            ground_truth_sha256="2" * 64,
            ids_sha256="3" * 64,
            building_context=tuple(sorted(context.items())),
            **_ground_truth_identity_fields(key),
        )
        for key, context in (
            (
                "predio",
                {
                    "building_type": "Residencial multifamiliar",
                    "bioclimatic_zone": "4A",
                },
            ),
            (
                "casa",
                {
                    "building_type": "Residencial unifamiliar",
                    "bioclimatic_zone": "4A",
                },
            ),
        )
    )
    return ExecutionIdentity(
        release_id="ifcqc-test",
        project_sha256="4" * 64,
        models_lock_sha256="5" * 64,
        datasets=datasets,
        replica_count=1,
        cache_enabled=False,
        prompt_version="v7.2",
        prompt_sha256="6" * 64,
        reuse_equivalent=True,
    )


class FakeOllama:
    def __init__(self, lock: ModelMatrixLock) -> None:
        self.base_url = "http://127.0.0.1:49152"
        self._digests = {model.name: model.digest for model in lock.models}
        self.pulls: list[str] = []

    def get_json(self, path: str) -> dict[str, object]:
        assert path == "/api/tags"
        return {
            "models": [
                {"name": name, "digest": digest}
                for name, digest in self._digests.items()
            ]
        }

    def pull_model(self, model: str) -> None:
        self.pulls.append(model)


class FakeServices:
    """Substitui somente rede, processos e inventario externo."""

    def __init__(self, lock: ModelMatrixLock) -> None:
        self.lock = lock
        self.ollama = FakeOllama(lock)
        self.commands: list[list[str]] = []
        self.model_store: Path | None = None
        self.downloads: list[str] = []
        self.hardware_failure = False
        self.llmfit_failure = False
        self.llmfit_download_failure = False
        self.runner_returncode = 0
        self.runner_interrupt = False

    def collect_inventory(self, **_kwargs: object) -> dict[str, object]:
        if self.hardware_failure:
            raise ValueError("hardware privado nao parseavel")
        return {
            "os": {"caption": "Windows 11", "build_number": "22631"},
            "computer": {"manufacturer": "Framework", "model": "Laptop 16"},
            "cpu": [{"name": "AMD Ryzen Test", "logical_processors": 16}],
            "memory": {"total_bytes": 32 * 1024**3, "modules": []},
            "gpu": [{"name": "NVIDIA RTX Test", "adapter_ram_bytes": 8 * 1024**3}],
            "storage": {"disks": [], "volumes": []},
            "display_drivers": [{"name": "NVIDIA RTX Test", "driver_version": "1"}],
            "power": {"active_scheme_name": "Balanced"},
            "bios": {"manufacturer": "Test"},
            "baseboard": {"manufacturer": "Test"},
            "nvidia_smi": {"status": "ok", "data": []},
            "dxdiag": {"status": "ok", "data": {"directx_version": "DirectX 12"}},
        }

    def run(self, command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.commands.append([str(part) for part in command])
        if any("build_ground_truths.py" in str(part) for part in command):
            return subprocess.CompletedProcess(command, 0, "GROUND_TRUTHS_OK\n", "")
        if self.runner_interrupt:
            raise KeyboardInterrupt
        self._write_twenty_pairs(command)
        log_path = kwargs.get("log_path")
        if isinstance(log_path, Path):
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text("runner simulated\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, self.runner_returncode, "runner\n", "")

    def _write_twenty_pairs(self, command: list[str]) -> None:
        identity_path = Path(command[command.index("--execution-identity") + 1])
        results_root = Path(command[command.index("--results-root") + 1])
        raw = json.loads(identity_path.read_text(encoding="utf-8"))
        identity = ExecutionIdentity(
            release_id=raw["release_id"],
            project_sha256=raw["project_sha256"],
            models_lock_sha256=raw["models_lock_sha256"],
            datasets=tuple(
                DatasetIdentity(
                    key=row["key"],
                    ifc_sha256=row["ifc_sha256"],
                    ground_truth_sha256=row["ground_truth_sha256"],
                    ids_sha256=row["ids_sha256"],
                    building_context=tuple(tuple(item) for item in row["building_context"]),
                    ground_truth_policy_version=row["ground_truth_policy_version"],
                    ground_truth_items=row["ground_truth_items"],
                    equivalence_classes=row["equivalence_classes"],
                    confidence_counts=tuple(
                        tuple(item) for item in row["confidence_counts"]
                    ),
                )
                for row in raw["datasets"]
            ),
            replica_count=raw["replica_count"],
            cache_enabled=raw["cache_enabled"],
            prompt_version=raw["prompt_version"],
            prompt_sha256=raw["prompt_sha256"],
            reuse_equivalent=raw["reuse_equivalent"],
        )
        for dataset in identity.datasets:
            for model in self.lock.models:
                expectation = _stage_expectation(
                    identity, dataset, model.name, model.digest, 0
                )
                aggregate = _stage_path(results_root, dataset.key, model.name, 0)
                aggregate.parent.mkdir(parents=True, exist_ok=True)
                aggregate.write_text(
                    json.dumps(
                        {
                            "metadata": asdict(expectation),
                            "issue_counts": {"total_issues": 1},
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                aggregate.with_name("run_0_issues.jsonl").write_text(
                    '{"issue_id":"simulated"}\n', encoding="utf-8"
                )

    def download_and_extract(
        self, specs: object, destination: Path, **_kwargs: object
    ) -> None:
        if "llmfit" in destination.as_posix() and self.llmfit_download_failure:
            raise OSError("llmfit auxiliar indisponivel")
        self.downloads.append(destination.as_posix())
        destination.mkdir(parents=True, exist_ok=True)
        if "ollama" in destination.as_posix():
            (destination / "ollama.exe").write_bytes(b"fake")
        else:
            (destination / "llmfit.exe").write_bytes(b"fake")

    def start_ollama(self, *, model_store: Path, **_kwargs: object) -> Any:
        self.model_store = model_store
        return nullcontext(self.ollama)

    def free_bytes(self, _path: Path) -> int:
        return 100 * 1024**3

    def run_llmfit(self, _executable: Path, output_dir: Path, **_kwargs: object) -> object:
        if self.llmfit_failure:
            raise ValueError("llmfit output privado")
        output_dir.mkdir(parents=True, exist_ok=True)
        payloads = {
            "system.json": {"system": {"backend": "CUDA"}},
            "recommend-2048.json": {"models": []},
            "recommend-8192.json": {"models": []},
            "recommend-extra-models.json": {"models": []},
        }
        for name, payload in payloads.items():
            (output_dir / name).write_text(
                json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8"
            )
        (output_dir / "doctor.txt").write_text("status: ok\n", encoding="utf-8")
        return SimpleNamespace(status="ok", extra_models=[])


@pytest.fixture
def release_fixture(tmp_path: Path) -> tuple[BenchmarkArgs, FakeServices]:
    package = tmp_path / "package"
    project = tmp_path / "app/releases/ifcqc-test"
    package.mkdir(parents=True)
    project.mkdir(parents=True)

    project_zip = package / "payload/project.zip"
    predio_package = package / "payload/datasets/predio_v1.ifc"
    casa_package = package / "payload/datasets/casa_v1.ifc"
    for path, payload in (
        (project_zip, b"project zip fixture"),
        (predio_package, b"predio fixture"),
        (casa_package, b"casa fixture"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    lock_path = project / "src/experiment/results/models.lock.json"
    prompt_path = project / "src/suggestion_engine/prompt_templates.py"
    ids_path = project / "data/ids_templates/residencial_nbr15575.ids"
    lock_path.parent.mkdir(parents=True)
    prompt_path.parent.mkdir(parents=True)
    ids_path.parent.mkdir(parents=True)
    lock_path.write_bytes(LOCK_SOURCE.read_bytes())
    prompt_path.write_text('PROMPT_VERSION = "v7.2"\n', encoding="utf-8")
    ids_path.write_text("<ids/>\n", encoding="utf-8")

    manifest_datasets: dict[str, dict[str, object]] = {}
    dataset_inputs: dict[str, dict[str, object]] = {}
    for key, package_ifc in (("predio", predio_package), ("casa", casa_package)):
        evaluation = project / f"data/evaluation/{key}"
        evaluation.mkdir(parents=True)
        local_ifc = evaluation / f"{key}_v1.ifc"
        local_ifc.write_bytes(package_ifc.read_bytes())
        ground_truth = evaluation / "ground_truth.yaml"
        gt_metadata = _ground_truth_identity_fields(key)
        counts = dict(gt_metadata["confidence_counts"])
        ground_truth.write_text(
            "metadata:\n"
            "  protocol: full-coverage-equivalent-v1\n"
            f"  total_items: {gt_metadata['ground_truth_items']}\n"
            f"  equivalence_class_count: {gt_metadata['equivalence_classes']}\n"
            "  confidence_counts:\n"
            f"    high: {counts['high']}\n"
            f"    medium: {counts['medium']}\n"
            f"    low: {counts['low']}\n"
            "items: []\nskipped: []\n",
            encoding="utf-8",
        )
        manifest_datasets[key] = _record(package, package_ifc, key="path")
        dataset_inputs[key] = {
            "ifc": dict(manifest_datasets[key]),
            "ground_truth": _record(project, ground_truth, key="project_path"),
            "ids": _record(project, ids_path, key="project_path"),
        }

    manifest = json.loads(TEMPLATE_SOURCE.read_text(encoding="utf-8"))
    manifest.update(
        {
            "release_id": "ifcqc-test",
            "source_commit": "a" * 40,
            "project": _record(package, project_zip, key="path"),
            "datasets": manifest_datasets,
            "inputs": {
                "models_lock": _record(project, lock_path, key="project_path"),
                "prompt_templates": {
                    **_record(project, prompt_path, key="project_path"),
                    "version": "v7.2",
                },
                "datasets": dataset_inputs,
            },
        }
    )
    manifest_path = package / "release-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args = BenchmarkArgs(
        manifest=manifest_path,
        package_root=package,
        launch_dir=tmp_path / "launch",
        bootstrap_receipt=tmp_path / "bootstrap-receipt.json",
        project_root=project,
        app_root=tmp_path / "app",
        python_executable=Path("python.exe"),
    )
    args.launch_dir.mkdir()
    return args, FakeServices(load_model_lock(lock_path))


def test_incomplete_matching_run_is_resumed_and_tampering_is_not(tmp_path: Path) -> None:
    identity = _identity()
    first = select_or_create_run(tmp_path / "state", identity=identity)
    state_path = tmp_path / "state" / str(first.run_id) / "status.json"
    raw = json.loads(state_path.read_text(encoding="utf-8"))
    raw["status"] = "interrupted"
    state_path.write_text(json.dumps(raw), encoding="utf-8")

    assert select_or_create_run(tmp_path / "state", identity=identity).run_id == first.run_id

    raw["execution_identity"]["release_id"] = "tampered"
    state_path.write_text(json.dumps(raw), encoding="utf-8")
    assert select_or_create_run(tmp_path / "state", identity=identity).run_id != first.run_id

    changed = replace(identity, prompt_sha256="f" * 64)
    assert select_or_create_run(tmp_path / "state", identity=changed).run_id != first.run_id


def test_child_environment_preserves_system_and_forces_private_ollama(tmp_path: Path) -> None:
    base = {
        "PATH": r"C:\Windows\System32",
        "SYSTEMROOT": r"C:\Windows",
        "TEMP": str(tmp_path),
        "LANG": "pt_BR.UTF-8",
        "OLLAMA_HOST": "remote:11434",
        "OLLAMA_MODELS": r"D:\other",
        "OPENAI_API_KEY": "secret",
        "IFCQC_TOKEN": "secret-2",
    }

    merged = build_child_env(
        base,
        ollama_url="http://127.0.0.1:49152",
        model_store=tmp_path / "models",
    )

    assert {key: merged[key] for key in ("PATH", "SYSTEMROOT", "TEMP", "LANG")} == {
        key: base[key] for key in ("PATH", "SYSTEMROOT", "TEMP", "LANG")
    }
    assert merged["OLLAMA_HOST"] == "127.0.0.1:49152"
    assert merged["OLLAMA_URL"] == "http://127.0.0.1:49152"
    assert merged["OLLAMA_MODELS"] == str(tmp_path / "models")
    assert merged["NO_PROXY"] == "127.0.0.1,localhost,::1"
    assert "OPENAI_API_KEY" not in merged
    assert "IFCQC_TOKEN" not in merged


def test_identity_uses_manifest_records_and_real_payload_hashes(
    release_fixture: tuple[BenchmarkArgs, FakeServices],
) -> None:
    args, _ = release_fixture

    identity = build_execution_identity(args)

    assert identity.project_sha256 == _sha256(args.package_root / "payload/project.zip")
    assert identity.models_lock_sha256 == _sha256(
        args.project_root / "src/experiment/results/models.lock.json"
    )
    assert [dataset.key for dataset in identity.datasets] == ["predio", "casa"]
    assert identity.replica_count == 1
    assert identity.cache_enabled is False
    assert identity.reuse_equivalent is True

    local_ifc = args.project_root / "data/evaluation/casa/casa_v1.ifc"
    local_ifc.write_bytes(b"x" * local_ifc.stat().st_size)
    with pytest.raises(ValueError, match="SHA-256"):
        build_execution_identity(args)


def test_app_root_is_inferred_from_bootstrap_release_layout(
    release_fixture: tuple[BenchmarkArgs, FakeServices], monkeypatch: pytest.MonkeyPatch
) -> None:
    args, services = release_fixture
    bootstrap_args = replace(args, app_root=None)
    monkeypatch.setenv(
        "LOCALAPPDATA", str(args.project_root.parent.parent.parent / "wrong-local-appdata")
    )

    assert run_benchmark_release(bootstrap_args, services=services) == 0

    assert services.model_store is not None
    assert services.model_store.is_relative_to(args.project_root.parent.parent)


def test_happy_path_creates_private_zip_with_exact_twenty_pairs(
    release_fixture: tuple[BenchmarkArgs, FakeServices], monkeypatch: pytest.MonkeyPatch
) -> None:
    args, services = release_fixture
    monkeypatch.setenv("OPENAI_API_KEY", "process-secret-value")
    (args.project_root / ".env").write_text(
        "TOKEN=dotenv-secret-value\n", encoding="utf-8"
    )

    assert run_benchmark_release(args, services=services) == 0

    command = next(
        command
        for command in services.commands
        if "scripts/run_benchmark.py" in command[1].replace("\\", "/")
    )
    assert command[-8:] == [
        "--replicas",
        "1",
        "--no-cache",
        "--reuse-equivalent",
        "--execution-identity",
        command[-3],
        "--results-root",
        command[-1],
    ]
    assert services.model_store is not None
    assert services.model_store.is_relative_to(args.app_root)
    assert services.ollama.pulls == []

    receipt = json.loads(args.bootstrap_receipt.read_text(encoding="utf-8"))
    output = Path(receipt["zip_path"])
    assert receipt["status"] == "complete"
    assert output.is_file()
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        assert {
            "README.txt",
            "status.json",
            "manifest.json",
            "privacy-report.json",
            "hardware/windows.json",
            "hardware/cpu.json",
            "hardware/memory.json",
            "hardware/gpu.json",
            "hardware/storage.json",
            "hardware/drivers.json",
            "hardware/power.json",
            "software/versions.json",
            "software/python-lock.txt",
            "software/ollama-models.json",
            "software/input-hashes.json",
            "llmfit/system.json",
            "llmfit/recommend-2048.json",
            "llmfit/recommend-8192.json",
            "llmfit/recommend-extra-models.json",
            "llmfit/doctor.txt",
            "benchmark/runner.log",
        } <= names
        stage_json = {
            name.removesuffix(".json")
            for name in names
            if name.startswith("benchmark/results/")
            and name.endswith(".json")
            and not name.endswith("_issues.json")
        }
        stage_jsonl = {
            name.removesuffix("_issues.jsonl")
            for name in names
            if name.startswith("benchmark/results/") and name.endswith("_issues.jsonl")
        }
        assert len(stage_json) == 20
        assert stage_json == stage_jsonl
        packed = b"\n".join(archive.read(name) for name in names)
        assert b"process-secret-value" not in packed
        assert b"dotenv-secret-value" not in packed
        assert json.loads(archive.read("status.json"))["status"] == "complete"
        assert json.loads(archive.read("llmfit/system.json"))["system"]["backend"] == "CUDA"


def test_optional_inventory_failures_do_not_block_and_interrupt_is_resumable(
    release_fixture: tuple[BenchmarkArgs, FakeServices],
) -> None:
    args, services = release_fixture
    services.hardware_failure = True
    services.llmfit_download_failure = True
    services.runner_interrupt = True

    assert run_benchmark_release(args, services=services) == 130

    receipt = json.loads(args.bootstrap_receipt.read_text(encoding="utf-8"))
    state = load_run_state(Path(receipt["state_path"]))
    assert state.status == "interrupted"
    output = Path(receipt["zip_path"])
    with zipfile.ZipFile(output) as archive:
        assert json.loads(archive.read("hardware/windows.json"))["status"] == "unavailable"
        assert json.loads(archive.read("llmfit/system.json"))["status"] == "unavailable"
        assert json.loads(archive.read("status.json"))["status"] == "interrupted"


def test_bundle_privacy_failure_falls_back_to_minimal_partial(
    release_fixture: tuple[BenchmarkArgs, FakeServices], monkeypatch: pytest.MonkeyPatch
) -> None:
    args, services = release_fixture

    def fail_bundle(*_args: object, **_kwargs: object) -> Path:
        raise EvidencePrivacyError("scanner")

    monkeypatch.setattr("scripts.windows_benchmark.create_evidence_zip", fail_bundle)

    assert run_benchmark_release(args, services=services) == 1

    receipt = json.loads(args.bootstrap_receipt.read_text(encoding="utf-8"))
    with zipfile.ZipFile(receipt["zip_path"]) as archive:
        assert set(archive.namelist()) == {
            "README.txt",
            "status.json",
            "privacy-report.json",
            "manifest.json",
        }
        status = json.loads(archive.read("status.json"))
        assert status["partial"] is True
        assert status["reason_code"] == "PRIVACY_SCAN_FAILED"
