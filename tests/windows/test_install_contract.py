from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INSTALL_PS1 = ROOT / "windows" / "install.ps1"
ENTRYPOINT_CMD = ROOT / "windows" / "EXECUTAR_BENCHMARK.cmd"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tool_pins() -> dict[str, dict[str, str | int]]:
    return {
        "uv": {
            "version": "0.12.3",
            "url": (
                "https://github.com/astral-sh/uv/releases/download/0.12.3/"
                "uv-x86_64-pc-windows-msvc.zip"
            ),
            "sha256": (
                "b23350c79e8ad0192b8124af13a0f17e"
                "8d4e4549524785e1aef389ae5a06990e"
            ),
            "size_bytes": 19_013_455,
        },
        "ollama": {
            "version": "0.32.5",
            "url": (
                "https://github.com/ollama/ollama/releases/download/v0.32.5/"
                "ollama-windows-amd64.zip"
            ),
            "sha256": (
                "7c941ae084569d298062d29f8139163a"
                "3187c76dbca0479c70d085e78fd8c7bb"
            ),
            "size_bytes": 1_457_824_795,
        },
        "ollama_rocm": {
            "version": "0.32.5",
            "url": (
                "https://github.com/ollama/ollama/releases/download/v0.32.5/"
                "ollama-windows-amd64-rocm.zip"
            ),
            "sha256": (
                "f2284e7008ffd64eadb7a05ac4ca1a0d"
                "e843d1e8d0c861aa0923ef855ca94615"
            ),
            "size_bytes": 245_370_090,
        },
        "llmfit": {
            "version": "1.1.8",
            "url": (
                "https://github.com/AlexsJones/llmfit/releases/download/v1.1.8/"
                "llmfit-v1.1.8-x86_64-pc-windows-msvc.zip"
            ),
            "sha256": (
                "bf8a509d68bc02f4cafc7040501938a3"
                "0841eeb8c496eda51ae886a2f43a88e2"
            ),
            "size_bytes": 5_249_067,
        },
    }


def _record(path: str, data: bytes) -> dict[str, str | int]:
    return {"path": path, "size_bytes": len(data), "sha256": _sha256(data)}


@pytest.fixture
def release_fixture(tmp_path: Path) -> Path:
    release = tmp_path / "Pacote fonte"
    payloads = {
        "payload/project.zip": b"project archive fixture",
        "payload/datasets/predio_v1.ifc": b"ISO-10303-21; PREDIO; END-ISO-10303-21;",
        "payload/datasets/casa_v1.ifc": b"ISO-10303-21; CASA; END-ISO-10303-21;",
    }
    for relative, data in payloads.items():
        target = release / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    project = _record("payload/project.zip", payloads["payload/project.zip"])
    predio = _record(
        "payload/datasets/predio_v1.ifc",
        payloads["payload/datasets/predio_v1.ifc"],
    )
    casa = _record(
        "payload/datasets/casa_v1.ifc", payloads["payload/datasets/casa_v1.ifc"]
    )
    internal = {
        "project_path": "data/ids_templates/residencial_nbr15575.ids",
        "size_bytes": 1,
        "sha256": "1" * 64,
    }
    manifest = {
        "schema_version": 1,
        "platform": "windows-x86_64",
        "minimum_windows_build": 19045,
        "python_version": "3.12.13",
        "tools": _tool_pins(),
        "release_id": "ifcqc-2026-08-08-aaaaaaaaaaaa",
        "source_commit": "a" * 40,
        "project": project,
        "datasets": {"predio": predio, "casa": casa},
        "inputs": {
            "models_lock": {
                **internal,
                "project_path": "src/experiment/results/models.lock.json",
            },
            "prompt_templates": {
                **internal,
                "project_path": "src/suggestion_engine/prompt_templates.py",
                "version": "v7.2",
            },
            "datasets": {
                dataset: {
                    "ifc": record,
                    "ground_truth": {
                        **internal,
                        "project_path": f"data/evaluation/{dataset}/ground_truth.yaml",
                    },
                    "ids": dict(internal),
                }
                for dataset, record in (("predio", predio), ("casa", casa))
            },
        },
    }
    (release / "release-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return release


def _powershell(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    child_env = os.environ.copy()
    child_env.update(env or {})
    return subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(INSTALL_PS1),
            *args,
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
        env=child_env,
    )


def _read_manifest(release: Path) -> dict[str, object]:
    return json.loads((release / "release-manifest.json").read_text(encoding="utf-8"))


def _write_manifest(release: Path, manifest: dict[str, object]) -> None:
    (release / "release-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _network_env(sentinel: Path) -> dict[str, str]:
    return {"IFCQC_TESTING": "1", "IFCQC_NETWORK_SENTINEL": str(sentinel)}


def test_powershell_script_parses() -> None:
    command = (
        "$errors=$null; "
        f"[void][Management.Automation.Language.Parser]::ParseFile('{INSTALL_PS1}',"
        "[ref]$null,[ref]$errors); if($errors){$errors; exit 1}"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-Command", command],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_validate_only_accepts_matching_payload(release_fixture: Path) -> None:
    result = _powershell("-PackageRoot", str(release_fixture), "-ValidateOnly")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("PAYLOAD_OK")


def test_validate_only_rejects_tampered_ifc(release_fixture: Path) -> None:
    (release_fixture / "payload/datasets/casa_v1.ifc").write_bytes(b"tampered")

    result = _powershell("-PackageRoot", str(release_fixture), "-ValidateOnly")

    assert result.returncode != 0
    assert "SHA-256" in result.stderr


def test_plan_only_handles_spaces_without_persistent_writes(
    release_fixture: Path, tmp_path: Path
) -> None:
    spaced = tmp_path / "Pacote com espacos"
    shutil.copytree(release_fixture, spaced)
    planned_app_root = tmp_path / "App planejado com espacos"

    result = _powershell(
        "-PackageRoot",
        str(spaced),
        "-AppRoot",
        str(planned_app_root),
        "-PlanOnly",
    )

    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout.splitlines()[-1])
    assert plan["python_version"] == "3.12.13"
    assert Path(plan["install_root"]).resolve() == planned_app_root.resolve()
    assert Path(plan["package_root"]).resolve() == spaced.resolve()
    assert not planned_app_root.exists()
    assert not (spaced / ".venv").exists()


@pytest.mark.parametrize(
    ("probe", "expected_error"),
    [
        (
            {
                "windows_build": 19044,
                "os_architecture": "64-bit",
                "process_architecture": "AMD64",
            },
            "build",
        ),
        (
            {
                "windows_build": 19045,
                "os_architecture": "32-bit",
                "process_architecture": "x86",
            },
            "x64",
        ),
    ],
)
def test_platform_failure_happens_before_any_network(
    release_fixture: Path,
    tmp_path: Path,
    probe: dict[str, str | int],
    expected_error: str,
) -> None:
    probe_path = tmp_path / "probe.json"
    probe_path.write_text(json.dumps(probe), encoding="utf-8")
    sentinel = tmp_path / "network-called"

    result = _powershell(
        "-PackageRoot",
        str(release_fixture),
        "-TestProbeJson",
        str(probe_path),
        env=_network_env(sentinel),
    )

    assert result.returncode != 0
    assert expected_error in result.stderr
    assert not sentinel.exists()


def test_payload_failure_happens_before_network(
    release_fixture: Path, tmp_path: Path
) -> None:
    sentinel = tmp_path / "network-called"
    (release_fixture / "payload/project.zip").write_bytes(b"tampered")

    result = _powershell(
        "-PackageRoot",
        str(release_fixture),
        "-AppRoot",
        str(tmp_path / "app"),
        env=_network_env(sentinel),
    )

    assert result.returncode != 0
    assert "SHA-256" in result.stderr
    assert not sentinel.exists()


def test_pin_failure_happens_before_network(
    release_fixture: Path, tmp_path: Path
) -> None:
    sentinel = tmp_path / "network-called"
    manifest = _read_manifest(release_fixture)
    manifest["tools"]["uv"]["version"] = "latest"  # type: ignore[index]
    _write_manifest(release_fixture, manifest)

    result = _powershell(
        "-PackageRoot",
        str(release_fixture),
        env=_network_env(sentinel),
    )

    assert result.returncode != 0
    assert "fixado" in result.stderr
    assert not sentinel.exists()


def test_traversal_path_fails_before_network(
    release_fixture: Path, tmp_path: Path
) -> None:
    sentinel = tmp_path / "network-called"
    manifest = _read_manifest(release_fixture)
    manifest["project"]["path"] = "../project.zip"  # type: ignore[index]
    _write_manifest(release_fixture, manifest)

    result = _powershell(
        "-PackageRoot",
        str(release_fixture),
        env=_network_env(sentinel),
    )

    assert result.returncode != 0
    assert "Caminho" in result.stderr
    assert not sentinel.exists()


def test_write_failure_happens_before_network(
    release_fixture: Path, tmp_path: Path
) -> None:
    sentinel = tmp_path / "network-called"
    app_root_is_a_file = tmp_path / "not-a-directory"
    app_root_is_a_file.write_text("x", encoding="utf-8")

    result = _powershell(
        "-PackageRoot",
        str(release_fixture),
        "-AppRoot",
        str(app_root_is_a_file),
        env=_network_env(sentinel),
    )

    assert result.returncode != 0
    assert "AppRoot" in result.stderr
    assert not sentinel.exists()


def test_cmd_propagates_install_failure_from_path_with_spaces(
    release_fixture: Path, tmp_path: Path
) -> None:
    package = tmp_path / "Release final com espacos"
    shutil.copytree(release_fixture, package)
    shutil.copyfile(INSTALL_PS1, package / "install.ps1")
    shutil.copyfile(ENTRYPOINT_CMD, package / "EXECUTAR_BENCHMARK.cmd")
    (package / "payload/datasets/predio_v1.ifc").write_bytes(b"tampered")
    sentinel = tmp_path / "network-called"
    env = os.environ.copy()
    env.update(_network_env(sentinel))
    env["IFCQC_NO_PAUSE"] = "1"

    result = subprocess.run(
        ["cmd.exe", "/d", "/c", str(package / "EXECUTAR_BENCHMARK.cmd")],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
        cwd=package,
        env=env,
    )

    assert result.returncode != 0
    assert not sentinel.exists()
