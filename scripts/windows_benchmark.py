"""Orquestra o benchmark oficial na release portatil para Windows x64.

O modulo mantem rede, processos e coleta de hardware em fronteiras injetaveis,
permitindo testar o caminho completo sem baixar modelos nem iniciar o Ollama.
"""

# ruff: noqa: E402 -- execucao direta exige incluir a raiz antes dos imports locais.

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal, cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_benchmark import _invalid_matrix_stages
from src.experiment.evidence_bundle import (
    FailureCode,
    collect_forbidden_values,
    create_evidence_zip,
    create_partial_evidence_zip,
    failure_code_for_exception,
)
from src.experiment.execution_identity import (
    DatasetIdentity,
    ExecutionIdentity,
    canonical_identity_sha256,
    load_ground_truth_identity_metadata,
)
from src.experiment.model_lock import (
    ModelMatrixLock,
    load_model_lock,
    required_free_bytes,
)
from src.experiment.windows_runtime import (
    LLMFIT_VERSION,
    OLLAMA_RUNTIME_RELATIVE,
    OLLAMA_VERSION,
    DownloadSpec,
    OllamaServer,
    RuntimeAssetPlan,
    RuntimeIntegrityError,
    download_verified,
    ensure_model_matrix,
    installed_model_digests,
    ollama_executable,
    safe_extract_zip,
    select_runtime_assets,
    validate_tool_pins,
)

LOCK_RELATIVE = Path("src/experiment/results/models.lock.json")
PROMPT_RELATIVE = Path("src/suggestion_engine/prompt_templates.py")
IDS_RELATIVE = Path("data/ids_templates/residencial_nbr15575.ids")
LLMFIT_RUNTIME_RELATIVE = Path(f"tools/llmfit/{LLMFIT_VERSION}")
RESULT_RESERVE_BYTES = 2 * 1024**3
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SECRET_ENV_RE = re.compile(
    r"(?:^OLLAMA_|TOKEN|SECRET|PASSWORD|API[_-]?KEY)", re.IGNORECASE
)
_INCOMPLETE_STATUSES = frozenset({"preparing", "running", "failed", "interrupted"})
_TOOL_MARKER = ".ifcqc-assets.json"

# Casos de fault injection e aceite em Windows real ficam para a etapa de
# endurecimento posterior ao MVP; o caminho feliz, retomada e privacidade sao
# cobertos em tests/windows/test_windows_benchmark.py.
MVP_PENDENCIAS = (
    "fault injection de cada dano possivel no JSONL",
    "aceite manual em Windows 10 22H2 e Windows 11",
    "teste real com NVIDIA, AMD/ROCm e maquina apenas CPU",
)


@dataclass(frozen=True)
class BenchmarkArgs:
    """Argumentos resolvidos pelo bootstrap PowerShell."""

    manifest: Path
    package_root: Path
    launch_dir: Path
    bootstrap_receipt: Path
    project_root: Path = PROJECT_ROOT
    app_root: Path | None = None
    python_executable: Path = Path(sys.executable)


@dataclass(frozen=True)
class AppPaths:
    """Diretorios app-owned usados sem alterar instalacoes globais."""

    app_root: Path
    release_root: Path
    download_cache: Path
    model_store: Path
    state_root: Path
    run_root: Path


@dataclass(frozen=True)
class Phase2Result:
    """Resultado do preflight Python anterior aos downloads pesados."""

    inventory: dict[str, object]
    assets: RuntimeAssetPlan
    ollama_bootstrap_bytes: int
    identity: ExecutionIdentity | None = None


@dataclass(frozen=True)
class RemainingBudget:
    """Componentes discriminados do espaco ainda necessario."""

    model_required_bytes: int
    auxiliary_required_bytes: int
    result_reserve_bytes: int = RESULT_RESERVE_BYTES

    @property
    def total_required_bytes(self) -> int:
        return (
            self.model_required_bytes
            + self.auxiliary_required_bytes
            + self.result_reserve_bytes
        )


class RunState(BaseModel):
    """Estado retomavel; entradas experimentais ficam no snapshot imutavel."""

    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    execution_identity: dict[str, object]
    execution_identity_sha256: str
    status: Literal["preparing", "running", "complete", "failed", "interrupted"]
    started_at_utc: datetime
    updated_at_utc: datetime
    results_root: str
    last_stage: str | None = None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_snapshot_sha256(snapshot: Mapping[str, object]) -> str:
    payload = json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _identity_snapshot(identity: ExecutionIdentity) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(json.dumps(asdict(identity), ensure_ascii=False, sort_keys=True)),
    )


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.partial")
    try:
        temporary.write_text(text, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json_atomic(path: Path, payload: object) -> None:
    _write_text_atomic(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} deve ser objeto")
    return cast(Mapping[str, object], value)


def _relative_member(value: object, *, expected: str, label: str) -> str:
    if value != expected:
        raise ValueError(f"{label} deve apontar para {expected}")
    if not isinstance(value, str):
        raise ValueError(f"{label} deve ser texto")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or "\\" in value or ":" in value:
        raise ValueError(f"{label} contem caminho inseguro")
    return value


def _validate_record(
    root: Path,
    record: Mapping[str, object],
    *,
    field: str,
    expected: str,
    label: str,
) -> tuple[Path, str]:
    relative = _relative_member(record.get(field), expected=expected, label=label)
    target = root / PurePosixPath(relative)
    resolved_root = root.resolve(strict=True)
    try:
        resolved = target.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, ValueError) as error:
        raise ValueError(f"{label} ausente ou fora da raiz permitida") from error
    size = record.get("size_bytes")
    expected_hash = record.get("sha256")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise ValueError(f"{label}.size_bytes invalido")
    if not isinstance(expected_hash, str) or _SHA256_RE.fullmatch(expected_hash) is None:
        raise ValueError(f"{label}.sha256 invalido")
    if resolved.stat().st_size != size:
        raise ValueError(f"Tamanho divergente em {label}")
    observed = _sha256(resolved)
    if observed != expected_hash:
        raise ValueError(f"SHA-256 divergente em {label}")
    return resolved, observed


def _load_manifest(path: Path) -> Mapping[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("manifesto de release invalido") from error
    return _mapping(raw, "manifesto")


def _coerce_args(args: BenchmarkArgs | argparse.Namespace) -> BenchmarkArgs:
    if isinstance(args, BenchmarkArgs):
        project_root = Path(args.project_root).resolve()
        app_root = _infer_app_root(project_root, args.app_root)
        return replace(
            args,
            manifest=Path(args.manifest).resolve(),
            package_root=Path(args.package_root).resolve(),
            launch_dir=Path(args.launch_dir).resolve(),
            bootstrap_receipt=Path(args.bootstrap_receipt).resolve(),
            project_root=project_root,
            app_root=Path(app_root).resolve(),
            python_executable=Path(args.python_executable),
        )
    project_root = Path(getattr(args, "project_root", PROJECT_ROOT)).resolve()
    return BenchmarkArgs(
        manifest=Path(args.manifest).resolve(),
        package_root=Path(args.package_root).resolve(),
        launch_dir=Path(args.launch_dir).resolve(),
        bootstrap_receipt=Path(args.bootstrap_receipt).resolve(),
        project_root=project_root,
        app_root=_infer_app_root(project_root, getattr(args, "app_root", None)),
        python_executable=Path(getattr(args, "python_executable", sys.executable)),
    )


def _default_app_root() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise RuntimeError("LOCALAPPDATA nao definido")
    return Path(local) / "IFCQualityCopilot"


def _infer_app_root(project_root: Path, explicit: object) -> Path:
    if explicit is not None:
        return Path(cast(Path | str, explicit)).resolve()
    if project_root.parent.name.casefold() == "releases":
        return project_root.parent.parent.resolve()
    return _default_app_root().resolve()


def build_execution_identity(args: BenchmarkArgs | argparse.Namespace) -> ExecutionIdentity:
    """Valida bytes reais e constroi a identidade oficial predio+casa."""

    resolved = _coerce_args(args)
    manifest = _load_manifest(resolved.manifest)
    release_id = manifest.get("release_id")
    if not isinstance(release_id, str) or not release_id.strip():
        raise ValueError("release_id ausente no manifesto")

    project_record = _mapping(manifest.get("project"), "manifesto.project")
    _, project_sha = _validate_record(
        resolved.package_root,
        project_record,
        field="path",
        expected="payload/project.zip",
        label="project.zip",
    )
    inputs = _mapping(manifest.get("inputs"), "manifesto.inputs")
    lock_record = _mapping(inputs.get("models_lock"), "inputs.models_lock")
    _, lock_sha = _validate_record(
        resolved.project_root,
        lock_record,
        field="project_path",
        expected=LOCK_RELATIVE.as_posix(),
        label="models.lock.json",
    )
    prompt_record = _mapping(inputs.get("prompt_templates"), "inputs.prompt_templates")
    _, prompt_sha = _validate_record(
        resolved.project_root,
        prompt_record,
        field="project_path",
        expected=PROMPT_RELATIVE.as_posix(),
        label="prompt_templates.py",
    )
    prompt_version = prompt_record.get("version")
    if not isinstance(prompt_version, str) or not prompt_version:
        raise ValueError("versao de prompt ausente")

    manifest_datasets = _mapping(manifest.get("datasets"), "manifesto.datasets")
    input_datasets = _mapping(inputs.get("datasets"), "inputs.datasets")
    contexts = {
        "predio": {
            "building_type": "Residencial multifamiliar",
            "bioclimatic_zone": "4A",
        },
        "casa": {
            "building_type": "Residencial unifamiliar",
            "bioclimatic_zone": "4A",
        },
    }
    frozen: list[DatasetIdentity] = []
    for key in ("predio", "casa"):
        expected_ifc = f"payload/datasets/{key}_v1.ifc"
        top_ifc = _mapping(manifest_datasets.get(key), f"datasets.{key}")
        _, ifc_sha = _validate_record(
            resolved.package_root,
            top_ifc,
            field="path",
            expected=expected_ifc,
            label=f"IFC {key} do payload",
        )
        dataset = _mapping(input_datasets.get(key), f"inputs.datasets.{key}")
        input_ifc = _mapping(dataset.get("ifc"), f"inputs.datasets.{key}.ifc")
        if dict(input_ifc) != dict(top_ifc):
            raise ValueError(f"registro IFC duplicado diverge para {key}")
        local_ifc = resolved.project_root / f"data/evaluation/{key}/{key}_v1.ifc"
        if not local_ifc.is_file() or local_ifc.stat().st_size != top_ifc.get("size_bytes"):
            raise ValueError(f"Tamanho divergente no IFC local {key}")
        if _sha256(local_ifc) != ifc_sha:
            raise ValueError(f"SHA-256 divergente no IFC local {key}")

        gt_record = _mapping(dataset.get("ground_truth"), f"{key}.ground_truth")
        gt_path, gt_sha = _validate_record(
            resolved.project_root,
            gt_record,
            field="project_path",
            expected=f"data/evaluation/{key}/ground_truth.yaml",
            label=f"ground truth {key}",
        )
        gt_metadata = load_ground_truth_identity_metadata(gt_path)
        ids_record = _mapping(dataset.get("ids"), f"{key}.ids")
        _, ids_sha = _validate_record(
            resolved.project_root,
            ids_record,
            field="project_path",
            expected=IDS_RELATIVE.as_posix(),
            label=f"IDS {key}",
        )
        frozen.append(
            DatasetIdentity(
                key=key,
                ifc_sha256=ifc_sha,
                ground_truth_sha256=gt_sha,
                ids_sha256=ids_sha,
                building_context=tuple(sorted(contexts[key].items())),
                ground_truth_policy_version=(
                    gt_metadata.ground_truth_policy_version
                ),
                ground_truth_items=gt_metadata.ground_truth_items,
                equivalence_classes=gt_metadata.equivalence_classes,
                confidence_counts=gt_metadata.confidence_counts,
            )
        )

    if frozen[0].ids_sha256 != frozen[1].ids_sha256:
        raise ValueError("IDS deve ser identico para predio e casa")
    return ExecutionIdentity(
        release_id=release_id,
        project_sha256=project_sha,
        models_lock_sha256=lock_sha,
        datasets=tuple(frozen),
        replica_count=1,
        cache_enabled=False,
        prompt_version=prompt_version,
        prompt_sha256=prompt_sha,
        reuse_equivalent=True,
    )


def _state_path(state_root: Path, run_id: UUID) -> Path:
    return state_root / str(run_id) / "status.json"


def load_run_state(path: Path) -> RunState:
    """Carrega state estrito; corrupcao nunca e tratada como retomavel."""

    raw = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    return RunState.model_validate(raw)


def _persist_state(state_root: Path, state: RunState) -> Path:
    path = _state_path(state_root, state.run_id)
    _write_json_atomic(path, state.model_dump(mode="json"))
    return path


def select_or_create_run(
    state_root: Path,
    *,
    identity: ExecutionIdentity,
    run_root: Path | None = None,
) -> RunState:
    """Retoma somente snapshot integro, incompleto e byte-equivalente."""

    state_root = state_root.resolve()
    resolved_run_root = (run_root or state_root.parent / "run-data").resolve()
    snapshot = _identity_snapshot(identity)
    identity_sha = canonical_identity_sha256(identity)
    candidates: list[RunState] = []
    if state_root.is_dir():
        for path in state_root.glob("*/status.json"):
            try:
                state = load_run_state(path)
                expected_results = resolved_run_root / str(state.run_id) / "results"
                if (
                    state.status in _INCOMPLETE_STATUSES
                    and state.execution_identity_sha256 == identity_sha
                    and _canonical_snapshot_sha256(state.execution_identity)
                    == state.execution_identity_sha256
                    and state.execution_identity == snapshot
                    and Path(state.results_root).resolve() == expected_results
                ):
                    candidates.append(state)
            except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
                continue
    if candidates:
        return max(candidates, key=lambda item: item.updated_at_utc)

    now = _utc_now()
    run_id = uuid4()
    state = RunState(
        run_id=run_id,
        execution_identity=snapshot,
        execution_identity_sha256=identity_sha,
        status="preparing",
        started_at_utc=now,
        updated_at_utc=now,
        results_root=str(resolved_run_root / str(run_id) / "results"),
    )
    _persist_state(state_root, state)
    return state


def build_child_env(
    base: Mapping[str, str], *, ollama_url: str, model_store: Path
) -> dict[str, str]:
    """Preserva o ambiente do sistema, remove segredos e fixa Ollama loopback."""

    parsed = urlsplit(ollama_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Ollama deve usar HTTP loopback privado")
    if parsed.port is None or parsed.path not in {"", "/"}:
        raise ValueError("URL Ollama invalida")
    merged = {
        str(key): str(value)
        for key, value in base.items()
        if not _SECRET_ENV_RE.search(str(key))
    }
    merged.update(
        {
            "OLLAMA_URL": ollama_url.rstrip("/"),
            "OLLAMA_HOST": f"{parsed.hostname}:{parsed.port}",
            "OLLAMA_MODELS": str(model_store),
            "NO_PROXY": "127.0.0.1,localhost,::1",
        }
    )
    return merged


def _paths_for(args: BenchmarkArgs, identity: ExecutionIdentity) -> AppPaths:
    if args.app_root is None:
        raise RuntimeError("app_root nao resolvido")
    app_root = args.app_root.resolve()
    return AppPaths(
        app_root=app_root,
        release_root=app_root,
        download_cache=app_root / "downloads",
        model_store=app_root / "models" / identity.models_lock_sha256,
        state_root=app_root / "state" / "runs",
        run_root=app_root / "runs",
    )


def _marker_has(destination: Path, specs: Sequence[DownloadSpec]) -> bool:
    marker = destination / _TOOL_MARKER
    try:
        raw = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    expected = sorted(spec.sha256 for spec in specs)
    return raw == {"sha256": expected}


def remaining_auxiliary_bytes(asset: DownloadSpec, paths: AppPaths) -> int:
    """Reserva download+extracao do llmfit somente quando ainda ausente."""

    destination = paths.release_root / LLMFIT_RUNTIME_RELATIVE
    executable = destination / "llmfit.exe"
    if executable.is_file() and _marker_has(destination, (asset,)):
        return 0
    return 2 * asset.size_bytes


def _gpu_names(inventory: Mapping[str, object]) -> list[str]:
    value = inventory.get("gpu")
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for row in value:
        if isinstance(row, Mapping) and isinstance(row.get("name"), str):
            names.append(cast(str, row["name"]))
    return names


def _returncode(result: object) -> int:
    if isinstance(result, int):
        return result
    code = getattr(result, "returncode", None)
    if isinstance(code, int):
        return code
    raise TypeError("runner deve retornar int ou CompletedProcess")


def _free_bytes(services: object, path: Path) -> int:
    method = getattr(services, "free_bytes", None)
    if method is not None:
        value = method(path)
    else:
        path.mkdir(parents=True, exist_ok=True)
        value = shutil.disk_usage(path).free
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RuntimeError("consulta de espaco retornou valor invalido")
    return value


def _assert_free(services: object, path: Path, required: int) -> None:
    available = _free_bytes(services, path)
    if available < required:
        raise RuntimeIntegrityError(
            f"espaco insuficiente: necessario {required} bytes, disponivel {available}"
        )


class DefaultServices:
    """Fronteiras reais usadas pelo executavel produzido."""

    commands = staticmethod(subprocess.run)

    def run(
        self,
        command: list[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        log_path: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=dict(env) if env is not None else None,
            text=True,
            capture_output=True,
            check=False,
        )
        if log_path is not None:
            _write_text_atomic(log_path, (result.stdout or "") + (result.stderr or ""))
        return result

    def collect_inventory(
        self, *, project_root: Path, forbidden_values: set[str]
    ) -> dict[str, object]:
        from src.experiment.windows_inventory import collect_windows_inventory

        return cast(
            dict[str, object],
            collect_windows_inventory(
                self.commands,
                powershell_script=project_root / "windows/collect-hardware.ps1",
                forbidden_values=forbidden_values,
            ),
        )

    def download_and_extract(
        self,
        specs: Sequence[DownloadSpec],
        destination: Path,
        *,
        paths: AppPaths,
    ) -> None:
        specs = tuple(specs)
        archives: list[Path] = []
        for spec in specs:
            archive = paths.download_cache / f"{spec.sha256}.zip"
            archives.append(
                download_verified(spec, archive, app_root=paths.app_root)
            )
        expected_executable = (
            destination / "ollama.exe"
            if "ollama" in destination.as_posix().casefold()
            else destination / "llmfit.exe"
        )
        if expected_executable.is_file() and _marker_has(destination, specs):
            return
        for archive in archives:
            safe_extract_zip(archive, destination, app_root=paths.app_root)
        _write_json_atomic(
            destination / _TOOL_MARKER,
            {"sha256": sorted(spec.sha256 for spec in specs)},
        )

    def start_ollama(self, *, executable: Path, model_store: Path) -> OllamaServer:
        return OllamaServer(executable, model_store)

    def free_bytes(self, path: Path) -> int:
        path.mkdir(parents=True, exist_ok=True)
        return shutil.disk_usage(path).free

    def run_llmfit(
        self,
        executable: Path,
        output_dir: Path,
        *,
        locked_names: set[str],
        forbidden_values: set[str],
    ) -> object:
        from src.experiment.windows_inventory import run_llmfit_inventory

        return run_llmfit_inventory(
            executable,
            output_dir,
            runner=self.commands,
            locked_names=locked_names,
            forbidden_values=forbidden_values,
        )


def _service_run(
    services: object,
    command: list[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    log_path: Path | None = None,
) -> object:
    method = cast(DefaultServices, services).run
    return method(command, cwd=cwd, env=env, log_path=log_path)


def run_preflight_phase2(
    args: BenchmarkArgs | argparse.Namespace,
    paths: AppPaths,
    services: object,
    *,
    identity: ExecutionIdentity | None = None,
    forbidden_values: set[str] | None = None,
    log_path: Path | None = None,
) -> Phase2Result:
    """Revalida release/GT/inventario/espaco sem baixar ferramentas."""

    resolved = _coerce_args(args)
    manifest = _load_manifest(resolved.manifest)
    validate_tool_pins(manifest)
    frozen = identity or build_execution_identity(resolved)
    gt_result = _service_run(
        services,
        [
            str(resolved.python_executable),
            str(resolved.project_root / "scripts/build_ground_truths.py"),
            "--check",
            "--dataset",
            "all",
        ],
        cwd=resolved.project_root,
        log_path=log_path,
    )
    if _returncode(gt_result) != 0:
        raise RuntimeIntegrityError("checagem dos ground truths falhou")

    inventory_method = getattr(services, "collect_inventory", None)
    try:
        if inventory_method is None:
            inventory = DefaultServices().collect_inventory(
                project_root=resolved.project_root,
                forbidden_values=forbidden_values or set(),
            )
        else:
            inventory = inventory_method(
                project_root=resolved.project_root,
                forbidden_values=forbidden_values or set(),
            )
        if not isinstance(inventory, dict):
            raise TypeError("inventario deve ser objeto")
    except Exception:
        inventory = {"status": "unavailable", "error_type": "ParseError"}

    assets = select_runtime_assets(_gpu_names(inventory))
    ollama_ready = ollama_executable(paths.release_root).is_file() and _marker_has(
        paths.release_root / OLLAMA_RUNTIME_RELATIVE, tuple(assets.ollama)
    )
    missing_archives = 0 if ollama_ready else sum(asset.size_bytes for asset in assets.ollama)
    bootstrap_bytes = 3 * missing_archives + RESULT_RESERVE_BYTES
    _assert_free(services, paths.app_root, bootstrap_bytes)
    return Phase2Result(
        inventory=inventory,
        assets=assets,
        ollama_bootstrap_bytes=bootstrap_bytes,
        identity=frozen,
    )


def _download_and_extract(
    services: object,
    specs: Sequence[DownloadSpec],
    destination: Path,
    paths: AppPaths,
) -> None:
    method = getattr(services, "download_and_extract", None)
    if method is None:
        DefaultServices().download_and_extract(specs, destination, paths=paths)
    else:
        method(specs, destination, paths=paths)


def _start_ollama(
    services: object, executable: Path, model_store: Path
) -> AbstractContextManager[object]:
    method = getattr(services, "start_ollama", None)
    if method is None:
        return DefaultServices().start_ollama(
            executable=executable, model_store=model_store
        )
    return cast(
        AbstractContextManager[object],
        method(executable=executable, model_store=model_store),
    )


def _run_llmfit(
    services: object,
    executable: Path,
    output_dir: Path,
    *,
    locked_names: set[str],
    forbidden_values: set[str],
) -> object:
    method = getattr(services, "run_llmfit", None)
    if method is None:
        return DefaultServices().run_llmfit(
            executable,
            output_dir,
            locked_names=locked_names,
            forbidden_values=forbidden_values,
        )
    return method(
        executable,
        output_dir,
        locked_names=locked_names,
        forbidden_values=forbidden_values,
    )


def _write_unavailable_llmfit(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    unavailable = {"status": "unavailable", "error_type": "ParseError"}
    for name in (
        "system.json",
        "recommend-2048.json",
        "recommend-8192.json",
        "recommend-extra-models.json",
    ):
        if not (output_dir / name).is_file():
            _write_json_atomic(output_dir / name, unavailable)
    doctor = output_dir / "doctor.txt"
    if not doctor.is_file():
        _write_text_atomic(doctor, "status: unavailable; error_type: ParseError\n")


def _safe_inventory_documents(inventory: Mapping[str, object]) -> dict[str, object]:
    if inventory.get("status") == "unavailable":
        unavailable = {"status": "unavailable", "error_type": "ParseError"}
        return {name: unavailable for name in (
            "windows", "cpu", "memory", "gpu", "storage", "drivers", "power"
        )}
    return {
        "windows": {
            "os": inventory.get("os", {}),
            "computer": inventory.get("computer", {}),
            "bios": inventory.get("bios", {}),
            "baseboard": inventory.get("baseboard", {}),
        },
        "cpu": inventory.get("cpu", []),
        "memory": inventory.get("memory", {}),
        "gpu": {
            "controllers": inventory.get("gpu", []),
            "nvidia_smi": inventory.get("nvidia_smi", {}),
            "dxdiag": inventory.get("dxdiag", {}),
        },
        "storage": inventory.get("storage", {}),
        "drivers": inventory.get("display_drivers", []),
        "power": inventory.get("power", {}),
    }


def _clear_evidence_root(evidence_root: Path, run_directory: Path) -> None:
    if not evidence_root.exists():
        evidence_root.mkdir(parents=True)
        return
    try:
        evidence_root.resolve().relative_to(run_directory.resolve())
    except ValueError as error:
        raise RuntimeError("evidence root fora do run app-owned") from error
    shutil.rmtree(evidence_root)
    evidence_root.mkdir(parents=True)


def _reset_run_subdirectory(directory: Path, run_directory: Path) -> None:
    if directory.exists():
        try:
            directory.resolve().relative_to(run_directory.resolve())
        except ValueError as error:
            raise RuntimeError("diretorio auxiliar fora do run app-owned") from error
        shutil.rmtree(directory)
    directory.mkdir(parents=True)


def _copy_complete_results(
    source: Path,
    destination: Path,
    identity: ExecutionIdentity,
    lock: ModelMatrixLock,
) -> None:
    for dataset in identity.datasets:
        for model in lock.models:
            safe_model = re.sub(r"[^a-zA-Z0-9_.-]", "_", model.name)
            stage = source / dataset.key / safe_model / "run_0.json"
            issues = stage.with_name("run_0_issues.jsonl")
            relative = stage.relative_to(source)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(stage, target)
            shutil.copyfile(issues, target.with_name("run_0_issues.jsonl"))


def _materialize_evidence(
    *,
    evidence_root: Path,
    run_directory: Path,
    state: RunState,
    status: str,
    identity: ExecutionIdentity,
    lock: ModelMatrixLock,
    inventory: Mapping[str, object],
    invalid_stages: list[str],
    project_root: Path,
    results_root: Path,
    runner_log: Path,
    llmfit_source: Path,
    forbidden_value_count: int,
) -> None:
    _clear_evidence_root(evidence_root, run_directory)
    _write_text_atomic(
        evidence_root / "README.txt",
        "IFC Quality Copilot - evidencia anonima do benchmark predio+casa.\n",
    )
    _write_json_atomic(
        evidence_root / "status.json",
        {
            "execution_identity_sha256": state.execution_identity_sha256,
            "expected_stages": 20,
            "invalid_stages": invalid_stages,
            "run_id": str(state.run_id),
            "status": status,
            "validated_stages": 20 if status == "complete" else 0,
        },
    )
    _write_json_atomic(
        evidence_root / "privacy-report.json",
        {
            "forbidden_value_count": forbidden_value_count,
            "raw_binary_files_included": False,
            "status": "sanitized-before-publication",
        },
    )
    hardware = evidence_root / "hardware"
    for name, payload in _safe_inventory_documents(inventory).items():
        _write_json_atomic(hardware / f"{name}.json", payload)

    software = evidence_root / "software"
    _write_json_atomic(
        software / "versions.json",
        {
            "ollama": OLLAMA_VERSION,
            "llmfit": LLMFIT_VERSION,
            "python": platform.python_version(),
            "release_id": identity.release_id,
        },
    )
    uv_lock = project_root / "uv.lock"
    _write_text_atomic(
        software / "python-lock.txt",
        uv_lock.read_text(encoding="utf-8", errors="strict")
        if uv_lock.is_file()
        else "status: unavailable\n",
    )
    _write_json_atomic(
        software / "ollama-models.json",
        {
            "models": [
                {"name": model.name, "digest": model.digest, "size_bytes": model.size_bytes}
                for model in lock.models
            ]
        },
    )
    _write_json_atomic(software / "input-hashes.json", _identity_snapshot(identity))

    benchmark = evidence_root / "benchmark"
    benchmark.mkdir(parents=True, exist_ok=True)
    if runner_log.is_file():
        shutil.copyfile(runner_log, benchmark / "runner.log")
    else:
        _write_text_atomic(benchmark / "runner.log", "runner nao iniciado\n")
    if status == "complete":
        _copy_complete_results(
            results_root, benchmark / "results", identity, lock
        )
    llmfit_target = evidence_root / "llmfit"
    llmfit_target.mkdir(parents=True, exist_ok=True)
    for name in (
        "system.json",
        "recommend-2048.json",
        "recommend-8192.json",
        "recommend-extra-models.json",
        "doctor.txt",
    ):
        source = llmfit_source / name
        if source.is_file():
            shutil.copyfile(source, llmfit_target / name)
    _write_unavailable_llmfit(llmfit_target)


def _output_name(state: RunState) -> str:
    stamp = state.started_at_utc.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"RESULTADO_IFCQC_{stamp}_{state.run_id}.zip"


def _publish_to_launch(source: Path, launch_dir: Path) -> Path:
    try:
        if not launch_dir.is_dir():
            return source
        destination = launch_dir / source.name
        temporary = destination.with_suffix(destination.suffix + ".partial")
        try:
            shutil.copyfile(source, temporary)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination
    except OSError:
        return source


def _write_receipt(
    path: Path,
    *,
    state: RunState,
    state_path: Path,
    status: str,
    exit_code: int,
    zip_path: Path,
) -> None:
    _write_json_atomic(
        path,
        {
            "exit_code": exit_code,
            "run_id": str(state.run_id),
            "state_path": str(state_path),
            "status": status,
            "zip_path": str(zip_path),
        },
    )


def _emergency_partial(args: BenchmarkArgs, reason: FailureCode) -> int:
    """Garante receipt/ZIP minimo quando a identidade nem pode ser criada."""

    app_root = args.app_root or _default_app_root()
    output_root = Path(app_root) / "runs" / "preflight-failures"
    output_root.mkdir(parents=True, exist_ok=True)
    output = output_root / f"RESULTADO_IFCQC_{_utc_now():%Y%m%dT%H%M%SZ}_{uuid4()}.zip"
    create_partial_evidence_zip(output, status="failed", reason_code=reason)
    published = _publish_to_launch(output, args.launch_dir)
    _write_json_atomic(
        args.bootstrap_receipt,
        {"exit_code": 1, "status": "failed", "zip_path": str(published)},
    )
    return 1


def run_benchmark_release(
    args: BenchmarkArgs | argparse.Namespace, *, services: object | None = None
) -> int:
    """Executa preflight, runtime privado, matriz oficial e bundle anonimo."""

    resolved = _coerce_args(args)
    active_services = services or DefaultServices()
    try:
        identity = build_execution_identity(resolved)
    except Exception:
        return _emergency_partial(resolved, FailureCode.PHASE2_PREFLIGHT_FAILED)

    paths = _paths_for(resolved, identity)
    for directory in (
        paths.app_root,
        paths.download_cache,
        paths.model_store,
        paths.state_root,
        paths.run_root,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    state = select_or_create_run(
        paths.state_root, identity=identity, run_root=paths.run_root
    )
    state_path = _state_path(paths.state_root, state.run_id)
    run_directory = paths.run_root / str(state.run_id)
    results_root = Path(state.results_root)
    evidence_root = run_directory / "evidence"
    llmfit_root = run_directory / "llmfit"
    runner_log = run_directory / "runner.log"
    identity_path = run_directory / "execution-identity.json"
    _write_json_atomic(identity_path, _identity_snapshot(identity))
    lock = load_model_lock(resolved.project_root / LOCK_RELATIVE)

    forbidden_values = collect_forbidden_values(
        os.environ,
        dotenv_paths=(resolved.project_root / ".env",),
        base_values=(
            getpass.getuser(),
            platform.node(),
            str(Path.home()),
            os.environ.get("USERPROFILE", ""),
        ),
    )
    status: Literal["complete", "failed", "interrupted"] = "failed"
    exit_code = 1
    invalid_stages: list[str] = []
    inventory: Mapping[str, object] = {
        "status": "unavailable",
        "error_type": "ParseError",
    }
    failure_code = FailureCode.PHASE2_PREFLIGHT_FAILED

    try:
        phase2 = run_preflight_phase2(
            resolved,
            paths,
            active_services,
            identity=identity,
            forbidden_values=forbidden_values,
            log_path=runner_log,
        )
        inventory = phase2.inventory
        failure_code = FailureCode.TOOL_DOWNLOAD_FAILED
        ollama_destination = paths.release_root / OLLAMA_RUNTIME_RELATIVE
        _download_and_extract(
            active_services, tuple(phase2.assets.ollama), ollama_destination, paths
        )
        executable = ollama_executable(paths.release_root)
        if not executable.is_file():
            raise RuntimeIntegrityError(
                f"executavel Ollama ausente: {OLLAMA_RUNTIME_RELATIVE.as_posix()}"
            )

        with _start_ollama(active_services, executable, paths.model_store) as ollama:
            installed = installed_model_digests(ollama)
            drifts = [
                f"digest divergente para {model.name}"
                for model in lock.models
                if model.name in installed and installed[model.name] != model.digest
            ]
            if drifts:
                raise RuntimeIntegrityError("; ".join(drifts))
            budget = RemainingBudget(
                model_required_bytes=required_free_bytes(lock, installed),
                auxiliary_required_bytes=remaining_auxiliary_bytes(
                    phase2.assets.llmfit, paths
                ),
            )
            _assert_free(active_services, paths.model_store, budget.total_required_bytes)
            failure_code = FailureCode.MODEL_PULL_FAILED
            ensure_model_matrix(lock, ollama)
            installed = installed_model_digests(ollama)
            if any(installed.get(model.name) != model.digest for model in lock.models):
                raise RuntimeIntegrityError("matriz Ollama final diverge do lock")

            llmfit_destination = paths.release_root / LLMFIT_RUNTIME_RELATIVE
            _reset_run_subdirectory(llmfit_root, run_directory)
            try:
                _download_and_extract(
                    active_services,
                    (phase2.assets.llmfit,),
                    llmfit_destination,
                    paths,
                )
                _run_llmfit(
                    active_services,
                    llmfit_destination / "llmfit.exe",
                    llmfit_root,
                    locked_names={model.name for model in lock.models},
                    forbidden_values=forbidden_values,
                )
            except Exception:
                _write_unavailable_llmfit(llmfit_root)

            state = state.model_copy(
                update={"status": "running", "updated_at_utc": _utc_now()}
            )
            _persist_state(paths.state_root, state)
            command = [
                str(resolved.python_executable),
                str(resolved.project_root / "scripts/run_benchmark.py"),
                "--replicas",
                "1",
                "--no-cache",
                "--reuse-equivalent",
                "--execution-identity",
                str(identity_path),
                "--results-root",
                str(results_root),
            ]
            failure_code = FailureCode.RUNNER_FAILED
            runner = _service_run(
                active_services,
                command,
                cwd=resolved.project_root,
                env=build_child_env(
                    os.environ,
                    ollama_url=cast(OllamaServer, ollama).base_url,
                    model_store=paths.model_store,
                ),
                log_path=runner_log,
            )
            runner_code = _returncode(runner)

        if runner_code == 130:
            status, exit_code = "interrupted", 130
            failure_code = FailureCode.INTERRUPTED
        elif runner_code != 0:
            status, exit_code = "failed", 1
        else:
            invalid_stages = _invalid_matrix_stages(
                results_root,
                identity,
                [(model.name, model.digest) for model in lock.models],
            )
            if invalid_stages:
                status, exit_code = "failed", 1
            else:
                status, exit_code = "complete", 0
    except KeyboardInterrupt:
        status, exit_code = "interrupted", 130
        failure_code = FailureCode.INTERRUPTED
    except Exception as error:
        status, exit_code = "failed", 1
        if not runner_log.is_file():
            _write_text_atomic(
                runner_log,
                f"{failure_code.value}: {type(error).__name__}: {error}\n",
            )
    finally:
        last_stage = "casa/qwen3.5:9b/run_0" if status == "complete" else None
        state = state.model_copy(
            update={
                "status": status,
                "updated_at_utc": _utc_now(),
                "last_stage": last_stage,
            }
        )
        _persist_state(paths.state_root, state)
        output = run_directory / _output_name(state)
        try:
            _materialize_evidence(
                evidence_root=evidence_root,
                run_directory=run_directory,
                state=state,
                status=status,
                identity=identity,
                lock=lock,
                inventory=inventory,
                invalid_stages=invalid_stages,
                project_root=resolved.project_root,
                results_root=results_root,
                runner_log=runner_log,
                llmfit_source=llmfit_root,
                forbidden_value_count=len(forbidden_values),
            )
            create_evidence_zip(
                evidence_root,
                output,
                forbidden_values=forbidden_values,
            )
        except Exception as bundle_error:
            status, exit_code = "failed", 1
            state = state.model_copy(
                update={"status": "failed", "updated_at_utc": _utc_now()}
            )
            _persist_state(paths.state_root, state)
            create_partial_evidence_zip(
                output,
                status="failed",
                reason_code=failure_code_for_exception(bundle_error),
            )
        published = _publish_to_launch(output, resolved.launch_dir)
        _write_receipt(
            resolved.bootstrap_receipt,
            state=state,
            state_path=state_path,
            status=status,
            exit_code=exit_code,
            zip_path=published,
        )
    return exit_code


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--launch-dir", type=Path, required=True)
    parser.add_argument("--bootstrap-receipt", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--app-root", type=Path, default=None)
    parser.add_argument("--python-executable", type=Path, default=Path(sys.executable))
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI consumida por install.ps1."""

    return run_benchmark_release(_build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
