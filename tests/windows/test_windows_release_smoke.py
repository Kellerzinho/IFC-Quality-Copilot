from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.parse
import zipfile
from pathlib import Path

import httpx
import pytest
import yaml

from scripts.build_windows_release import build_release, sha256_file
from src.experiment.model_lock import load_model_lock
from src.experiment.windows_runtime import safe_extract_zip

ROOT = Path(__file__).resolve().parents[2]
MODEL_LOCK = ROOT / "src/experiment/results/models.lock.json"
PREDIO_SHA = "a71c8be30d82760218f5b3f3a1c476b49e3f30e608b0065916b9d5206a1a6dd0"
CASA_SHA = "3b84789c7396449f2c8a3d2f4a66468d81e59f8351ebd4b71fad161fa06112f2"
RUN_E2E = os.environ.get("IFCQC_WINDOWS_SMOKE") == "1"


@pytest.fixture(scope="module")
def built_release(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Monta uma vez a release real; o fixture não chama rede."""

    output = tmp_path_factory.mktemp("Pacote final com espacos") / "dist"
    return build_release(ROOT, output)


def _powershell(
    release: Path, *arguments: str, network_sentinel: Path
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "IFCQC_TESTING": "1",
            "IFCQC_NETWORK_SENTINEL": str(network_sentinel),
        }
    )
    return subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(release / "install.ps1"),
            "-PackageRoot",
            str(release),
            *arguments,
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
        env=env,
    )


def _project_member_is_allowlisted(name: str) -> bool:
    exact = {
        ".python-version",
        "uv.lock",
        "pyproject.toml",
        "scripts/run_benchmark.py",
        "scripts/windows_benchmark.py",
        "scripts/build_ground_truths.py",
        "windows/collect-hardware.ps1",
        "data/cache/bsdd_cache.json",
        "data/evaluation/predio/ground_truth.yaml",
        "data/evaluation/predio/README.md",
        "data/evaluation/casa/ground_truth.yaml",
        "data/evaluation/casa/README.md",
        "data/evaluation/legacy-reference.lock.json",
        "src/experiment/results/models.lock.json",
    }
    if name in exact:
        return True
    return any(
        name.startswith(prefix) and name.endswith(suffix)
        for prefix, suffix in (
            ("src/", ".py"),
            ("data/ids_templates/", ".ids"),
            ("data/ids_schema/", ".xsd"),
            ("references/normative/public/", ".md"),
            ("references/normative/public/", ".yaml"),
        )
    )


def test_readme_explains_only_required_action_and_constraints() -> None:
    """Falha se a entrega deixar de explicar a operação segura de um clique."""

    text = (ROOT / "windows/LEIA-ME.txt").read_text(encoding="utf-8")
    required = [
        "EXECUTAR_BENCHMARK.cmd",
        "Windows 10 22H2",
        "55 GiB",
        "internet",
        "muitas horas",
        "RESULTADO_IFCQC",
        "não instale",
        "SHA-256 não é assinatura",
        "canal confiável",
        "QUARANTINE_RECOVERY_REQUIRED",
    ]
    folded = text.casefold()
    assert [value for value in required if value.casefold() not in folded] == []


def test_manual_checklist_keeps_unexecuted_clean_machine_cases_pending() -> None:
    """Falha se o documento puder sugerir aceite real sem as duas máquinas."""

    text = (ROOT / "docs/testing/windows-one-click-acceptance.md").read_text(encoding="utf-8")
    required = [
        "Windows 10 22H2 build 19045 x64",
        "Windows 11 x64",
        "Ctrl+C",
        "BENCHMARK_STOP",
        "20 pares válidos (JSON + JSONL)",
        "quarentena reconciliada",
        "PID/token da execução",
        "SHA-256 dos dois membros",
        "/api/pull",
        "PENDENTE",
    ]
    assert all(value in text for value in required)
    assert "IFCQC_WINDOWS_SMOKE=1" in text


def test_built_release_has_exact_tree_and_verified_payloads(built_release: Path) -> None:
    """Falha se faltar um dos sete arquivos ou se o manifesto não cobrir o payload."""

    relative = {
        path.relative_to(built_release).as_posix()
        for path in built_release.rglob("*")
        if path.is_file()
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

    manifest = json.loads((built_release / "release-manifest.json").read_text(encoding="utf-8"))
    records = [manifest["project"], *manifest["datasets"].values()]
    for record in records:
        payload = built_release / record["path"]
        assert payload.stat().st_size == record["size_bytes"]
        assert sha256_file(payload) == record["sha256"]
    assert sha256_file(built_release / "payload/datasets/predio_v1.ifc") == PREDIO_SHA
    assert sha256_file(built_release / "payload/datasets/casa_v1.ifc") == CASA_SHA


def test_project_zip_is_allowlisted_and_contains_no_local_state(
    built_release: Path,
) -> None:
    """Falha se resultados, sentinelas ou nomes de segredo vazarem no ZIP."""

    archive_path = built_release / "payload/project.zip"
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()

    assert names == sorted(names)
    assert all(_project_member_is_allowlisted(name) for name in names)
    required = {
        ".python-version",
        "uv.lock",
        "pyproject.toml",
        "scripts/run_benchmark.py",
        "scripts/windows_benchmark.py",
        "src/experiment/results/models.lock.json",
        "data/evaluation/predio/ground_truth.yaml",
        "data/evaluation/casa/ground_truth.yaml",
        "data/evaluation/legacy-reference.lock.json",
        "src/experiment/ground_truth_policy.py",
        "src/experiment/ground_truth_value_policy.py",
        "src/experiment/ground_truth_validation.py",
        "src/experiment/evaluator.py",
    }
    assert required <= set(names)

    forbidden_parts = {
        ".git",
        ".claude",
        ".env",
        ".venv",
        "__pycache__",
        "artigo",
        "dist",
        "build",
        "secrets",
        "history",
        ".history",
    }
    for name in names:
        parts = tuple(part.casefold() for part in Path(name).parts)
        assert not forbidden_parts.intersection(parts), name
        assert parts[-1] not in {"benchmark_running", "benchmark_stop"}, name
        assert not parts[-1].startswith(("credentials.", "secret.")), name
        if parts[:3] == ("src", "experiment", "results"):
            assert name == "src/experiment/results/models.lock.json"


def test_project_zip_contains_integral_ground_truths_and_legacy_lock(
    built_release: Path,
) -> None:
    with zipfile.ZipFile(built_release / "payload/project.zip") as archive:
        assert "data/evaluation/legacy-reference.lock.json" in archive.namelist()
        for dataset, expected in (("predio", 4720), ("casa", 263)):
            document = yaml.safe_load(
                archive.read(f"data/evaluation/{dataset}/ground_truth.yaml")
            )
            assert document["metadata"]["protocol"] == "full-coverage-equivalent-v1"
            assert document["metadata"]["total_items"] == expected
            assert len(document["items"]) == expected
            assert document["skipped"] == []


def test_built_release_validate_and_plan_are_offline(built_release: Path, tmp_path: Path) -> None:
    """Falha se o caminho seguro tocar a rede ou planejar fora do AppRoot informado."""

    sentinel = tmp_path / "network-called"
    validate = _powershell(
        built_release,
        "-ValidateOnly",
        network_sentinel=sentinel,
    )
    assert validate.returncode == 0, validate.stdout + validate.stderr
    assert validate.stdout.strip().endswith("PAYLOAD_OK")
    assert not sentinel.exists()

    app_root = tmp_path / "Aplicacao planejada com espacos"
    plan_result = _powershell(
        built_release,
        "-AppRoot",
        str(app_root),
        "-PlanOnly",
        network_sentinel=sentinel,
    )
    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    plan = json.loads(plan_result.stdout.splitlines()[-1])
    assert Path(plan["install_root"]).resolve() == app_root.resolve()
    assert Path(plan["package_root"]).resolve() == built_release.resolve()
    assert plan["python_version"] == "3.12.13"
    assert not app_root.exists()
    assert not sentinel.exists()


def test_clean_project_imports_locked_matrix_and_both_datasets(
    built_release: Path, tmp_path: Path
) -> None:
    """Falha se project.zip depender de um arquivo local que não foi empacotado."""

    clean = tmp_path / "Projeto extraido com espacos"
    safe_extract_zip(built_release / "payload/project.zip", clean)
    probe = (
        "import json\n"
        "from pathlib import Path\n"
        "from src.experiment.model_lock import load_model_lock\n"
        "import scripts.run_benchmark as runner\n"
        "lock = load_model_lock(Path('src/experiment/results/models.lock.json'))\n"
        "print(json.dumps({'python': Path('.python-version').read_text().strip(), "
        "'schema': lock.schema_version, 'models': len(lock.models), "
        "'datasets': [item['key'] for item in runner.DATASETS]}))\n"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(clean)
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=clean,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    observed = json.loads(result.stdout.splitlines()[-1])
    assert observed == {
        "python": "3.12.13",
        "schema": 2,
        "models": 10,
        "datasets": ["predio", "casa"],
    }


@pytest.mark.windows_e2e
@pytest.mark.skipif(not RUN_E2E, reason="defina IFCQC_WINDOWS_SMOKE=1")
def test_opt_in_real_ground_truth_check_from_clean_release(
    built_release: Path, tmp_path: Path
) -> None:
    """Confere os GTs reais sem alterá-los; continua opt-in por ser demorado."""

    clean = tmp_path / "Pasta limpa com espacos"
    safe_extract_zip(built_release / "payload/project.zip", clean)
    for dataset in ("predio", "casa"):
        target = clean / "data/evaluation" / dataset / f"{dataset}_v1.ifc"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            built_release / "payload/datasets" / f"{dataset}_v1.ifc",
            target,
        )
    before = {
        dataset: sha256_file(clean / "data/evaluation" / dataset / "ground_truth.yaml")
        for dataset in ("predio", "casa")
    }
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_ground_truths.py",
            "--check",
            "--dataset",
            "all",
        ],
        cwd=clean,
        text=True,
        capture_output=True,
        timeout=900,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK predio" in result.stdout
    assert "OK casa" in result.stdout
    assert before == {
        dataset: sha256_file(clean / "data/evaluation" / dataset / "ground_truth.yaml")
        for dataset in ("predio", "casa")
    }


@pytest.mark.windows_e2e
@pytest.mark.skipif(not RUN_E2E, reason="defina IFCQC_WINDOWS_SMOKE=1")
def test_opt_in_local_ollama_minimal_response() -> None:
    """Exige explicitamente modelo do lock já presente e nunca chama /api/pull."""

    base_url = os.environ.get("IFCQC_SMOKE_OLLAMA_URL", "")
    model = os.environ.get("IFCQC_SMOKE_MODEL", "")
    missing_message = "defina IFCQC_SMOKE_OLLAMA_URL e IFCQC_SMOKE_MODEL para o smoke opt-in"
    assert base_url, missing_message
    assert model, missing_message
    assert urllib.parse.urlsplit(base_url).hostname in {"127.0.0.1", "::1", "localhost"}
    locked = {entry.name: entry.digest for entry in load_model_lock(MODEL_LOCK).models}

    tags_response = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=10)
    tags_response.raise_for_status()
    tags = tags_response.json()["models"]
    installed = {str(row["name"]): str(row["digest"]).removeprefix("sha256:") for row in tags}
    assert model in locked
    assert installed.get(model) == locked[model]

    response = httpx.post(
        f"{base_url.rstrip('/')}/api/generate",
        json={"model": model, "prompt": "Responda apenas: ok", "stream": False},
        timeout=120,
    )
    response.raise_for_status()
    assert str(response.json()["response"]).strip()
