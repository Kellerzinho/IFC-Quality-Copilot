from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pytest

import scripts.build_windows_release as release_builder
from scripts.build_windows_release import (
    RELEASE_DATE,
    ReleaseBuildError,
    build_project_zip,
    build_release,
)

TOOL_PINS = {
    "uv": {
        "version": "0.12.3",
        "url": (
            "https://github.com/astral-sh/uv/releases/download/0.12.3/"
            "uv-x86_64-pc-windows-msvc.zip"
        ),
        "sha256": "b23350c79e8ad0192b8124af13a0f17e8d4e4549524785e1aef389ae5a06990e",
        "size_bytes": 19013455,
    },
    "ollama": {
        "version": "0.32.5",
        "url": (
            "https://github.com/ollama/ollama/releases/download/v0.32.5/"
            "ollama-windows-amd64.zip"
        ),
        "sha256": "7c941ae084569d298062d29f8139163a3187c76dbca0479c70d085e78fd8c7bb",
        "size_bytes": 1457824795,
    },
    "ollama_rocm": {
        "version": "0.32.5",
        "url": (
            "https://github.com/ollama/ollama/releases/download/v0.32.5/"
            "ollama-windows-amd64-rocm.zip"
        ),
        "sha256": "f2284e7008ffd64eadb7a05ac4ca1a0de843d1e8d0c861aa0923ef855ca94615",
        "size_bytes": 245370090,
    },
    "llmfit": {
        "version": "1.1.8",
        "url": (
            "https://github.com/AlexsJones/llmfit/releases/download/v1.1.8/"
            "llmfit-v1.1.8-x86_64-pc-windows-msvc.zip"
        ),
        "sha256": "bf8a509d68bc02f4cafc7040501938a30841eeb8c496eda51ae886a2f43a88e2",
        "size_bytes": 5249067,
    },
}


@dataclass(frozen=True)
class ProjectFixture:
    root: Path
    ifc_bytes: dict[str, bytes]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(root: Path, relative: str, data: str | bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8", newline="\n")
    else:
        path.write_bytes(data)
    return path


@pytest.fixture
def project_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ProjectFixture:
    root = tmp_path / "projeto fonte com espacos"
    predio = b"ISO-10303-21;\nFILE_NAME('predio');\nEND-ISO-10303-21;\n"
    casa = b"ISO-10303-21;\nFILE_NAME('casa');\nEND-ISO-10303-21;\n"
    ids = b"<?xml version='1.0' encoding='UTF-8'?><ids/>\n"

    files: dict[str, str | bytes] = {
        ".python-version": "3.12.13\n",
        "uv.lock": "version = 1\n",
        "pyproject.toml": "[project]\nname = 'fixture'\n",
        "src/__init__.py": "",
        "src/core.py": b"VALUE = 1\r\n",
        "src/experiment/ground_truth_policy.py": "POLICY_VERSION = 'fixture'\n",
        "src/experiment/ground_truth_value_policy.py": "VALUE_POLICY = 'fixture'\n",
        "src/experiment/ground_truth_validation.py": "VALIDATION = 'fixture'\n",
        "src/experiment/evaluator.py": "EVALUATOR = 'fixture'\n",
        "src/experiment/results/models.lock.json": (
            '{"schema_version":2,"runtime":{"name":"ollama"},"models":[]}\n'
        ),
        "src/suggestion_engine/prompt_templates.py": b'PROMPT_VERSION = "v7.6"\r\n',
        "scripts/run_benchmark.py": "print('runner')\n",
        "scripts/windows_benchmark.py": "print('windows')\n",
        "scripts/build_ground_truths.py": "print('gt')\n",
        "windows/collect-hardware.ps1": "Write-Output '{}'\n",
        "data/ids_templates/residencial_nbr15575.ids": ids,
        "data/ids_schema/ids.xsd": "<schema/>\n",
        "data/cache/bsdd_cache.json": "{}\n",
        "data/evaluation/legacy-reference.lock.json": (
            '{"schema_version":1,"datasets":{}}\n'
        ),
        "data/evaluation/predio/predio_v1.ifc": predio,
        "data/evaluation/casa/casa_v1.ifc": casa,
        "data/evaluation/predio/README.md": "# Predio\n",
        "data/evaluation/casa/README.md": "# Casa\n",
        "references/normative/public/README.md": "# Fontes publicas\n",
        "references/normative/public/sources.yaml": "sources: []\n",
        "windows/EXECUTAR_BENCHMARK.cmd": "@echo off\n",
        "windows/install.ps1": b"Write-Output 'MVP'\r\n",
        "windows/LEIA-ME.txt": b"Execute EXECUTAR_BENCHMARK.cmd\r\n",
        # Estes arquivos parecem permitidos pelo glob amplo de Python, mas nunca podem sair.
        "src/experiment/results/2026-08-01/run.py": "SECRET_RESULT = 1\n",
        "src/.history/old.py": "TOKEN = 'history'\n",
        "src/secrets/token.py": "TOKEN = 'secret'\n",
        ".env": "TOKEN=secret\n",
        "BENCHMARK_RUNNING": "123\n",
        "BENCHMARK_STOP": "stop\n",
        ".claude/settings.local.json": "{}\n",
        "Artigo/draft.py": "conteudo\n",
        "dist/old.py": "resultado\n",
        "build/temp.py": "temporario\n",
    }
    for relative, data in files.items():
        _write(root, relative, data)

    expected_hashes = {"predio": _sha256(predio), "casa": _sha256(casa)}
    monkeypatch.setattr(release_builder, "EXPECTED_IFC_SHA256", expected_hashes)

    ids_hash = _sha256(ids)
    for dataset, ifc_hash in expected_hashes.items():
        _write(
            root,
            f"data/evaluation/{dataset}/ground_truth.yaml",
            (
                "metadata:\n"
                f"  input_ifc_sha256: {ifc_hash}\n"
                f"  ids_sha256: {ids_hash}\n"
                "items: []\n"
            ),
        )

    template = {
        "schema_version": 1,
        "platform": "windows-x86_64",
        "minimum_windows_build": 19045,
        "python_version": "3.12.13",
        "tools": TOOL_PINS,
    }
    _write(
        root,
        "windows/release-manifest.template.json",
        json.dumps(template, indent=2, sort_keys=True) + "\n",
    )
    return ProjectFixture(root=root, ifc_bytes={"predio": predio, "casa": casa})


def test_project_archive_is_deterministic_allowlisted_and_portable(
    project_fixture: ProjectFixture, tmp_path: Path
) -> None:
    first = build_project_zip(project_fixture.root, tmp_path / "first.zip")
    second = build_project_zip(project_fixture.root, tmp_path / "second.zip")

    assert first.sha256 == second.sha256
    assert first.path.read_bytes() == second.path.read_bytes()
    with zipfile.ZipFile(first.path) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        assert {
            ".python-version",
            "uv.lock",
            "pyproject.toml",
            "scripts/run_benchmark.py",
            "scripts/windows_benchmark.py",
            "scripts/build_ground_truths.py",
            "src/experiment/ground_truth_policy.py",
            "src/experiment/ground_truth_value_policy.py",
            "src/experiment/ground_truth_validation.py",
            "src/experiment/evaluator.py",
            "src/experiment/results/models.lock.json",
            "data/evaluation/legacy-reference.lock.json",
            "data/ids_schema/ids.xsd",
            "references/normative/public/sources.yaml",
        } <= set(names)
        assert archive.read("src/core.py") == b"VALUE = 1\n"
        assert (
            archive.read("src/suggestion_engine/prompt_templates.py")
            == b'PROMPT_VERSION = "v7.6"\n'
        )
        assert not any(
            forbidden in name.casefold()
            for name in names
            for forbidden in (
                ".git/",
                ".claude/",
                ".history/",
                "artigo/",
                "dist/",
                "build/",
                "src/secrets/",
                "src/experiment/results/2026-",
            )
        )
        assert not any(
            name.endswith((".env", "BENCHMARK_RUNNING", "BENCHMARK_STOP"))
            for name in names
        )
        for info in archive.infolist():
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            assert info.create_system == 3
            assert (info.external_attr >> 16) & 0o777 == 0o644


def test_release_contains_exact_public_shape_and_canonical_manifest(
    project_fixture: ProjectFixture, tmp_path: Path
) -> None:
    release = build_release(project_fixture.root, tmp_path / "dist")

    relative = {
        path.relative_to(release).as_posix() for path in release.rglob("*") if path.is_file()
    }
    assert relative == {
        "EXECUTAR_BENCHMARK.cmd",
        "LEIA-ME.txt",
        "install.ps1",
        "release-manifest.json",
        "payload/project.zip",
        "payload/datasets/predio_v1.ifc",
        "payload/datasets/casa_v1.ifc",
    }
    manifest_bytes = (release / "release-manifest.json").read_bytes()
    assert (release / "EXECUTAR_BENCHMARK.cmd").read_bytes() == b"@echo off\r\n"
    assert (release / "install.ps1").read_bytes() == b"Write-Output 'MVP'\n"
    assert (release / "LEIA-ME.txt").read_bytes().endswith(b"\n")
    assert b"\r\n" not in (release / "LEIA-ME.txt").read_bytes()
    assert manifest_bytes.endswith(b"\n")
    assert b"\r\n" not in manifest_bytes
    manifest = json.loads(manifest_bytes)
    assert set(manifest) == {
        "schema_version",
        "platform",
        "minimum_windows_build",
        "python_version",
        "tools",
        "release_id",
        "source_commit",
        "project",
        "datasets",
        "inputs",
    }
    # Derivado da constante, nao fixado: RELEASE_DATE e bumpado a cada
    # republicacao e o teste nao deve quebrar por isso.
    assert re.fullmatch(
        rf"ifcqc-{re.escape(RELEASE_DATE)}-[0-9a-f]{{12}}", manifest["release_id"]
    )
    assert release.name == f"IFCQC-Benchmark-Windows-x64-{manifest['release_id']}"
    # O fixture vive sob um Git externo; esse commit não pode vazar para a release.
    assert re.fullmatch(r"tree-[0-9a-f]{64}", manifest["source_commit"])
    assert manifest["tools"] == TOOL_PINS


def test_manifest_hashes_every_local_payload_and_internal_input(
    project_fixture: ProjectFixture, tmp_path: Path
) -> None:
    release = build_release(project_fixture.root, tmp_path / "dist")
    manifest = json.loads((release / "release-manifest.json").read_text(encoding="utf-8"))

    for record in (manifest["project"], *manifest["datasets"].values()):
        path = release / record["path"]
        assert set(record) == {"path", "size_bytes", "sha256"}
        assert record["size_bytes"] == path.stat().st_size
        assert record["sha256"] == _sha256(path.read_bytes())
        assert re.fullmatch(r"[0-9a-f]{64}", record["sha256"])

    with zipfile.ZipFile(release / manifest["project"]["path"]) as archive:
        model_lock = manifest["inputs"]["models_lock"]
        prompt = manifest["inputs"]["prompt_templates"]
        assert prompt["version"] == "v7.6"
        for record in (model_lock, prompt):
            payload = archive.read(record["project_path"])
            assert record["size_bytes"] == len(payload)
            assert record["sha256"] == _sha256(payload)
        for dataset, dataset_inputs in manifest["inputs"]["datasets"].items():
            assert dataset_inputs["ifc"] == manifest["datasets"][dataset]
            for key in ("ground_truth", "ids"):
                record = dataset_inputs[key]
                payload = archive.read(record["project_path"])
                assert record["size_bytes"] == len(payload)
                assert record["sha256"] == _sha256(payload)


@pytest.mark.parametrize(
    "missing",
    [
        "data/evaluation/predio/predio_v1.ifc",
        "data/evaluation/casa/casa_v1.ifc",
        "data/evaluation/predio/ground_truth.yaml",
        "data/evaluation/casa/ground_truth.yaml",
        "data/evaluation/legacy-reference.lock.json",
        "data/ids_templates/residencial_nbr15575.ids",
        "src/experiment/results/models.lock.json",
        "src/suggestion_engine/prompt_templates.py",
    ],
)
def test_builder_rejects_missing_required_input(
    project_fixture: ProjectFixture, tmp_path: Path, missing: str
) -> None:
    (project_fixture.root / missing).unlink()

    with pytest.raises(ReleaseBuildError, match="ausente"):
        build_release(project_fixture.root, tmp_path / "dist")


def test_builder_rejects_ifc_whose_sha256_differs_from_frozen_pin(
    project_fixture: ProjectFixture, tmp_path: Path
) -> None:
    (project_fixture.root / "data/evaluation/casa/casa_v1.ifc").write_bytes(b"tampered")

    with pytest.raises(ReleaseBuildError, match=r"IFC.*SHA-256"):
        build_release(project_fixture.root, tmp_path / "dist")


def test_builder_rejects_symlink_or_reparse_point(
    project_fixture: ProjectFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    linked = project_fixture.root / "src/linked.py"
    linked.write_text("x = 1\n", encoding="utf-8", newline="\n")
    real_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda self: self == linked or real_is_symlink(self),
    )

    with pytest.raises(ReleaseBuildError, match="symlink/reparse"):
        build_project_zip(project_fixture.root, tmp_path / "project.zip")


def test_builder_rejects_nonempty_release_destination(
    project_fixture: ProjectFixture, tmp_path: Path
) -> None:
    output_root = tmp_path / "dist"
    first = build_release(project_fixture.root, output_root)
    (first / "extra.txt").write_text("do not overwrite\n", encoding="utf-8")

    with pytest.raises(ReleaseBuildError, match="não está vazio"):
        build_release(project_fixture.root, output_root)
    assert (first / "extra.txt").read_text(encoding="utf-8") == "do not overwrite\n"


def test_builder_rejects_prompt_version_other_than_pinned(
    project_fixture: ProjectFixture, tmp_path: Path
) -> None:
    prompt = project_fixture.root / "src/suggestion_engine/prompt_templates.py"
    prompt.write_text('PROMPT_VERSION = "v7.2"\n', encoding="utf-8", newline="\n")

    with pytest.raises(ReleaseBuildError, match=r"PROMPT_VERSION.*v7.6"):
        build_release(project_fixture.root, tmp_path / "dist")
