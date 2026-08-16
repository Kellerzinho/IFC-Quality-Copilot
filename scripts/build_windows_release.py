"""Build the self-contained Windows benchmark release from an explicit allowlist."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

# Data da release, fixada de proposito: o release_id precisa ser deterministico
# para o mesmo conteudo. Bumpe junto com PROMPT_VERSION ou ao republicar.
RELEASE_DATE = "2026-08-16"
RELEASE_DIRECTORY_PREFIX = "IFCQC-Benchmark-Windows-x64"
PROMPT_VERSION = "v7.7"
TEMPLATE_PATH = "windows/release-manifest.template.json"

PROJECT_PATTERNS = (
    ".python-version",
    "uv.lock",
    "pyproject.toml",
    "src/**/*.py",
    "src/experiment/results/models.lock.json",
    "scripts/run_benchmark.py",
    "scripts/windows_benchmark.py",
    "scripts/build_ground_truths.py",
    "windows/collect-hardware.ps1",
    "data/ids_templates/**/*.ids",
    "data/ids_schema/**/*",
    "data/cache/bsdd_cache.json",
    "data/evaluation/legacy-reference.lock.json",
    "data/evaluation/predio/ground_truth.yaml",
    "data/evaluation/predio/README.md",
    "data/evaluation/casa/ground_truth.yaml",
    "data/evaluation/casa/README.md",
    "references/normative/public/**/*",
)

REQUIRED_PROJECT_FILES = frozenset(
    {
        ".python-version",
        "uv.lock",
        "pyproject.toml",
        "src/experiment/results/models.lock.json",
        "src/suggestion_engine/prompt_templates.py",
        "scripts/run_benchmark.py",
        "scripts/windows_benchmark.py",
        "scripts/build_ground_truths.py",
        "windows/collect-hardware.ps1",
        "data/ids_templates/residencial_nbr15575.ids",
        "data/ids_schema/ids.xsd",
        "data/cache/bsdd_cache.json",
        "data/evaluation/legacy-reference.lock.json",
        "data/evaluation/predio/ground_truth.yaml",
        "data/evaluation/predio/README.md",
        "data/evaluation/casa/ground_truth.yaml",
        "data/evaluation/casa/README.md",
        "references/normative/public/README.md",
        "references/normative/public/sources.yaml",
    }
)

PUBLIC_FILES = {
    "windows/EXECUTAR_BENCHMARK.cmd": "EXECUTAR_BENCHMARK.cmd",
    "windows/LEIA-ME.txt": "LEIA-ME.txt",
    "windows/install.ps1": "install.ps1",
}

DATASET_FILES = {
    "predio": "data/evaluation/predio/predio_v1.ifc",
    "casa": "data/evaluation/casa/casa_v1.ifc",
}

EXPECTED_IFC_SHA256 = {
    "predio": "a71c8be30d82760218f5b3f3a1c476b49e3f30e608b0065916b9d5206a1a6dd0",
    "casa": "3b84789c7396449f2c8a3d2f4a66468d81e59f8351ebd4b71fad161fa06112f2",
}

_TEMPLATE_KEYS = {
    "schema_version",
    "platform",
    "minimum_windows_build",
    "python_version",
    "tools",
}
_TOOL_NAMES = {"uv", "ollama", "ollama_rocm", "llmfit"}
_TOOL_RECORD_KEYS = {"version", "url", "sha256", "size_bytes"}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_DIRECTORIES = {
    ".git",
    ".claude",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".history",
    "history",
    "artigo",
    "dist",
    "build",
    "secrets",
    ".secrets",
}
_FORBIDDEN_FILENAMES = {
    ".env",
    "benchmark_running",
    "benchmark_stop",
    "credentials.json",
    "secrets.json",
}
_REPARSE_POINT_ATTRIBUTE = 0x400


class ReleaseBuildError(RuntimeError):
    """Raised when release inputs are missing, unsafe, or inconsistent."""


@dataclass(frozen=True)
class ArchiveRecord:
    """Hash and size of a file created by the release builder."""

    path: Path
    size_bytes: int
    sha256: str


def sha256_file(path: Path) -> str:
    """Return a lowercase SHA-256 for *path* without loading it all in memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolve_root(root: Path) -> Path:
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise ReleaseBuildError(f"Raiz do projeto ausente: {root}") from exc
    if not resolved.is_dir():
        raise ReleaseBuildError(f"Raiz do projeto não é diretório: {root}")
    return resolved


def _is_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction) and is_junction():
        return True
    try:
        attributes = int(getattr(path.lstat(), "st_file_attributes", 0))
    except OSError as exc:
        raise ReleaseBuildError(f"Não foi possível inspecionar {path}") from exc
    return bool(attributes & _REPARSE_POINT_ATTRIBUTE)


def _assert_safe_source(root: Path, candidate: Path) -> None:
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise ReleaseBuildError(f"Caminho fora da raiz do projeto: {candidate}") from exc

    current = root
    for part in relative.parts:
        current = current / part
        if _is_reparse_point(current):
            raise ReleaseBuildError(f"Fonte symlink/reparse não permitida: {current}")

    try:
        resolved = candidate.resolve(strict=True)
        common = os.path.commonpath((str(root), str(resolved)))
    except (OSError, ValueError) as exc:
        raise ReleaseBuildError(f"Não foi possível resolver a fonte: {candidate}") from exc
    if os.path.normcase(common) != os.path.normcase(str(root)):
        raise ReleaseBuildError(f"Caminho fora da raiz do projeto: {candidate}")


def _is_forbidden(relative: str) -> bool:
    parts = tuple(part.casefold() for part in Path(relative).parts)
    if any(part in _FORBIDDEN_DIRECTORIES for part in parts[:-1]):
        return True
    name = parts[-1]
    if name in _FORBIDDEN_FILENAMES or name.startswith(".env."):
        return True
    if name.endswith((".pem", ".key")) or name.startswith(("credentials.", "secret.")):
        return True
    return (
        len(parts) >= 4
        and parts[:3] == ("src", "experiment", "results")
        and relative != "src/experiment/results/models.lock.json"
    )


def _collect_project_files(root: Path) -> dict[str, Path]:
    selected: dict[str, Path] = {}
    for pattern in PROJECT_PATTERNS:
        for candidate in root.glob(pattern):
            relative = candidate.relative_to(root).as_posix()
            if _is_forbidden(relative):
                continue
            _assert_safe_source(root, candidate)
            try:
                mode = candidate.lstat().st_mode
            except OSError as exc:
                raise ReleaseBuildError(f"Não foi possível inspecionar {relative}") from exc
            if stat.S_ISDIR(mode):
                continue
            if not stat.S_ISREG(mode):
                raise ReleaseBuildError(f"Fonte não é arquivo regular: {relative}")
            selected[relative] = candidate

    missing = sorted(REQUIRED_PROJECT_FILES - selected.keys())
    if missing:
        raise ReleaseBuildError(f"Entrada obrigatória ausente: {missing[0]}")
    python_version = selected[".python-version"].read_text(encoding="utf-8").strip()
    if python_version != "3.12.13":
        raise ReleaseBuildError(".python-version deve fixar 3.12.13")
    _validate_prompt_version(selected["src/suggestion_engine/prompt_templates.py"])
    return dict(sorted(selected.items()))


def _validate_prompt_version(path: Path) -> None:
    try:
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeError) as exc:
        raise ReleaseBuildError(f"Não foi possível ler PROMPT_VERSION em {path}") from exc

    versions: list[str] = []
    for node in module.body:
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "PROMPT_VERSION"
                for target in node.targets
            )
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ) or (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "PROMPT_VERSION"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            versions.append(node.value.value)
    if versions != [PROMPT_VERSION]:
        observed = versions[0] if len(versions) == 1 else "ausente/ambíguo"
        raise ReleaseBuildError(
            f"PROMPT_VERSION deve ser {PROMPT_VERSION}; valor observado: {observed}"
        )


def _write_deterministic_member(
    archive: zipfile.ZipFile, relative: str, data: bytes
) -> None:
    info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    archive.writestr(info, data)


def _normalized_utf8_lf(source: Path, label: str) -> bytes:
    try:
        text = source.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ReleaseBuildError(f"Arquivo textual UTF-8 inválido: {label}") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _project_member_bytes(source: Path, relative: str) -> bytes:
    return _normalized_utf8_lf(source, relative)


def _public_member_bytes(source: Path, output_name: str) -> bytes:
    canonical_lf = _normalized_utf8_lf(source, output_name)
    if output_name.casefold().endswith(".cmd"):
        return canonical_lf.replace(b"\n", b"\r\n")
    return canonical_lf


def build_project_zip(root: Path, output: Path) -> ArchiveRecord:
    """Write the deterministic, allowlisted project payload ZIP."""

    resolved_root = _resolve_root(root)
    selected = _collect_project_files(resolved_root)
    output = output.resolve()
    if output.exists():
        raise ReleaseBuildError(f"Saída já existe e não será sobrescrita: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".partial",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for relative, source in selected.items():
                _write_deterministic_member(
                    archive, relative, _project_member_bytes(source, relative)
                )
        os.replace(temporary, output)
        temporary = None
    except OSError as exc:
        raise ReleaseBuildError(f"Falha ao criar project.zip: {exc}") from exc
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()

    return ArchiveRecord(
        path=output,
        size_bytes=output.stat().st_size,
        sha256=sha256_file(output),
    )


def _load_template(root: Path) -> dict[str, Any]:
    path = root / TEMPLATE_PATH
    if not path.exists():
        raise ReleaseBuildError(f"Entrada obrigatória ausente: {TEMPLATE_PATH}")
    _assert_safe_source(root, path)
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseBuildError(f"Template de manifesto inválido: {path}") from exc
    if not isinstance(loaded, dict) or set(loaded) != _TEMPLATE_KEYS:
        raise ReleaseBuildError("Template de manifesto possui chaves inesperadas")

    template = cast(dict[str, Any], loaded)
    expected_scalars = {
        "schema_version": 1,
        "platform": "windows-x86_64",
        "minimum_windows_build": 19045,
        "python_version": "3.12.13",
    }
    for key, expected in expected_scalars.items():
        if template.get(key) != expected:
            raise ReleaseBuildError(f"Pin inválido no template: {key}")

    tools = template.get("tools")
    if not isinstance(tools, dict) or set(tools) != _TOOL_NAMES:
        raise ReleaseBuildError("Template deve fixar uv, ollama, ollama_rocm e llmfit")
    for name, raw_record in tools.items():
        if not isinstance(raw_record, dict) or set(raw_record) != _TOOL_RECORD_KEYS:
            raise ReleaseBuildError(f"Registro de ferramenta inválido: {name}")
        version = raw_record.get("version")
        url = raw_record.get("url")
        sha256 = raw_record.get("sha256")
        size = raw_record.get("size_bytes")
        if not isinstance(version, str) or not version:
            raise ReleaseBuildError(f"Versão de ferramenta inválida: {name}")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise ReleaseBuildError(f"URL de ferramenta inválida: {name}")
        if not isinstance(sha256, str) or _SHA256_RE.fullmatch(sha256) is None:
            raise ReleaseBuildError(f"SHA-256 de ferramenta inválido: {name}")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise ReleaseBuildError(f"Tamanho de ferramenta inválido: {name}")
    return template


def _required_source(root: Path, relative: str) -> Path:
    source = root / relative
    if not source.exists():
        raise ReleaseBuildError(f"Entrada obrigatória ausente: {relative}")
    _assert_safe_source(root, source)
    if not source.is_file():
        raise ReleaseBuildError(f"Entrada obrigatória não é arquivo: {relative}")
    return source


def _validate_ifcs(root: Path) -> dict[str, Path]:
    sources: dict[str, Path] = {}
    for dataset, relative in DATASET_FILES.items():
        source = _required_source(root, relative)
        observed = sha256_file(source)
        expected = EXPECTED_IFC_SHA256[dataset]
        if observed != expected:
            raise ReleaseBuildError(
                f"IFC {dataset} com SHA-256 divergente: esperado {expected}, observado {observed}"
            )
        sources[dataset] = source
    return sources


def _tree_fallback_commit(
    project_files: dict[str, Path], extra_files: dict[str, Path]
) -> str:
    members = {
        f"project/{relative}": _project_member_bytes(source, relative)
        for relative, source in project_files.items()
    }
    for relative, source in extra_files.items():
        if relative.startswith("public/"):
            members[relative] = _public_member_bytes(source, Path(relative).name)
        elif relative == TEMPLATE_PATH:
            members[relative] = _normalized_utf8_lf(source, relative)
        else:
            members[relative] = source.read_bytes()
    digest = hashlib.sha256()
    for relative, data in sorted(members.items()):
        encoded_path = relative.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return f"tree-{digest.hexdigest()}"


def _git_commit_for_exact_root(root: Path) -> str | None:
    try:
        top_level = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if top_level.returncode != 0:
        return None
    try:
        discovered_root = Path(top_level.stdout.strip()).resolve(strict=True)
    except OSError:
        return None
    if os.path.normcase(str(discovered_root)) != os.path.normcase(str(root)):
        return None

    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = head.stdout.strip().lower()
    if head.returncode != 0 or re.fullmatch(r"[0-9a-f]{40,64}", commit) is None:
        return None
    return commit


def project_input_record(root: Path, project_path: str) -> dict[str, object]:
    """Describe one file that is stored inside ``project.zip``."""

    source = _required_source(_resolve_root(root), project_path)
    data = _project_member_bytes(source, project_path)
    return {
        "project_path": project_path,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _payload_record(source: Path, relative: str) -> dict[str, object]:
    return {
        "path": relative,
        "size_bytes": source.stat().st_size,
        "sha256": sha256_file(source),
    }


def build_release(root: Path, output_root: Path) -> Path:
    """Build and return a validated Windows release directory."""

    resolved_root = _resolve_root(root)
    project_files = _collect_project_files(resolved_root)
    template = _load_template(resolved_root)
    public_sources = {
        output_name: _required_source(resolved_root, source_name)
        for source_name, output_name in PUBLIC_FILES.items()
    }
    dataset_sources = _validate_ifcs(resolved_root)

    extra_sources = {
        TEMPLATE_PATH: resolved_root / TEMPLATE_PATH,
        **{f"public/{name}": source for name, source in public_sources.items()},
        **{f"datasets/{name}.ifc": source for name, source in dataset_sources.items()},
    }
    source_commit = _git_commit_for_exact_root(resolved_root) or _tree_fallback_commit(
        project_files, extra_sources
    )
    identity_hex = source_commit.removeprefix("tree-")
    release_id = f"ifcqc-{RELEASE_DATE}-{identity_hex[:12]}"
    destination = output_root.resolve() / f"{RELEASE_DIRECTORY_PREFIX}-{release_id}"
    if destination.exists():
        if not destination.is_dir() or any(destination.iterdir()):
            raise ReleaseBuildError(f"Destino da release não está vazio: {destination}")
    else:
        destination.mkdir(parents=True)

    payload = destination / "payload"
    datasets_directory = payload / "datasets"
    datasets_directory.mkdir(parents=True)

    project_archive = build_project_zip(resolved_root, payload / "project.zip")
    project_record: dict[str, object] = {
        "path": "payload/project.zip",
        "size_bytes": project_archive.size_bytes,
        "sha256": project_archive.sha256,
    }

    manifest_datasets: dict[str, dict[str, object]] = {}
    for dataset, source in dataset_sources.items():
        relative = f"payload/datasets/{dataset}_v1.ifc"
        target = destination / relative
        shutil.copyfile(source, target)
        manifest_datasets[dataset] = _payload_record(target, relative)

    for output_name, source in public_sources.items():
        (destination / output_name).write_bytes(_public_member_bytes(source, output_name))

    ids_record = project_input_record(
        resolved_root, "data/ids_templates/residencial_nbr15575.ids"
    )
    prompt_record = project_input_record(
        resolved_root, "src/suggestion_engine/prompt_templates.py"
    )
    prompt_record["version"] = PROMPT_VERSION
    inputs = {
        "models_lock": project_input_record(
            resolved_root, "src/experiment/results/models.lock.json"
        ),
        "prompt_templates": prompt_record,
        "datasets": {
            dataset: {
                "ifc": dict(manifest_datasets[dataset]),
                "ground_truth": project_input_record(
                    resolved_root, f"data/evaluation/{dataset}/ground_truth.yaml"
                ),
                "ids": dict(ids_record),
            }
            for dataset in ("predio", "casa")
        },
    }

    manifest = {
        **template,
        "release_id": release_id,
        "source_commit": source_commit,
        "project": project_record,
        "datasets": manifest_datasets,
        "inputs": inputs,
    }
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    (destination / "release-manifest.json").write_text(
        manifest_text, encoding="utf-8", newline="\n"
    )
    return destination


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="raiz do projeto (padrão: raiz que contém este script)",
    )
    parser.add_argument("--output", type=Path, required=True, help="diretório pai da release")
    args = parser.parse_args(argv)
    try:
        release = build_release(args.root, args.output)
    except ReleaseBuildError as exc:
        parser.exit(2, f"ERRO: {exc}\n")
    print(release)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
