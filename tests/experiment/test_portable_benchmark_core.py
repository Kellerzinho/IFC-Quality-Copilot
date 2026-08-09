"""Smoke integrado do núcleo portátil sem Ollama, rede ou IFCs grandes."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import ifcopenshell.api
import ifcopenshell.api.owner.settings
import ifcopenshell.guid

import scripts.run_benchmark as benchmark
import src.experiment.runner as runner_module
from src.bsdd.client import BSDDClient
from src.config import get_settings
from src.experiment.evidence_bundle import (
    collect_forbidden_values,
    create_evidence_zip,
    filter_llmfit_recommendations,
    parse_llmfit_recommendations,
    scan_sensitive_text,
    validate_evidence_archive,
    validate_manifest,
)
from src.experiment.execution_identity import DatasetIdentity, ExecutionIdentity
from src.experiment.model_lock import load_model_lock
from src.experiment.runner import ExperimentRunner
from src.models import Suggestion, SuggestionMetrics, SuggestionSet


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_minimal_ifc(path: Path, *, seed: int, monkeypatch) -> str:
    model = ifcopenshell.api.run("project.create_file", version="IFC2X3")
    person = ifcopenshell.api.run(
        "owner.add_person", model, identification="eng", family_name="Eng"
    )
    organisation = ifcopenshell.api.run(
        "owner.add_organisation", model, identification="IFCQC", name="IFCQC"
    )
    user = ifcopenshell.api.run(
        "owner.add_person_and_organisation",
        model,
        person=person,
        organisation=organisation,
    )
    application = ifcopenshell.api.run("owner.add_application", model)
    with monkeypatch.context() as owner_patch:
        owner_patch.setattr(ifcopenshell.api.owner.settings, "get_user", lambda _model: user)
        owner_patch.setattr(
            ifcopenshell.api.owner.settings,
            "get_application",
            lambda _model: application,
        )
        ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Teste")
        ifcopenshell.api.run("unit.assign_unit", model)
        storey = ifcopenshell.api.run(
            "root.create_entity", model, ifc_class="IfcBuildingStorey", name="P1"
        )
        space = model.create_entity(
            "IfcSpace",
            GlobalId=ifcopenshell.guid.compress(f"{seed:032x}"),
            Name="Room 1",
            LongName="Room 1",
        )
        model.create_entity(
            "IfcRelContainedInSpatialStructure",
            GlobalId=ifcopenshell.guid.compress(f"{seed + 1:032x}"),
            RelatingStructure=storey,
            RelatedElements=[space],
        )
        quantities = ifcopenshell.api.run(
            "pset.add_qto", model, product=space, name="Qto_SpaceBaseQuantities"
        )
        ifcopenshell.api.run(
            "pset.edit_qto",
            model,
            qto=quantities,
            properties={"NetFloorArea": 10.0},
        )
    for index, entity in enumerate(model.by_type("IfcRoot"), start=2):
        entity.GlobalId = ifcopenshell.guid.compress(f"{seed + index:032x}")
    for owner_history in model.by_type("IfcOwnerHistory"):
        owner_history.CreationDate = 1786190400
    model.header.file_name.name = path.name
    model.header.file_name.time_stamp = "2026-08-08T00:00:00"
    model.write(path)
    return space.GlobalId


def _write_ground_truth(path: Path, element_guid: str) -> None:
    path.write_text(
        "\n".join(
            (
                "metadata:",
                "  source: portable-core-smoke",
                "items:",
                f'  - element_guid: "{element_guid}"',
                "    issue_type: space_unnamed",
                '    expected_value: "Sala de Estar"',
                "    verified: true",
                "",
            )
        ),
        encoding="utf-8",
    )


def _write_minimal_ids(path: Path) -> None:
    path.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<ids:ids xmlns:ids="http://standards.buildingsmart.org/IDS"
         xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <ids:specifications>
    <ids:specification name="Smoke">
      <ids:applicability>
        <ids:entity>
          <ids:name><ids:simpleValue>IFCSPACE</ids:simpleValue></ids:name>
        </ids:entity>
      </ids:applicability>
      <ids:requirements />
    </ids:specification>
  </ids:specifications>
</ids:ids>
""",
        encoding="utf-8",
    )


def _suggestions_without_llm(issues, _context, on_progress=None, **_kwargs):
    results = []
    for issue in issues:
        results.append(
            SuggestionSet(
                issue_id=issue.id,
                suggestions=[
                    Suggestion(
                        label="Sala de Estar",
                        value="Sala de Estar",
                        justification="fixture determinístico",
                        confidence="alta",
                        source="llm",
                    )
                ],
                metrics=SuggestionMetrics(
                    issue_id=issue.id,
                    attempts=1,
                    final_status="ready",
                    llm_total_ms=1.0,
                    output_tokens=4,
                ),
            )
        )
    if on_progress is not None:
        on_progress(len(issues), len(issues))
    return results


def test_portable_core_runs_exact_matrix_and_publishes_private_evidence(tmp_path, monkeypatch):
    """Quebra se identidade, matriz, pares ou privacidade deixarem de ser integrais."""
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    lock_path = inputs / "models.lock.json"
    prompt_path = inputs / "prompt_templates.py"
    ids_path = inputs / "requirements.ids"
    shutil.copy2(benchmark.LOCK_FILE, lock_path)
    shutil.copy2(benchmark.PROMPT_FILE, prompt_path)
    _write_minimal_ids(ids_path)

    dataset_rows = []
    dataset_identities = []
    for key, building_type, seed in (
        ("predio", "Residencial multifamiliar", 100),
        ("casa", "Residencial unifamiliar", 200),
    ):
        dataset_dir = inputs / key
        dataset_dir.mkdir()
        ifc_path = dataset_dir / f"{key}_v1.ifc"
        gt_path = dataset_dir / "ground_truth.yaml"
        element_guid = _write_minimal_ifc(ifc_path, seed=seed, monkeypatch=monkeypatch)
        _write_ground_truth(gt_path, element_guid)
        context = {
            "building_type": building_type,
            "bioclimatic_zone": "4A",
        }
        dataset_rows.append(
            {
                "key": key,
                "ifc": ifc_path,
                "gt": gt_path,
                "issue_types": ["space_unnamed"],
                "building_context": context,
            }
        )
        dataset_identities.append(
            DatasetIdentity(
                key=key,
                ifc_sha256=_sha256(ifc_path),
                ground_truth_sha256=_sha256(gt_path),
                ids_sha256=_sha256(ids_path),
                building_context=tuple(sorted(context.items())),
            )
        )

    identity = ExecutionIdentity(
        release_id="portable-core-smoke-r1",
        project_sha256=hashlib.sha256(b"portable-core-smoke").hexdigest(),
        models_lock_sha256=_sha256(lock_path),
        datasets=tuple(dataset_identities),
        replica_count=1,
        cache_enabled=False,
        prompt_version=benchmark.PROMPT_VERSION,
        prompt_sha256=_sha256(prompt_path),
        reuse_equivalent=True,
    )
    identity_path = inputs / "execution-identity.json"
    identity_path.write_text(
        json.dumps(asdict(identity), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(benchmark, "LOCK_FILE", lock_path)
    monkeypatch.setattr(benchmark, "PROMPT_FILE", prompt_path)
    monkeypatch.setattr(benchmark, "IDS_PATH", ids_path)
    monkeypatch.setattr(benchmark, "DATASETS", dataset_rows)
    monkeypatch.setattr(benchmark, "PID_FILE", tmp_path / "BENCHMARK_RUNNING")
    monkeypatch.setattr(benchmark, "STOP_FILE", tmp_path / "BENCHMARK_STOP")
    lock = load_model_lock(lock_path)
    installed_digests = {model.name: model.digest for model in lock.models}
    monkeypatch.setattr(benchmark, "_installed_digest", lambda model: installed_digests[model])
    monkeypatch.setattr(benchmark, "_unload_model", lambda _model: None)

    original_runner_init = ExperimentRunner.__init__

    def offline_runner_init(self):
        original_runner_init(self, suggestion_batch_fn=_suggestions_without_llm)

    monkeypatch.setattr(ExperimentRunner, "__init__", offline_runner_init)
    monkeypatch.setattr(BSDDClient, "_get_cached_or_fetch", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runner_module, "gpu_residency", lambda *_args: None)
    monkeypatch.setattr(
        runner_module, "ollama_model_digest", lambda model, _url: installed_digests[model]
    )
    monkeypatch.setattr(runner_module, "_ollama_version", lambda: "0.32.5")
    monkeypatch.setattr(
        runner_module,
        "hardware_snapshot",
        lambda: {
            "gpus": [{"name": "Synthetic GPU", "memory_total": "24 GiB", "driver": "test"}],
            "gpu_count": 1,
            "cpu": "Synthetic CPU",
            "cpu_count": 16,
            "ram_total_gb": 64.0,
            "os": "Windows 11",
            "python": "3.12.13",
        },
    )

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            instant = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
            return instant if tz is not None else instant.replace(tzinfo=None)

    monkeypatch.setattr(benchmark, "datetime", FrozenDateTime)
    monkeypatch.setenv("BSDD_CACHE_ENABLED", "false")
    monkeypatch.setenv("BSDD_CACHE_PATH", str(tmp_path / "bsdd-cache.json"))
    monkeypatch.setenv("POST_VALIDATION_ENABLED", "false")
    get_settings.cache_clear()

    results_root = tmp_path / "results"
    return_code = benchmark.main(
        [
            "--replicas",
            "1",
            "--no-cache",
            "--reuse-equivalent",
            "--execution-identity",
            str(identity_path),
            "--results-root",
            str(results_root),
        ]
    )

    aggregate_paths = sorted(results_root.rglob("run_*.json"))
    issues_paths = sorted(results_root.rglob("run_*_issues.jsonl"))
    runs = [json.loads(path.read_text(encoding="utf-8")) for path in aggregate_paths]
    locked_model_pairs = [(model.name, model.digest) for model in lock.models]
    loaded_identity = benchmark._load_and_validate_execution_identity(identity_path)
    expectations_by_path = {}
    for dataset in loaded_identity.datasets:
        for model_name, model_digest in locked_model_pairs:
            path = benchmark._stage_path(results_root, dataset.key, model_name, 0)
            expectations_by_path[path] = benchmark._stage_expectation(
                loaded_identity, dataset, model_name, model_digest, 0
            )

    assert return_code == 0
    assert len(aggregate_paths) == 20
    assert len(issues_paths) == 20
    assert len(runs) == 20
    assert len(expectations_by_path) == 20
    assert {run["metadata"]["dataset_key"] for run in runs} == {"predio", "casa"}
    assert all(run["metadata"]["reuse_equivalent"] is True for run in runs)
    assert all(run["metadata"]["cache_enabled"] is False for run in runs)
    assert all(run["metadata"]["replica_index"] == 0 for run in runs)
    assert all(run["issue_counts"]["total_issues"] == 1 for run in runs)
    assert all(run["metadata"]["building_context"]["bioclimatic_zone"] == "4A" for run in runs)
    assert all(
        benchmark._stage_done(path, expectation)
        for path, expectation in expectations_by_path.items()
    )
    assert benchmark._invalid_matrix_stages(results_root, loaded_identity, locked_model_pairs) == []
    assert len({run["metadata"]["execution_identity_sha256"] for run in runs}) == 1

    evidence_root = tmp_path / "evidence"
    evidence_results = evidence_root / "benchmark-results"
    shutil.copytree(results_root, evidence_results)
    first_metadata = runs[0]["metadata"]
    (evidence_root / "hardware.json").write_text(
        json.dumps(first_metadata["hardware"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    llmfit_rows = parse_llmfit_recommendations(
        {
            "models": [
                {"name": lock.models[0].name, "ollama_name": lock.models[0].name},
                {
                    "name": "larger-local-70b",
                    "ollama_name": "larger-local:70b",
                    "fit": "synthetic-compatible",
                },
            ]
        }
    )
    recommendations = filter_llmfit_recommendations(
        llmfit_rows, {model.name for model in lock.models}
    )
    (evidence_root / "llmfit-recommendations.json").write_text(
        json.dumps({"models": recommendations}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    synthetic_username = "researcher-private"
    synthetic_hostname = "workstation-private"
    process_secret = "process-secret"
    dotenv_secret = "dotenv-secret"
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(f"TOKEN={dotenv_secret}\n", encoding="utf-8")
    log_path = evidence_root / "benchmark.log"
    log_path.write_text(
        (
            f"username={synthetic_username} hostname={synthetic_hostname}\n"
            f"OPENAI_API_KEY={process_secret} TOKEN={dotenv_secret}\n"
        ),
        encoding="utf-8",
    )

    forbidden_values = collect_forbidden_values(
        {"OPENAI_API_KEY": process_secret},
        dotenv_paths=(dotenv_path,),
        base_values=(synthetic_username, synthetic_hostname),
    )
    expected_forbidden = {
        process_secret,
        dotenv_secret,
        synthetic_username,
        synthetic_hostname,
    }
    assert expected_forbidden <= forbidden_values
    assert scan_sensitive_text(evidence_root, forbidden_values=forbidden_values)
    assert all(
        path.suffix.lower() in {".json", ".jsonl", ".log", ".txt", ".csv", ".md"}
        for path in evidence_root.rglob("*")
        if path.is_file()
    )
    assert not any(evidence_root.rglob("*.ifc"))
    assert not any(evidence_root.rglob("*.ids"))
    assert not any(evidence_root.rglob(".env"))
    assert not any(evidence_root.rglob("*.zip"))

    evidence_zip = create_evidence_zip(
        evidence_root,
        tmp_path / "ifcqc-evidence.zip",
        forbidden_values=forbidden_values,
    )
    first_zip_bytes = evidence_zip.read_bytes()
    repeated_zip = create_evidence_zip(
        evidence_root,
        tmp_path / "ifcqc-evidence-repeat.zip",
        forbidden_values=forbidden_values,
    )

    assert evidence_zip.parent == tmp_path
    assert first_zip_bytes == repeated_zip.read_bytes()
    assert validate_evidence_archive(evidence_zip) == []
    assert validate_evidence_archive(repeated_zip) == []
    assert not scan_sensitive_text(evidence_root, forbidden_values=forbidden_values)
    assert validate_manifest(evidence_root / "manifest.json", evidence_root) == []
    with zipfile.ZipFile(evidence_zip) as archive:
        archived_text = "\n".join(
            archive.read(name).decode("utf-8") for name in archive.namelist()
        ).casefold()
    for forbidden in forbidden_values:
        assert forbidden.casefold() not in archived_text
    get_settings.cache_clear()
