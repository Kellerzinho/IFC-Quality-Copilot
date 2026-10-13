"""Testes do inventário e da comparabilidade do legado (M7-02).

Fixtures sintéticas pequenas (runs, sidecar e ZIP montados em ``tmp_path``)
testam parsers, conferência de hashes, flags e classificação. Um único teste
lê o inventário documental versionado para conferir os totais declarados.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from src.experiment.budget_v1.legacy import (
    NAO_REGISTRADO,
    HashCheck,
    LegacyRunRecord,
    apply_run_payload,
    build_inventory,
    build_records,
    check_archives,
    classify,
    csv_consistency,
    dataset_hash_index,
    deduplicate,
    ensure_outside,
    finalize,
    group_rounds,
    installed_only_models,
    load_documental,
    models_with_runs,
    quantization_index,
    reconcile_totals,
    record_from_documental,
    resolve_dataset,
    round_key,
    write_outputs,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]

CASA_IFC = "c" * 64
PREDIO_IFC = "p" * 64
DIGEST = "d" * 64


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run_payload(model: str = "m:7b", accuracy: float = 0.5, **meta: Any) -> dict[str, Any]:
    metadata = {
        "model_name": model,
        "model_digest": DIGEST,
        "ollama_version": "0.32.5",
        "seed": 42,
        "temperature": 0.1,
        "num_ctx": 4096,
        "ifc_sha256": CASA_IFC,
        "ids_sha256": "i" * 64,
        "ground_truth_sha256": "g" * 64,
        "prompt_version": "v7.7",
        "timestamp": "2026-08-13",
        **meta,
    }
    return {
        "metadata": metadata,
        "evaluation": {"accuracy_top1": accuracy, "total_evaluated": 263, "by_profile": {}},
        "review_proxy": {"simulation": True, "acceptance_rate": 0.4},
        "stability": {"failure_rate": 0.0},
        "timing": {"latency_ms_p50": 1000.0},
    }


def _entry(
    artifact: str,
    payload: dict[str, Any],
    *,
    group: str = "estudo-x",
    sidecar: tuple[str, bytes] | None = None,
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    entry: dict[str, Any] = {
        "artifact": artifact,
        "group": group,
        "sha256": _sha(data),
        "bytes": len(data),
        "metadata": payload["metadata"],
        "has_review_proxy": "review_proxy" in payload,
        "evaluation_keys": sorted(payload.get("evaluation", {})),
        "sidecar": None,
        "sidecar_info": None,
    }
    if sidecar is not None:
        path, content = sidecar
        entry["sidecar"] = path
        entry["sidecar_info"] = {
            "sha256": _sha(content),
            "bytes": len(content),
            "records": content.count(b"\n"),
            "all_lines_json_valid": True,
        }
    return entry


@pytest.fixture
def legacy_tree(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    """Pasta legada mínima: um run local com sidecar, um smoke e um ZIP com um run."""
    root = tmp_path / "legado"
    sidecar = b'{"i":1}\n{"i":2}\n'

    local = _run_payload()
    local_path = "src/experiment/results/estudo-x/casa/m_7b/run_0.json"
    local_sidecar = "src/experiment/results/estudo-x/casa/m_7b/run_0_issues.jsonl"
    (root / local_path).parent.mkdir(parents=True)
    (root / local_path).write_bytes(json.dumps(local).encode("utf-8"))
    (root / local_sidecar).write_bytes(sidecar)

    smoke = _run_payload(
        model="phi3.5",
        model_digest=None,
        ifc_sha256=PREDIO_IFC,
        prompt_version="v3",
        timestamp=None,
    )
    smoke_path = "src/experiment/results/2026-07-02-smoke/phi3.5/run_0.json"
    (root / smoke_path).parent.mkdir(parents=True)
    (root / smoke_path).write_bytes(json.dumps(smoke).encode("utf-8"))

    zipped = _run_payload(model="z:9b", dataset_key="predio", ifc_sha256=PREDIO_IFC)
    zip_name = "dist/RESULTADO_X.zip"
    (root / "dist").mkdir()
    with zipfile.ZipFile(root / zip_name, "w") as zf:
        zf.writestr("benchmark/results/predio/z_9b/run_0.json", json.dumps(zipped))
        zf.writestr("benchmark/results/predio/z_9b/run_0_issues.jsonl", sidecar)

    documental = {
        "runs": [
            _entry(local_path, local, sidecar=(local_sidecar, sidecar)),
            _entry(smoke_path, smoke, group="2026-07-02-smoke"),
            _entry(
                f"{zip_name}!/benchmark/results/predio/z_9b/run_0.json",
                zipped,
                group="RESULTADO_X.zip",
                sidecar=(f"{zip_name}!/benchmark/results/predio/z_9b/run_0_issues.jsonl", sidecar),
            ),
        ],
        "archive_groups": [{"archive": zip_name, "sha256": _sha((root / zip_name).read_bytes())}],
        "model_locks": [
            {
                "artifact": "lock.json",
                "data": {"models": [{"name": "m:7b", "digest": DIGEST, "quantization": "Q4_K_M"}]},
            }
        ],
        "model_installation_snapshots": [
            {"snapshot": {"models": [{"name": "m:7b"}, {"name": "so-instalado:1b"}]}}
        ],
    }
    return root, documental


def _by_model(records: list[LegacyRunRecord]) -> dict[str, LegacyRunRecord]:
    return {r.model_tag: r for r in records}


# --- parsers -----------------------------------------------------------------


def test_documental_local_run_keeps_unrecorded_fields_explicit(legacy_tree):
    _, documental = legacy_tree
    entry = documental["runs"][1]  # smoke sem digest nem data
    record = record_from_documental(entry, hash_index={}, quant_index={})
    assert record.artifact_kind == "smoke"
    assert record.model_digest == NAO_REGISTRADO
    assert record.date == NAO_REGISTRADO
    assert record.quantization == NAO_REGISTRADO
    assert record.quantization_lock_by_digest == NAO_REGISTRADO
    assert record.gpu == NAO_REGISTRADO
    assert record.metric_values == NAO_REGISTRADO
    assert record.n_items == NAO_REGISTRADO
    assert record.sidecar_hash.status == "sem_artefato"
    assert record.condition["grounding_bsdd"] == NAO_REGISTRADO


def test_documental_zip_run_reads_dataset_key_and_sidecar(legacy_tree):
    _, documental = legacy_tree
    record = record_from_documental(documental["runs"][2], hash_index={}, quant_index={})
    assert record.dataset == "predio"
    assert record.dataset_source == "dataset_key"
    assert record.sidecar_records == 2
    assert record.sidecar_hash.artifact.endswith("run_0_issues.jsonl")
    assert record.review_type == "review_proxy"


def test_quantization_only_from_lock_with_same_digest(legacy_tree):
    _, documental = legacy_tree
    quant = quantization_index(documental["model_locks"])
    with_digest = record_from_documental(documental["runs"][0], hash_index={}, quant_index=quant)
    without = record_from_documental(documental["runs"][1], hash_index={}, quant_index=quant)
    assert with_digest.quantization == NAO_REGISTRADO  # o run não registra
    assert with_digest.quantization_lock_by_digest == "Q4_K_M"
    assert without.quantization_lock_by_digest == NAO_REGISTRADO


@pytest.mark.parametrize(
    ("artifact", "metadata", "expected"),
    [
        ("a/b/x/m/run_0.json", {"dataset_key": "casa"}, ("casa", "dataset_key")),
        ("r/estudo/predio-masked/m/run_0.json", {}, ("predio-masked", "pasta")),
        (
            "r/2026-07-02-smoke/phi3.5/run_0.json",
            {"ifc_sha256": PREDIO_IFC},
            ("predio", "hash_ifc"),
        ),
        (
            "r/estudo/outro/m/run_0.json",
            {"ifc_sha256": "z" * 64},
            (NAO_REGISTRADO, "nao_registrado"),
        ),
    ],
)
def test_resolve_dataset_uses_only_registered_sources(artifact, metadata, expected):
    assert resolve_dataset(artifact, metadata, {PREDIO_IFC: "predio"}) == expected


def test_dataset_hash_index_drops_ambiguous_hashes():
    runs = [
        {"metadata": {"dataset_key": "casa", "ifc_sha256": CASA_IFC}},
        {"metadata": {"dataset_key": "predio", "ifc_sha256": PREDIO_IFC}},
        {"metadata": {"dataset_key": "outro", "ifc_sha256": PREDIO_IFC}},
    ]
    assert dataset_hash_index(runs) == {CASA_IFC: "casa"}


def test_apply_run_payload_reads_values_without_zero_filling():
    record = LegacyRunRecord(run_id="r", artifact="r", sha256="s", artifact_kind="run", study="e")
    full = apply_run_payload(record, _run_payload())
    assert full.n_items == 263
    assert full.metric_values["evaluation.accuracy_top1"] == 0.5
    assert full.metric_values["review_proxy.acceptance_rate"] == 0.4
    assert "evaluation.by_profile" not in full.metric_values
    empty = apply_run_payload(record, {"metadata": {}})
    assert empty.n_items == NAO_REGISTRADO
    assert empty.metric_values == NAO_REGISTRADO


# --- conferência de hashes ---------------------------------------------------


def test_legacy_folder_mode_confirms_hashes_and_reads_values(legacy_tree):
    root, documental = legacy_tree
    records = _by_model(build_records(documental, root=root, mode="pasta_legada"))
    assert {r.run_hash.status for r in records.values()} == {"confere"}
    assert records["m:7b"].sidecar_hash.status == "confere"
    assert records["z:9b"].sidecar_hash.status == "confere"  # membro de ZIP
    assert records["z:9b"].n_items == 263


def test_legacy_folder_mode_reports_divergent_and_absent(legacy_tree):
    root, documental = legacy_tree
    local = root / documental["runs"][0]["artifact"]
    local.write_bytes(local.read_bytes() + b" ")
    (root / documental["runs"][1]["artifact"]).unlink()
    records = _by_model(build_records(documental, root=root, mode="pasta_legada"))
    assert records["m:7b"].run_hash.status == "divergente"
    assert records["m:7b"].metric_values == NAO_REGISTRADO  # bytes divergentes não são lidos
    assert records["phi3.5"].run_hash.status == "ausente"
    for tag in ("m:7b", "phi3.5"):
        assert records[tag].comparability_class == "comparabilidade_insuficiente"


def test_documental_mode_marks_missing_as_not_verified_and_skips_values(legacy_tree, tmp_path):
    _, documental = legacy_tree
    empty_clone = tmp_path / "clone"
    empty_clone.mkdir()
    records = build_records(documental, root=empty_clone, mode="documental")
    assert {r.run_hash.status for r in records} == {"nao_verificado"}
    assert all(r.metric_values == NAO_REGISTRADO for r in records)
    assert all(r.comparability_class != "comparabilidade_insuficiente" for r in records)


def test_documental_mode_confirms_local_runs_but_keeps_values_unrecorded(legacy_tree):
    root, documental = legacy_tree
    records = _by_model(build_records(documental, root=root, mode="documental"))
    assert records["m:7b"].run_hash.status == "confere"
    assert records["m:7b"].metric_values == NAO_REGISTRADO


def test_zip_member_missing_is_absent_in_legacy_mode(legacy_tree):
    root, documental = legacy_tree
    documental["runs"][2]["artifact"] = "dist/RESULTADO_X.zip!/nao/existe/run_0.json"
    records = _by_model(build_records(documental, root=root, mode="pasta_legada"))
    assert records["z:9b"].run_hash.status == "ausente"


def test_check_archives_reports_each_status(legacy_tree):
    root, documental = legacy_tree
    groups = [
        *documental["archive_groups"],
        {"archive": "dist/RESULTADO_X.zip", "sha256": "0" * 64},
        {"archive": "dist/falta.zip", "sha256": "0" * 64},
    ]
    assert [c.status for c in check_archives(root, groups)] == ["confere", "divergente", "ausente"]


def test_output_inside_legacy_folder_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        ensure_outside(tmp_path / "legado" / "saida", tmp_path / "legado")
    ensure_outside(tmp_path / "saida", tmp_path / "legado")


# --- flags e classificação ---------------------------------------------------


def test_flags_are_independent_of_class(legacy_tree):
    root, documental = legacy_tree
    records = build_records(documental, root=root, mode="pasta_legada")
    assert {r.dataset_contaminado for r in records} == {"sim"}
    assert {r.revisao_simulada for r in records} == {"sim"}
    assert len({r.comparability_class for r in records}) > 1


def test_flags_not_recorded_or_negative():
    base = {"run_id": "r", "artifact": "r", "sha256": "s", "artifact_kind": "run", "study": "e"}
    unknown = finalize([LegacyRunRecord(**base)])[0]
    assert unknown.dataset_contaminado == "nao_registrado"
    assert unknown.revisao_simulada == "nao_registrado"
    clean = finalize([LegacyRunRecord(**base, dataset="projeto-novo", review_type="humana")])[0]
    assert clean.dataset_contaminado == "nao"
    assert clean.revisao_simulada == "nao"


def test_classification_per_rule(legacy_tree):
    root, documental = legacy_tree
    records = _by_model(build_records(documental, root=root, mode="pasta_legada"))
    assert records["m:7b"].comparability_class == "entrada_reavaliavel"
    assert records["phi3.5"].comparability_class == "referencia_historica"
    assert "smoke inicial, não benchmark completo" in records["phi3.5"].comparability_reasons
    assert "digest do modelo não registrado" in records["phi3.5"].comparability_reasons


def test_missing_inputs_make_comparability_insufficient():
    record = LegacyRunRecord(
        run_id="r",
        artifact="r",
        sha256="s",
        artifact_kind="run",
        study="e",
        model_tag="m",
        instrument_version="v7.7",
    )
    klass, reasons = classify(record)
    assert klass == "comparabilidade_insuficiente"
    assert "hash do GT não registrado" in reasons


def test_full_contract_is_the_only_path_to_comparable_measurement():
    fields = {
        "run_id": "r",
        "artifact": "r",
        "sha256": "s",
        "artifact_kind": "run",
        "study": "e",
        "model_tag": "m",
        "model_digest": DIGEST,
        "quantization": "Q4_K_M",
        "instrument_version": "budget_v1",
        "ifc_sha256": "a",
        "ids_sha256": "b",
        "ground_truth_sha256": "c",
        "ollama_version": "0.32.5",
        "gpu": "RTX",
        "split_manifest_sha256": "s1",
        "recipe_sha256": "r1",
        "evidence_exposure_sha256": "e1",
        "comparator_version": "c1",
        "metric_definition_version": "m1",
    }
    assert classify(LegacyRunRecord(**fields))[0] == "medicao_comparavel"
    fields["evidence_exposure_sha256"] = NAO_REGISTRADO
    klass, reasons = classify(LegacyRunRecord(**fields))
    assert klass != "medicao_comparavel"
    assert any("evidência enviada" in r for r in reasons)


def test_each_record_gets_exactly_one_class_with_reasons(legacy_tree):
    root, documental = legacy_tree
    for record in build_records(documental, root=root, mode="pasta_legada"):
        assert record.comparability_class in (
            "referencia_historica",
            "entrada_reavaliavel",
            "medicao_comparavel",
            "comparabilidade_insuficiente",
        )
        assert record.comparability_reasons


# --- T7-02 / T7-29 / T7-30 ----------------------------------------------------


def test_t7_02_repeated_artifact_is_deduplicated_by_hash(legacy_tree):
    _, documental = legacy_tree
    original = record_from_documental(documental["runs"][2], hash_index={}, quant_index={})
    copy = original.model_copy(
        update={"artifact": "dist/copia/RESULTADO_X.zip!/b/run_0.json", "run_id": "copia"}
    )
    records = deduplicate([original, copy])
    copies = [r for r in records if r.copy_of]
    assert len(copies) == 1
    assert copies[0].copy_of == min(original.artifact, copy.artifact)
    assert reconcile_totals(records)["observado"]["runs"] == 1
    assert len(models_with_runs(records)["z:9b"]) == 1


def test_t7_02_installed_model_without_run_is_not_tested(legacy_tree):
    root, documental = legacy_tree
    records = build_records(documental, root=root, mode="documental")
    assert "so-instalado:1b" not in models_with_runs(records)
    assert installed_only_models(records, documental["model_installation_snapshots"]) == [
        "so-instalado:1b"
    ]


@pytest.mark.parametrize(
    "change",
    [
        {"instrument_version": "v7.8"},
        {"ground_truth_sha256": "outro-gt"},
        {"ifc_sha256": "outro-ifc", "dataset": "outro"},
        {"metrics_available": ["evaluation.accuracy_top1", "evaluation.nova_metrica"]},
    ],
)
def test_t7_29_change_in_instrument_or_population_opens_new_round(change):
    base = LegacyRunRecord(
        run_id="r",
        artifact="r",
        sha256="s",
        artifact_kind="run",
        study="e",
        instrument_version="v7.7",
        ground_truth_sha256="gt",
        ifc_sha256="ifc",
        dataset="casa",
        metrics_available=["evaluation.accuracy_top1"],
    )
    replica = base.model_copy(update={"run_id": "r2", "artifact": "r2", "sha256": "s2"})
    changed = base.model_copy(update={"run_id": "r3", "artifact": "r3", "sha256": "s3", **change})
    assert round_key(base) == round_key(replica)
    assert round_key(base) != round_key(changed)
    groups = group_rounds([base, replica, changed])
    assert len(groups) == 2
    for members in groups.values():
        assert len({m.instrument_version for m in members}) == 1
        assert len({m.ground_truth_sha256 for m in members}) == 1


def test_t7_30_negative_and_failed_runs_stay_in_inventory(legacy_tree):
    root, documental = legacy_tree
    negative = _run_payload(model="neg:7b", accuracy=0.0)
    failed = _run_payload(model="falha:7b")
    failed["stability"] = {"failure_rate": 1.0}
    del failed["evaluation"]
    for payload in (negative, failed):
        slug = payload["metadata"]["model_name"].replace(":", "_")
        name = f"src/experiment/results/estudo-x/casa/{slug}/run_0.json"
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(json.dumps(payload).encode("utf-8"))
        documental["runs"].append(_entry(name, payload))
    records = _by_model(build_records(documental, root=root, mode="pasta_legada"))
    assert len(records) == 5
    assert records["neg:7b"].metric_values["evaluation.accuracy_top1"] == 0.0
    assert records["falha:7b"].n_items == NAO_REGISTRADO
    assert records["falha:7b"].metric_values["stability.failure_rate"] == 1.0
    assert records["falha:7b"].comparability_reasons


# --- saídas -------------------------------------------------------------------


def test_inventory_marks_hash_validation_partial_and_writes_lf(legacy_tree, tmp_path):
    root, documental = legacy_tree
    (root / documental["runs"][1]["artifact"]).unlink()
    records = build_records(documental, root=root, mode="documental")
    inventory = build_inventory(
        documental, records, mode="documental", generated_at="2026-10-13T00:00:00+00:00", sources={}
    )
    check = inventory["checklist"]["validar_artefatos_hashes"]
    assert check["status"] == "PARCIAL"
    assert check["runs"]["confere"] == 2
    assert check["runs"]["nao_verificado"] == 1
    out = tmp_path / "saida"
    write_outputs(out, inventory)
    assert b"\r\n" not in (out / "inventory.json").read_bytes()
    csv_bytes = (out / "comparability.csv").read_bytes()
    assert b"\r\n" not in csv_bytes
    assert csv_bytes.count(b"\n") == 4  # cabeçalho + 3 runs


def test_inventory_complete_when_every_artifact_confirms(legacy_tree):
    root, documental = legacy_tree
    records = build_records(documental, root=root, mode="pasta_legada")
    inventory = build_inventory(
        documental,
        records,
        mode="pasta_legada",
        generated_at="x",
        sources={},
        archive_checks=check_archives(root, documental["archive_groups"]),
    )
    assert inventory["checklist"]["validar_artefatos_hashes"]["status"] == "COMPLETO"


def test_csv_consistency_flags_divergence(legacy_tree):
    _, documental = legacy_tree
    first = documental["runs"][0]
    csv_text = f"artifact,sha256\n{first['artifact']},{'0' * 64}\nso/no/csv.json,abc\n"
    check = csv_consistency(documental, csv_text)
    assert check["hash_divergente"] == [first["artifact"]]
    assert check["so_no_csv"] == ["so/no/csv.json"]
    assert len(check["so_no_json"]) == 2


def test_reconcile_totals_reports_difference_without_forcing():
    records = [
        LegacyRunRecord(
            run_id="r",
            artifact="r",
            sha256="s",
            artifact_kind="run",
            study="e",
            model_tag="m",
            instrument_version="v7.8",
        )
    ]
    totals = reconcile_totals(records)
    assert totals["confere"] is False
    assert totals["diferenca"] == {"runs": -274, "modelos": -20, "runs_v7.8": 1}


def test_hash_check_default_is_not_verified():
    assert HashCheck().status == "nao_verificado"


# --- inventário documental versionado -----------------------------------------


def test_documental_inventory_matches_declared_totals():
    documental = load_documental(PROJECT_ROOT)
    records = build_records(documental, root=PROJECT_ROOT, mode="documental")
    totals = reconcile_totals(records)
    assert totals["confere"], totals
    assert {r.revisao_simulada for r in records} == {"sim"}
    assert {r.dataset_contaminado for r in records} == {"sim"}
    assert not [r for r in records if r.comparability_class == "medicao_comparavel"]
