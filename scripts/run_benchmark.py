"""Executa a matriz oficial do benchmark com retomada integral e auditável.

Cada estágio é considerado concluído somente quando o agregado JSON e o
JSONL por issue formam um par íntegro cuja identidade experimental coincide
com o snapshot fornecido pelo instalador portátil.
"""

# ruff: noqa: E402 -- a CLI precisa inserir a raiz antes dos imports do projeto.

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import stat
import sys
import time
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast
from uuid import UUID, uuid4

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import psutil
from loguru import logger
from pydantic import BaseModel, ConfigDict

from src.experiment.execution_identity import (
    DatasetIdentity,
    ExecutionIdentity,
    canonical_identity_sha256,
    load_ground_truth_identity_metadata,
)
from src.experiment.model_lock import load_model_lock
from src.experiment.runner import ExperimentRunner, _sanitize
from src.suggestion_engine.prompt_templates import PROMPT_VERSION

STOP_FILE = PROJECT_ROOT / "BENCHMARK_STOP"
PID_FILE = PROJECT_ROOT / "BENCHMARK_RUNNING"
LOCK_FILE = PROJECT_ROOT / "src" / "experiment" / "results" / "models.lock.json"
IDS_PATH = PROJECT_ROOT / "data" / "ids_templates" / "residencial_nbr15575.ids"
EVAL_ROOT = PROJECT_ROOT / "data" / "evaluation"
PROMPT_FILE = PROJECT_ROOT / "src" / "suggestion_engine" / "prompt_templates.py"

DATASETS: list[dict[str, Any]] = [
    {
        "key": "predio",
        "ifc": EVAL_ROOT / "predio" / "predio_v1.ifc",
        "gt": EVAL_ROOT / "predio" / "ground_truth.yaml",
        "issue_types": None,
        "building_context": {
            "building_type": "Residencial multifamiliar",
            "bioclimatic_zone": "4A",
        },
    },
    {
        "key": "casa",
        "ifc": EVAL_ROOT / "casa" / "casa_v1.ifc",
        "gt": EVAL_ROOT / "casa" / "ground_truth.yaml",
        "issue_types": None,
        "building_context": {
            "building_type": "Residencial unifamiliar",
            "bioclimatic_zone": "4A",
        },
    },
]

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STAGE_JSON_RE = re.compile(r"^run_\d+\.json$")
_STAGE_JSONL_RE = re.compile(r"^run_\d+_issues\.jsonl$")
_WINDOWS_REPARSE_POINT = 0x400


@dataclass(frozen=True)
class StageExpectation:
    """Campos congelados que tornam um par de saída reutilizável."""

    dataset_key: str
    model_name: str
    model_digest: str
    replica_index: int
    execution_identity: dict[str, object]
    execution_identity_sha256: str
    ifc_sha256: str
    ground_truth_sha256: str
    ids_sha256: str
    prompt_version: str
    cache_enabled: bool
    reuse_equivalent: bool
    building_context: dict[str, str]
    ground_truth_policy_version: str
    ground_truth_items: int
    ground_truth_equivalence_classes: int
    ground_truth_confidence_counts: dict[str, int]


@dataclass(frozen=True)
class StopBaseline:
    """Fingerprint do arquivo STOP no instante de lançamento."""

    exists: bool
    mtime_ns: int | None
    size_bytes: int | None
    sha256: str | None


@dataclass(frozen=True)
class PidLease:
    """Lease exclusivo de uma fila, identificado por token imprevisível."""

    pid: int
    create_time: float
    token: str


class QuarantineMember(BaseModel):
    """Membro existente do par no início de uma transação."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["aggregate", "issues"]
    source_relative: str
    size_bytes: int
    sha256: str


class QuarantineJournal(BaseModel):
    """Journal persistente de uma mudança de par para a quarentena."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    transaction_id: UUID
    state: Literal["prepared", "moving", "recovery_required", "finalized"]
    results_root_relative: str
    staging_relative: str
    final_relative: str
    members: tuple[QuarantineMember, ...]


class QuarantineRecoveryError(RuntimeError):
    """A fila não pode executar enquanto a transação não for reconciliada."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _locked_models() -> list[str]:
    """Retorna a ordem validada da matriz oficial."""
    return [entry.name for entry in load_model_lock(LOCK_FILE).models]


def _locked_digests() -> dict[str, str]:
    """Retorna os digests completos da matriz validada."""
    return {entry.name: entry.digest for entry in load_model_lock(LOCK_FILE).models}


def _require_exact_keys(value: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} possui campos ausentes ou extras")
    return value


def _parse_execution_identity(raw: object) -> ExecutionIdentity:
    identity_data = _require_exact_keys(
        raw,
        {
            "release_id",
            "project_sha256",
            "models_lock_sha256",
            "datasets",
            "replica_count",
            "cache_enabled",
            "prompt_version",
            "prompt_sha256",
            "reuse_equivalent",
            # Acrescentados em 2026-08-12: parametros de geracao e politica de
            # janela entram na identidade, porque mudam o resultado.
            "source_commit",
            "num_ctx_policy",
            "num_ctx",
            "num_predict",
            "seed",
            "temperature",
            "top_p",
            "repeat_penalty",
            # Acrescentado em 2026-08-18: sem ele, a rodada de ablação de
            # grounding teria identidade idêntica à baseline e seus estágios
            # seriam pulados como "já concluídos".
            "grounding_bsdd",
        },
        "execution_identity",
    )
    if not isinstance(identity_data["release_id"], str):
        raise TypeError("release_id deve ser string")
    if type(identity_data["replica_count"]) is not int:
        raise TypeError("replica_count deve ser inteiro")
    if type(identity_data["cache_enabled"]) is not bool:
        raise TypeError("cache_enabled deve ser booleano")
    if type(identity_data["reuse_equivalent"]) is not bool:
        raise TypeError("reuse_equivalent deve ser booleano")
    if type(identity_data["grounding_bsdd"]) is not bool:
        raise TypeError("grounding_bsdd deve ser booleano")
    if not isinstance(identity_data["prompt_version"], str):
        raise TypeError("prompt_version deve ser string")
    for chave in ("source_commit", "num_ctx_policy"):
        if not isinstance(identity_data[chave], str):
            raise TypeError(f"{chave} deve ser string")
    for chave in ("num_ctx", "num_predict"):
        if type(identity_data[chave]) is not int:
            raise TypeError(f"{chave} deve ser inteiro")
    if identity_data["seed"] is not None and type(identity_data["seed"]) is not int:
        raise TypeError("seed deve ser inteiro ou nulo")
    for chave in ("temperature", "top_p", "repeat_penalty"):
        if type(identity_data[chave]) not in (int, float) or isinstance(
            identity_data[chave], bool
        ):
            raise TypeError(f"{chave} deve ser numerico")
    raw_datasets = identity_data["datasets"]
    if not isinstance(raw_datasets, list):
        raise ValueError("datasets deve ser uma lista JSON")
    datasets: list[DatasetIdentity] = []
    for index, raw_dataset in enumerate(raw_datasets):
        dataset_data = _require_exact_keys(
            raw_dataset,
            {
                "key",
                "ifc_sha256",
                "ground_truth_sha256",
                "ids_sha256",
                "building_context",
                "ground_truth_policy_version",
                "ground_truth_items",
                "equivalence_classes",
                "confidence_counts",
            },
            f"datasets[{index}]",
        )
        raw_context = dataset_data["building_context"]
        if not isinstance(raw_context, list):
            raise ValueError("building_context deve ser uma lista JSON")
        context: list[tuple[str, str]] = []
        for pair in raw_context:
            if (
                not isinstance(pair, list)
                or len(pair) != 2
                or not all(isinstance(item, str) for item in pair)
            ):
                raise ValueError("building_context contém par inválido")
            context.append((pair[0], pair[1]))
        context_keys = [key for key, _ in context]
        if len(context_keys) != len(set(context_keys)):
            raise ValueError("building_context contém chave duplicada")
        raw_confidence = dataset_data["confidence_counts"]
        if not isinstance(raw_confidence, list):
            raise ValueError("confidence_counts deve ser uma lista JSON")
        confidence_counts: list[tuple[str, int]] = []
        for pair in raw_confidence:
            if (
                not isinstance(pair, list)
                or len(pair) != 2
                or not isinstance(pair[0], str)
                or type(pair[1]) is not int
            ):
                raise ValueError("confidence_counts contém par inválido")
            confidence_counts.append((pair[0], pair[1]))
        datasets.append(
            DatasetIdentity(
                key=dataset_data["key"],
                ifc_sha256=dataset_data["ifc_sha256"],
                ground_truth_sha256=dataset_data["ground_truth_sha256"],
                ids_sha256=dataset_data["ids_sha256"],
                building_context=tuple(context),
                ground_truth_policy_version=dataset_data[
                    "ground_truth_policy_version"
                ],
                ground_truth_items=dataset_data["ground_truth_items"],
                equivalence_classes=dataset_data["equivalence_classes"],
                confidence_counts=tuple(confidence_counts),
            )
        )
    identity = ExecutionIdentity(
        release_id=identity_data["release_id"],
        project_sha256=identity_data["project_sha256"],
        models_lock_sha256=identity_data["models_lock_sha256"],
        datasets=tuple(datasets),
        replica_count=identity_data["replica_count"],
        cache_enabled=identity_data["cache_enabled"],
        prompt_version=identity_data["prompt_version"],
        prompt_sha256=identity_data["prompt_sha256"],
        reuse_equivalent=identity_data["reuse_equivalent"],
        source_commit=identity_data["source_commit"],
        num_ctx_policy=identity_data["num_ctx_policy"],
        num_ctx=identity_data["num_ctx"],
        num_predict=identity_data["num_predict"],
        seed=identity_data["seed"],
        temperature=float(identity_data["temperature"]),
        top_p=float(identity_data["top_p"]),
        repeat_penalty=float(identity_data["repeat_penalty"]),
        grounding_bsdd=identity_data["grounding_bsdd"],
    )
    if not identity.release_id:
        raise ValueError("release_id vazio")
    return identity


def _load_and_validate_execution_identity(path: Path) -> ExecutionIdentity:
    """Carrega o snapshot e recalcula todas as entradas disponíveis localmente."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    identity = _parse_execution_identity(raw)
    if identity.replica_count != 1:
        raise ValueError("replica_count oficial deve ser 1")
    if identity.cache_enabled:
        raise ValueError("a execução oficial exige cache desabilitado")
    if not identity.reuse_equivalent:
        raise ValueError("a execução oficial exige reuse_equivalent")
    if identity.prompt_version != PROMPT_VERSION:
        raise ValueError("prompt_version diverge do projeto")

    load_model_lock(LOCK_FILE)
    if _sha256(LOCK_FILE) != identity.models_lock_sha256:
        raise ValueError("models_lock_sha256 diverge do arquivo local")
    if _sha256(PROMPT_FILE) != identity.prompt_sha256:
        raise ValueError("prompt_sha256 diverge do arquivo local")

    if [item["key"] for item in DATASETS] != ["predio", "casa"]:
        raise ValueError("registro local de datasets não é predio,casa")
    if [dataset.key for dataset in identity.datasets] != ["predio", "casa"]:
        raise ValueError("snapshot de datasets não é predio,casa")
    for local, frozen in zip(DATASETS, identity.datasets, strict=True):
        actual = {
            "ifc_sha256": _sha256(Path(local["ifc"])),
            "ground_truth_sha256": _sha256(Path(local["gt"])),
            "ids_sha256": _sha256(IDS_PATH),
        }
        for field, digest in actual.items():
            if digest != getattr(frozen, field):
                raise ValueError(f"{frozen.key}.{field} diverge do arquivo local")
        if dict(frozen.building_context) != local["building_context"]:
            raise ValueError(f"{frozen.key}.building_context diverge do registro local")
        metadata = load_ground_truth_identity_metadata(Path(local["gt"]))
        if (
            metadata.ground_truth_policy_version
            != frozen.ground_truth_policy_version
            or metadata.ground_truth_items != frozen.ground_truth_items
            or metadata.equivalence_classes != frozen.equivalence_classes
            or metadata.confidence_counts != frozen.confidence_counts
        ):
            raise ValueError(f"{frozen.key}.metadata integral diverge do arquivo local")
    return identity


def _stage_path(results_root: Path, dataset_key: str, model: str, replica: int) -> Path:
    """Caminho canônico do agregado de um estágio."""
    return results_root / dataset_key / _sanitize(model) / f"run_{replica}.json"


def _stage_artifact_paths(json_path: Path) -> tuple[Path, Path]:
    """Deriva o par agregado/por-issue de um caminho canônico ``run_N.json``."""
    if _STAGE_JSON_RE.fullmatch(json_path.name) is None:
        raise ValueError("caminho de estágio deve terminar em run_N.json")
    issues_path = json_path.with_name(f"{json_path.stem}_issues.jsonl")
    return json_path, issues_path


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _stage_done(json_path: Path, expectation: StageExpectation) -> bool:
    """Valida integralmente agregado, metadata congelado e JSONL por issue."""
    try:
        aggregate_path, issues_path = _stage_artifact_paths(json_path)
        _validate_contained_path(json_path.parent, aggregate_path)
        _validate_contained_path(json_path.parent, issues_path)
        aggregate = json.loads(aggregate_path.read_text(encoding="utf-8", errors="strict"))
        if not isinstance(aggregate, dict):
            raise ValueError("agregado não é objeto")
        metadata = aggregate.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError("metadata ausente")
        expected_metadata = asdict(expectation)
        projected: dict[str, object] = {}
        for field in expected_metadata:
            if field not in metadata:
                raise ValueError(f"metadata sem {field}")
            projected[field] = metadata[field]
        if _canonical_json(projected) != _canonical_json(expected_metadata):
            raise ValueError("metadata diverge da expectativa")

        counts = aggregate.get("issue_counts")
        if not isinstance(counts, dict):
            raise ValueError("issue_counts ausente")
        total = counts.get("total_issues")
        if isinstance(total, bool) or not isinstance(total, int) or total <= 0:
            raise ValueError("total_issues deve ser inteiro positivo")

        payload = issues_path.read_bytes()
        if not payload:
            raise ValueError("JSONL vazio")
        if not payload.endswith(b"\n"):
            raise ValueError("JSONL sem newline final")
        text = payload.decode("utf-8", errors="strict")
        lines = text[:-1].split("\n")
        if any(not line for line in lines):
            raise ValueError("JSONL contém linha vazia")
        for line in lines:
            json.loads(line)
        if len(lines) != total:
            raise ValueError("contagem JSONL diverge do agregado")
        return True
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
        QuarantineRecoveryError,
    ) as exc:
        logger.debug("STAGE_INVALID {}: {}", json_path.name, exc)
        return False


def _stage_expectation(
    identity: ExecutionIdentity,
    dataset: DatasetIdentity,
    model_name: str,
    model_digest: str,
    replica: int,
) -> StageExpectation:
    return StageExpectation(
        dataset_key=dataset.key,
        model_name=model_name,
        model_digest=model_digest,
        replica_index=replica,
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


def _invalid_matrix_stages(
    results_root: Path,
    identity: ExecutionIdentity,
    models: list[tuple[str, str]],
) -> list[str]:
    """Revalida a matriz e rejeita stems de estágio esperados a mais ou a menos."""
    if identity.replica_count != 1:
        raise RuntimeError("replica_count oficial deve ser 1")
    _validate_contained_path(results_root.parent, results_root)
    invalid: list[str] = []
    expected_physical: set[str] = set()
    for dataset in identity.datasets:
        for model_name, model_digest in models:
            for replica in range(identity.replica_count):
                path = _stage_path(results_root, dataset.key, model_name, replica)
                _validate_contained_path(results_root, path)
                _validate_contained_path(results_root, _stage_artifact_paths(path)[1])
                expected_physical.add(path.relative_to(results_root).as_posix()[:-5])
                expectation = _stage_expectation(
                    identity, dataset, model_name, model_digest, replica
                )
                if not _stage_done(path, expectation):
                    invalid.append(f"{dataset.key}/{model_name}/run_{replica}")

    found: set[str] = set()
    if results_root.is_dir():
        for path in results_root.rglob("*"):
            if not path.is_file():
                continue
            name = path.name
            relative = path.relative_to(results_root).as_posix()
            if _STAGE_JSON_RE.fullmatch(name):
                found.add(relative.removesuffix(".json"))
            elif _STAGE_JSONL_RE.fullmatch(name):
                found.add(relative.removesuffix("_issues.jsonl"))
    invalid.extend(f"unexpected:{stem}" for stem in sorted(found - expected_physical))
    return invalid


def _relative_to_base(path: Path, base: Path) -> str:
    try:
        return path.absolute().relative_to(base.absolute()).as_posix()
    except ValueError as exc:
        raise QuarantineRecoveryError("recovery_required: path escape") from exc


def _path_is_reparse(path: Path) -> bool:
    """Detecta links e reparse points sem seguir o alvo."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        info = None
    if info is not None:
        if stat.S_ISLNK(info.st_mode):
            return True
        attributes = getattr(info, "st_file_attributes", 0)
        if attributes & _WINDOWS_REPARSE_POINT:
            return True
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction is not None and is_junction())


def _validate_contained_path(base: Path, candidate: Path) -> Path:
    """Valida contenção sem atravessar symlink, junction ou reparse point."""
    base_absolute = Path(os.path.abspath(base))
    candidate_absolute = Path(os.path.abspath(candidate))
    try:
        relative = candidate_absolute.relative_to(base_absolute)
    except ValueError as exc:
        raise QuarantineRecoveryError("recovery_required: path escape") from exc

    chain = [base_absolute]
    current = base_absolute
    for part in relative.parts:
        current = current / part
        chain.append(current)
    for index, component in enumerate(chain):
        if _path_is_reparse(component):
            raise QuarantineRecoveryError(
                "recovery_required: symlink, junction ou reparse point proibido"
            )
        try:
            info = os.lstat(component)
        except FileNotFoundError:
            continue
        if index < len(chain) - 1 and not stat.S_ISDIR(info.st_mode):
            raise QuarantineRecoveryError("recovery_required: ancestral de path não é diretório")

    base_resolved = base_absolute.resolve(strict=False)
    candidate_resolved = candidate_absolute.resolve(strict=False)
    try:
        candidate_resolved.relative_to(base_resolved)
    except ValueError as exc:
        raise QuarantineRecoveryError("recovery_required: alvo resolvido fora da raiz") from exc
    return candidate_absolute


def _safe_relative(base: Path, value: str) -> Path:
    pure = PurePosixPath(value)
    if (
        not value
        or pure.is_absolute()
        or any(part in {"", ".", ".."} or ":" in part for part in pure.parts)
    ):
        raise QuarantineRecoveryError("recovery_required: path relativo inválido")
    candidate = base.joinpath(*pure.parts)
    return _validate_contained_path(base, candidate)


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    data = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(5):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.01)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _move_no_replace(source: Path, destination: Path) -> None:
    """Renomeia no mesmo volume sem jamais substituir o destino."""
    if os.name != "nt":
        raise OSError(
            errno.ENOTSUP,
            "movimento no-replace oficial requer o runtime Windows",
        )
    for attempt in range(5):
        try:
            os.rename(source, destination)
            return
        except FileExistsError:
            raise
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.01)


def _move_transaction_member(paths: _TransactionPaths, source: Path, destination: Path) -> None:
    _validate_contained_path(paths.base, source)
    _validate_contained_path(paths.base, destination)
    _move_no_replace(source, destination)


def _persist_journal(path: Path, journal: QuarantineJournal) -> None:
    _write_json_atomic(path, journal.model_dump(mode="json"))


@dataclass(frozen=True)
class _TransactionPaths:
    base: Path
    results_root: Path
    journal: Path
    staging: Path
    final: Path


def _validated_transaction_paths(
    results_root: Path,
    journal_path: Path,
    journal: QuarantineJournal,
) -> _TransactionPaths:
    base = results_root.parent
    declared_results = _safe_relative(base, journal.results_root_relative)
    if declared_results.absolute() != results_root.absolute():
        raise QuarantineRecoveryError("recovery_required: results_root divergente")
    staging = _safe_relative(base, journal.staging_relative)
    final = _safe_relative(base, journal.final_relative)
    expected_root = base / ".invalid-stage-artifacts"
    expected_staging = expected_root / ".transactions" / (f"{journal.transaction_id}.partial")
    expected_final = expected_root / "quarantine" / str(journal.transaction_id)
    expected_journal = expected_root / ".transactions" / (f"{journal.transaction_id}.journal.json")
    if (
        staging.absolute() != expected_staging.absolute()
        or final.absolute() != expected_final.absolute()
        or journal_path.absolute() != expected_journal.absolute()
    ):
        raise QuarantineRecoveryError("recovery_required: destinos divergentes")
    seen_sources: set[str] = set()
    sources_by_kind: dict[str, Path] = {}
    for member in journal.members:
        if member.size_bytes < 0 or _SHA256_RE.fullmatch(member.sha256) is None:
            raise QuarantineRecoveryError("recovery_required: membro inválido")
        source = _safe_relative(base, member.source_relative)
        try:
            source.absolute().relative_to(results_root.absolute())
        except ValueError as exc:
            raise QuarantineRecoveryError("recovery_required: source fora da matriz") from exc
        if member.source_relative in seen_sources:
            raise QuarantineRecoveryError("recovery_required: membro duplicado")
        seen_sources.add(member.source_relative)
        if member.kind in sources_by_kind:
            raise QuarantineRecoveryError("recovery_required: kind duplicado")
        sources_by_kind[member.kind] = source
        if member.kind == "aggregate" and _STAGE_JSON_RE.fullmatch(source.name) is None:
            raise QuarantineRecoveryError("recovery_required: aggregate inválido")
        if member.kind == "issues" and _STAGE_JSONL_RE.fullmatch(source.name) is None:
            raise QuarantineRecoveryError("recovery_required: issues inválido")
    if not journal.members:
        raise QuarantineRecoveryError("recovery_required: transação vazia")
    if len(journal.members) > 2:
        raise QuarantineRecoveryError("recovery_required: membros excedentes")
    if set(sources_by_kind) == {"aggregate", "issues"}:
        aggregate = sources_by_kind["aggregate"]
        expected_issues = _stage_artifact_paths(aggregate)[1]
        if sources_by_kind["issues"].absolute() != expected_issues.absolute():
            raise QuarantineRecoveryError("recovery_required: stems divergentes")
    paths = _TransactionPaths(base, results_root, journal_path, staging, final)
    _assert_transaction_dirs_clean(paths, journal)
    return paths


def _member_paths(paths: _TransactionPaths, member: QuarantineMember) -> tuple[Path, Path, Path]:
    source = _safe_relative(paths.base, member.source_relative)
    return source, paths.staging / source.name, paths.final / source.name


def _assert_transaction_dirs_clean(paths: _TransactionPaths, journal: QuarantineJournal) -> None:
    expected_names = {
        _safe_relative(paths.base, member.source_relative).name for member in journal.members
    }
    for directory in (paths.staging, paths.final):
        if directory.is_symlink():
            raise QuarantineRecoveryError("recovery_required: symlink proibido")
        if directory.exists():
            if not directory.is_dir():
                raise QuarantineRecoveryError("recovery_required: destino não é diretório")
            actual_names = {entry.name for entry in directory.iterdir()}
            if not actual_names.issubset(expected_names):
                raise QuarantineRecoveryError(
                    "recovery_required: arquivo não registrado na transação"
                )


def _validate_member_file(path: Path, member: QuarantineMember) -> None:
    if path.is_symlink() or not path.is_file():
        raise QuarantineRecoveryError("recovery_required: membro ausente ou symlink")
    stat = path.stat()
    if stat.st_size != member.size_bytes or _sha256(path) != member.sha256:
        raise QuarantineRecoveryError("recovery_required: hash/tamanho divergente")


def _member_location(
    paths: _TransactionPaths, member: QuarantineMember
) -> Literal["source", "staging", "final"]:
    locations: list[Literal["source", "staging", "final"]] = []
    for label, candidate in zip(
        ("source", "staging", "final"), _member_paths(paths, member), strict=True
    ):
        if candidate.exists() or candidate.is_symlink():
            _validate_member_file(candidate, member)
            locations.append(cast(Literal["source", "staging", "final"], label))
    if len(locations) != 1:
        raise QuarantineRecoveryError("recovery_required: membro ausente ou duplicado")
    return locations[0]


def _remove_empty_staging(staging: Path) -> None:
    if staging.is_dir():
        with suppress(OSError):
            staging.rmdir()


def _clear_transaction(paths: _TransactionPaths) -> None:
    paths.journal.unlink(missing_ok=True)
    _remove_empty_staging(paths.staging)


def _finalize_forward(
    paths: _TransactionPaths,
    journal: QuarantineJournal,
) -> Path:
    _assert_transaction_dirs_clean(paths, journal)
    if paths.final.exists() or paths.final.is_symlink():
        raise QuarantineRecoveryError("recovery_required: destino final já existe")
    for member in journal.members:
        source, staged, _ = _member_paths(paths, member)
        if source.exists() or not staged.exists():
            raise QuarantineRecoveryError("recovery_required: conjunto ainda dividido")
        _validate_member_file(staged, member)
    paths.final.parent.mkdir(parents=True, exist_ok=True)
    _move_transaction_member(paths, paths.staging, paths.final)
    for member in journal.members:
        _, _, final = _member_paths(paths, member)
        _validate_member_file(final, member)
    journal.state = "finalized"
    _persist_journal(paths.journal, journal)
    paths.journal.unlink(missing_ok=True)
    return paths.final


def _attempt_forward(paths: _TransactionPaths, journal: QuarantineJournal) -> bool:
    try:
        _assert_transaction_dirs_clean(paths, journal)
        paths.staging.mkdir(parents=True, exist_ok=True)
        for member in journal.members:
            source, staged, final = _member_paths(paths, member)
            if final.exists() or final.is_symlink():
                return False
            if staged.exists() or staged.is_symlink():
                _validate_member_file(staged, member)
                if source.exists() or source.is_symlink():
                    return False
                continue
            _validate_member_file(source, member)
            _move_transaction_member(paths, source, staged)
            _validate_member_file(staged, member)
        _finalize_forward(paths, journal)
        return True
    except (OSError, QuarantineRecoveryError):
        return False


def _attempt_rollback(paths: _TransactionPaths, journal: QuarantineJournal) -> bool:
    try:
        _assert_transaction_dirs_clean(paths, journal)
        for member in reversed(journal.members):
            source, staged, final = _member_paths(paths, member)
            if final.exists() or final.is_symlink():
                return False
            if source.exists() or source.is_symlink():
                _validate_member_file(source, member)
                if staged.exists() or staged.is_symlink():
                    return False
                continue
            _validate_member_file(staged, member)
            source.parent.mkdir(parents=True, exist_ok=True)
            _move_transaction_member(paths, staged, source)
            _validate_member_file(source, member)
        if any(_member_location(paths, member) != "source" for member in journal.members):
            return False
        _clear_transaction(paths)
        return True
    except (OSError, QuarantineRecoveryError):
        return False


def _quarantine_invalid_stage_pair(json_path: Path, results_root: Path) -> Path | None:
    """Move, transacionalmente, os membros existentes de um par inválido."""
    aggregate, issues = _stage_artifact_paths(json_path)
    base = results_root.parent
    _validate_contained_path(base, results_root)
    _validate_contained_path(results_root, aggregate)
    _validate_contained_path(results_root, issues)
    existing = [
        ("aggregate", aggregate),
        ("issues", issues),
    ]
    existing = [(kind, path) for kind, path in existing if path.exists()]
    if not existing:
        return None
    for _, source in existing:
        try:
            source.absolute().relative_to(results_root.absolute())
        except ValueError as exc:
            raise RuntimeError("quarentena recusou path fora da matriz") from exc
        if source.is_symlink() or not source.is_file():
            raise RuntimeError("quarentena recusou membro não regular")

    transaction_id = uuid4()
    root = base / ".invalid-stage-artifacts"
    journal_path = root / ".transactions" / f"{transaction_id}.journal.json"
    staging = root / ".transactions" / f"{transaction_id}.partial"
    final = root / "quarantine" / str(transaction_id)
    _validate_contained_path(base, journal_path)
    _validate_contained_path(base, staging)
    _validate_contained_path(base, final)
    members = tuple(
        QuarantineMember(
            kind=kind,
            source_relative=_relative_to_base(source, base),
            size_bytes=source.stat().st_size,
            sha256=_sha256(source),
        )
        for kind, source in existing
    )
    journal = QuarantineJournal(
        transaction_id=transaction_id,
        state="prepared",
        results_root_relative=_relative_to_base(results_root, base),
        staging_relative=_relative_to_base(staging, base),
        final_relative=_relative_to_base(final, base),
        members=members,
    )
    paths = _TransactionPaths(base, results_root, journal_path, staging, final)
    _safe_relative(base, journal.staging_relative)
    _safe_relative(base, journal.final_relative)
    staging.mkdir(parents=True, exist_ok=False)
    _persist_journal(journal_path, journal)
    journal.state = "moving"
    _persist_journal(journal_path, journal)
    try:
        for member in members:
            source, staged, _ = _member_paths(paths, member)
            if staged.exists() or staged.is_symlink():
                raise OSError("destino de staging já existe")
            _move_transaction_member(paths, source, staged)
            _validate_member_file(staged, member)
        return _finalize_forward(paths, journal)
    except (OSError, QuarantineRecoveryError) as exc:
        if _attempt_rollback(paths, journal):
            raise RuntimeError("falha de quarentena; par restaurado") from exc
        if _attempt_forward(paths, journal):
            raise RuntimeError("falha de quarentena; par isolado por recuperação") from exc
        journal.state = "recovery_required"
        _persist_journal(journal_path, journal)
        raise QuarantineRecoveryError(
            "recovery_required: transação de quarentena pendente"
        ) from exc


def _load_journal(path: Path) -> QuarantineJournal:
    try:
        if path.is_symlink():
            raise ValueError("journal symlink")
        raw = json.loads(path.read_text(encoding="utf-8", errors="strict"))
        data = _require_exact_keys(
            raw,
            {
                "schema_version",
                "transaction_id",
                "state",
                "results_root_relative",
                "staging_relative",
                "final_relative",
                "members",
            },
            "journal",
        )
        if type(data["schema_version"]) is not int:
            raise TypeError("schema_version inválido")
        for field in (
            "transaction_id",
            "state",
            "results_root_relative",
            "staging_relative",
            "final_relative",
        ):
            if not isinstance(data[field], str):
                raise TypeError(f"{field} inválido")
        if not isinstance(data["members"], list):
            raise TypeError("members inválido")
        for raw_member in data["members"]:
            member = _require_exact_keys(
                raw_member,
                {"kind", "source_relative", "size_bytes", "sha256"},
                "journal.members",
            )
            if (
                not isinstance(member["kind"], str)
                or not isinstance(member["source_relative"], str)
                or type(member["size_bytes"]) is not int
                or not isinstance(member["sha256"], str)
            ):
                raise TypeError("journal.members possui tipo inválido")
        return QuarantineJournal.model_validate(raw)
    except Exception as exc:
        raise QuarantineRecoveryError("recovery_required: journal inválido") from exc


def _reconcile_quarantine_transactions(results_root: Path) -> None:
    """Reconcilia journals lexicograficamente antes de qualquer estágio."""
    transaction_root = results_root.parent / ".invalid-stage-artifacts" / ".transactions"
    try:
        _validate_contained_path(results_root.parent, results_root)
        _validate_contained_path(results_root.parent, transaction_root)
        if not transaction_root.is_dir():
            return
        journal_paths = sorted(transaction_root.glob("*.journal.json"))
    except QuarantineRecoveryError:
        raise
    except OSError as exc:
        raise QuarantineRecoveryError(
            "recovery_required: erro de I/O durante reconciliação"
        ) from exc
    for journal_path in journal_paths:
        journal: QuarantineJournal | None = None
        try:
            _validate_contained_path(transaction_root, journal_path)
            journal = _load_journal(journal_path)
            paths = _validated_transaction_paths(results_root, journal_path, journal)
            locations = [_member_location(paths, member) for member in journal.members]
            if all(location == "source" for location in locations):
                _clear_transaction(paths)
                continue
            if all(location == "final" for location in locations):
                paths.journal.unlink(missing_ok=True)
                continue
            if "final" not in locations:
                if _attempt_forward(paths, journal):
                    continue
                if _attempt_rollback(paths, journal):
                    continue
            journal.state = "recovery_required"
            _persist_journal(journal_path, journal)
            raise QuarantineRecoveryError("recovery_required: transação não reconciliada")
        except (OSError, QuarantineRecoveryError) as exc:
            if journal is not None:
                journal.state = "recovery_required"
                with suppress(OSError):
                    _persist_journal(journal_path, journal)
            if isinstance(exc, QuarantineRecoveryError):
                raise
            raise QuarantineRecoveryError(
                "recovery_required: erro de I/O durante reconciliação"
            ) from exc


def _pid_record_is_live(record: object) -> bool:
    """Confere PID, instante de criação e comando do runner."""
    if not isinstance(record, dict):
        return False
    if set(record) != {"pid", "create_time", "token"}:
        return False
    pid = record.get("pid")
    create_time = record.get("create_time")
    token = record.get("token")
    if (
        isinstance(pid, bool)
        or not isinstance(pid, int)
        or not isinstance(create_time, (int, float))
        or not isinstance(token, str)
        or not token
    ):
        return False
    try:
        process = psutil.Process(pid)
        if abs(process.create_time() - float(create_time)) > 0.01:
            return False
        return any("run_benchmark.py" in part.lower() for part in process.cmdline())
    except (psutil.Error, OSError):
        return False


def _lease_payload(lease: PidLease) -> bytes:
    return (json.dumps(asdict(lease), sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _create_lease_exclusive(path: Path, lease: PidLease) -> bool:
    """Publica um registro completo por hard link, sem janela de JSON parcial."""
    temporary = path.with_name(f".{path.name}.{lease.token}.partial")
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(_lease_payload(lease))
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        return True
    except FileExistsError:
        return False
    finally:
        if descriptor is not None:
            os.close(descriptor)
        with suppress(OSError):
            temporary.unlink(missing_ok=True)


def _read_pid_record(path: Path) -> tuple[object, bytes, os.stat_result] | None:
    try:
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
    except FileNotFoundError:
        return None
    if before.st_mtime_ns != after.st_mtime_ns or before.st_size != after.st_size:
        raise OSError(errno.EAGAIN, "pidfile mudou durante a leitura")
    try:
        record: object = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        record = None
    return record, payload, after


def _restore_pidfile_claim(claimed: Path, path: Path) -> None:
    """Restaura bytes que não pertenciam ao chamador, sem sobrescrever terceiros."""
    try:
        _move_no_replace(claimed, path)
    except FileExistsError:
        # Outro lease já ocupa o nome canônico; o claim permanece preservado.
        return


def _remove_stale_pidfile(path: Path, expected_payload: bytes | None) -> bool:
    """Remove somente o registro morto observado, após reivindicá-lo atomicamente."""
    claimed = path.with_name(f".{path.name}.{uuid4().hex}.stale")
    try:
        _move_no_replace(path, claimed)
    except FileNotFoundError:
        return True

    try:
        observed = _read_pid_record(claimed)
        if observed is None:
            raise OSError(errno.ENOENT, "claim de pidfile desapareceu")
        record, payload, _ = observed
        if expected_payload is not None and payload != expected_payload:
            _restore_pidfile_claim(claimed, path)
            return False
        if _pid_record_is_live(record):
            _restore_pidfile_claim(claimed, path)
            return False
        claimed.unlink()
        return True
    except Exception:
        if claimed.exists() or claimed.is_symlink():
            with suppress(OSError):
                _restore_pidfile_claim(claimed, path)
        raise


def _acquire_pidfile(path: Path) -> PidLease | None:
    """Adquire lease O_EXCL; coleta registro morto sob um segundo lease."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lease = PidLease(
        pid=os.getpid(),
        create_time=psutil.Process(os.getpid()).create_time(),
        token=str(uuid4()),
    )
    if _create_lease_exclusive(path, lease):
        return lease

    observed = _read_pid_record(path)
    if observed is not None and _pid_record_is_live(observed[0]):
        return None
    reap_path = path.with_name(f"{path.name}.reap")
    reap_lease = PidLease(lease.pid, lease.create_time, str(uuid4()))
    if not _create_lease_exclusive(reap_path, reap_lease):
        observed_reap = _read_pid_record(reap_path)
        if observed_reap is not None and _pid_record_is_live(observed_reap[0]):
            return None
        expected_reap = observed_reap[1] if observed_reap is not None else None
        if not _remove_stale_pidfile(reap_path, expected_reap):
            return None
        if not _create_lease_exclusive(reap_path, reap_lease):
            return None
    try:
        current = _read_pid_record(path)
        if current is not None and _pid_record_is_live(current[0]):
            return None
        expected_current = current[1] if current is not None else None
        if current is not None and not _remove_stale_pidfile(path, expected_current):
            return None
        return lease if _create_lease_exclusive(path, lease) else None
    finally:
        _release_pidfile(reap_path, reap_lease)


def _release_pidfile(path: Path, lease: PidLease) -> None:
    """Remove apenas o lease do chamador por move-validate, sem check/unlink."""
    claimed = path.with_name(f".{path.name}.{uuid4().hex}.release")
    try:
        _move_no_replace(path, claimed)
    except FileNotFoundError:
        return

    try:
        observed = _read_pid_record(claimed)
        if observed is not None and observed[1] == _lease_payload(lease):
            claimed.unlink()
            return
        _restore_pidfile_claim(claimed, path)
    except Exception:
        if claimed.exists() or claimed.is_symlink():
            with suppress(OSError):
                _restore_pidfile_claim(claimed, path)
        raise


def _capture_stop_baseline(path: Path) -> StopBaseline:
    try:
        stat = path.stat()
        return StopBaseline(True, stat.st_mtime_ns, stat.st_size, _sha256(path))
    except OSError:
        return StopBaseline(False, None, None, None)


def _stop_requested(path: Path, baseline: StopBaseline) -> bool:
    current = _capture_stop_baseline(path)
    return current.exists and current != baseline


def _installed_digest(model: str) -> str | None:
    from src.config import get_settings
    from src.experiment.environment import ollama_model_digest

    return ollama_model_digest(model, get_settings().ollama_url)


def _assert_model_digest(model: str, expected: str, actual: str | None) -> None:
    if actual != expected:
        actual_display = actual or "<ausente>"
        raise RuntimeError(
            f"digest divergente para {model}: esperado {expected}, atual {actual_display}"
        )


def _unload_model(model: str) -> None:
    import httpx

    from src.config import get_settings

    try:
        httpx.post(
            f"{get_settings().ollama_url}/api/generate",
            json={"model": model, "prompt": "", "keep_alive": 0},
            timeout=60,
        )
        logger.info("Modelo {} descarregado", model)
    except Exception as exc:
        logger.warning("Falha ao descarregar {}: {}", model, exc)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python scripts/run_benchmark.py")
    parser.add_argument("--replicas", type=int, default=1)
    parser.add_argument("--only-model", default=None)
    parser.add_argument("--results-root", default=None)
    parser.add_argument("--execution-identity", type=Path, required=True)
    parser.add_argument("--no-cache", action="store_true", required=True)
    parser.add_argument("--reuse-equivalent", action="store_true")
    # Braço da ablação de grounding. Não tem default implícito: o valor precisa
    # casar com identity.grounding_bsdd, senão a fila aborta antes do 1º estágio.
    parser.add_argument(
        "--no-bsdd",
        dest="use_bsdd",
        action="store_false",
        help="Desliga a consulta ao bSDD (exige execution-identity com grounding_bsdd=false).",
    )
    parser.set_defaults(use_bsdd=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Executa a fila; 0=matriz íntegra, 1=falha, 130=interrupção."""
    args = _build_parser().parse_args(argv)
    if args.replicas != 1:
        logger.error("--replicas oficial deve ser 1")
        return 1
    if not args.reuse_equivalent:
        logger.error("--reuse-equivalent é obrigatório no modo oficial")
        return 1
    stop_baseline = _capture_stop_baseline(STOP_FILE)
    try:
        lease = _acquire_pidfile(PID_FILE)
    except OSError as exc:
        logger.error("PID_LEASE_FAILED: {}", type(exc).__name__)
        return 1
    if lease is None:
        logger.error("BENCHMARK_ALREADY_RUNNING")
        return 1

    resident_model: str | None = None
    try:
        launch_stamp = datetime.now(UTC).isoformat()
        results_root = Path(
            args.results_root
            or PROJECT_ROOT
            / "src"
            / "experiment"
            / "results"
            / f"{datetime.now():%Y-%m-%d}-benchmark"
        )
        try:
            _validate_contained_path(results_root.parent, results_root)
            _reconcile_quarantine_transactions(results_root)
        except QuarantineRecoveryError:
            logger.error("QUARANTINE_RECOVERY_REQUIRED")
            return 1

        identity = _load_and_validate_execution_identity(args.execution_identity)
        if identity.replica_count != 1:
            raise RuntimeError("replica_count oficial deve ser 1")
        if identity.reuse_equivalent is not True:
            raise RuntimeError("reuse_equivalent oficial deve ser true")
        if identity.replica_count != args.replicas:
            raise RuntimeError("replica_count diverge de --replicas")
        if identity.cache_enabled is not False:
            raise RuntimeError("cache oficial deve permanecer desabilitado")
        if identity.reuse_equivalent != args.reuse_equivalent:
            raise RuntimeError("reuse_equivalent diverge da identidade")
        if identity.grounding_bsdd != args.use_bsdd:
            raise RuntimeError(
                "grounding_bsdd diverge de --no-bsdd: a identidade declara "
                f"{identity.grounding_bsdd} e a fila rodaria com {args.use_bsdd}"
            )

        models = _locked_models()
        locked_digests = _locked_digests()
        official_model_matrix = [(model, locked_digests[model]) for model in models]
        if args.only_model:
            if args.only_model not in models:
                raise RuntimeError("--only-model não pertence ao lock")
            models = [args.only_model]
        model_matrix = [(model, locked_digests[model]) for model in models]
        identity_by_key = {dataset.key: dataset for dataset in identity.datasets}
        runner = ExperimentRunner()
        failures: list[str] = []
        checked_digests: set[str] = set()
        completed = 0
        skipped = 0
        started = time.perf_counter()

        for replica in range(args.replicas):
            for model, expected_digest in model_matrix:
                if resident_model is not None and resident_model != model:
                    _unload_model(resident_model)
                    resident_model = None
                for dataset in DATASETS:
                    stage = f"{dataset['key']}/{model}/run_{replica}"
                    if _stop_requested(STOP_FILE, stop_baseline):
                        logger.warning("interrupted: BENCHMARK_STOP")
                        return 130
                    frozen_dataset = identity_by_key[dataset["key"]]
                    expectation = _stage_expectation(
                        identity, frozen_dataset, model, expected_digest, replica
                    )
                    json_path = _stage_path(results_root, dataset["key"], model, replica)
                    _validate_contained_path(results_root, json_path)
                    _validate_contained_path(results_root, _stage_artifact_paths(json_path)[1])
                    if _stage_done(json_path, expectation):
                        skipped += 1
                        logger.info("STAGE SKIP: {}", stage)
                        continue
                    _, issues_path = _stage_artifact_paths(json_path)
                    if json_path.exists() or issues_path.exists():
                        try:
                            _quarantine_invalid_stage_pair(json_path, results_root)
                        except QuarantineRecoveryError:
                            logger.error("QUARANTINE_RECOVERY_REQUIRED")
                            return 1
                        except RuntimeError as exc:
                            failures.append(stage)
                            logger.error("STAGE FAIL {}: {}", stage, exc)
                            continue

                    if model not in checked_digests:
                        _assert_model_digest(model, expected_digest, _installed_digest(model))
                        checked_digests.add(model)
                    resident_model = model
                    try:
                        result = runner.run_single(
                            ifc_path=str(dataset["ifc"]),
                            ground_truth_path=str(dataset["gt"]),
                            building_context=dataset["building_context"],
                            ids_path=str(IDS_PATH),
                            model_name=model,
                            cache_enabled=False,
                            replica_index=replica,
                            timestamp=launch_stamp,
                            issue_types=dataset["issue_types"],
                            reuse_equivalent=args.reuse_equivalent,
                            dataset_key=dataset["key"],
                            execution_identity=identity,
                            use_bsdd=args.use_bsdd,
                        )
                        json_path.parent.mkdir(parents=True, exist_ok=True)
                        _validate_contained_path(results_root, json_path.parent)
                        _validate_contained_path(results_root, json_path)
                        _validate_contained_path(results_root, _stage_artifact_paths(json_path)[1])
                        ExperimentRunner._export(result, str(results_root / dataset["key"]))
                        if not _stage_done(json_path, expectation):
                            raise RuntimeError("par exportado não passou na revalidação")
                        completed += 1
                        if _stop_requested(STOP_FILE, stop_baseline):
                            logger.warning("interrupted: BENCHMARK_STOP")
                            return 130
                        logger.info("STAGE OK: {}", stage)
                    except KeyboardInterrupt:
                        raise
                    except Exception as exc:
                        failures.append(stage)
                        logger.exception("STAGE FAIL {}: {}", stage, exc)

        invalid = _invalid_matrix_stages(results_root, identity, official_model_matrix)
        if invalid:
            failures.extend(invalid)
            logger.error("MATRIX_INVALID: {}", invalid)
        elapsed = (time.perf_counter() - started) / 3600
        logger.info(
            "FILA FINAL: {:.2f}h, {} concluídos, {} retomados, {} falhas",
            elapsed,
            completed,
            skipped,
            len(failures),
        )
        return 1 if failures else 0
    except KeyboardInterrupt:
        logger.warning("interrupted: KeyboardInterrupt")
        return 130
    except Exception as exc:
        logger.exception("BENCHMARK_FAILED: {}", exc)
        return 1
    finally:
        if resident_model is not None:
            _unload_model(resident_model)
        try:
            _release_pidfile(PID_FILE, lease)
        except OSError as exc:
            logger.error("PID_LEASE_RELEASE_FAILED: {}", type(exc).__name__)


if __name__ == "__main__":
    sys.exit(main())
