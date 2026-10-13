"""Testes da prospecção M7-09: estimativa, parsers e invariantes (sem GPU nem Ollama)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.experiment.budget_v1.prospection import (
    BITS_PER_WEIGHT,
    GIB,
    ArchitectureSpec,
    HardwareProfile,
    OllamaTagInfo,
    SourcedValue,
    build_records,
    classify_fit,
    collect_hardware_profile,
    kv_cache_bytes,
    load_outputs,
    parse_cuda_driver_version,
    parse_nvcc_version,
    parse_nvidia_smi_csv,
    parse_ollama_list,
    parse_ollama_show,
    parse_ollama_version,
    read_ollama_manifests,
    redact_profile,
    render_markdown,
    run_ollama_readonly,
    unconfirmed_profile,
    weights_bytes,
    write_outputs,
)
from src.experiment.budget_v1.prospection_sources import CANDIDATES

NVIDIA_SMI_CSV = """name, memory.total [MiB], driver_version
NVIDIA GeForce RTX 4050 Laptop GPU, 6141 MiB, 572.83
"""
NVIDIA_SMI_BANNER = """Mon Oct 12 23:07:15 2026
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 572.83                 Driver Version: 572.83         CUDA Version: 12.8     |
"""
NVCC = "Cuda compilation tools, release 12.4, V12.4.131\n"
OLLAMA_VERSION_UP = "ollama version is 0.40.3\n"
OLLAMA_VERSION_DOWN = (
    "Warning: could not connect to a running Ollama instance\nWarning: client version is 0.40.3\n"
)
OLLAMA_LIST = """NAME                ID              SIZE      MODIFIED
qwen3:8b-q4_K_M     500a1f067a9f    5.2 GB    2 weeks ago
llama3.2:3b         a80c4f17acd5    2.0 GB    3 days ago
"""
OLLAMA_SHOW = """  Model
    architecture        qwen3
    parameters          8.2B
    context length      40960
    embedding length    4096
    quantization        Q4_K_M

  Capabilities
    completion
    tools

  Parameters
    temperature    0.6
"""


def _spec(**overrides: object) -> ArchitectureSpec:
    def sv(value: object) -> SourcedValue:
        return SourcedValue(value=value, status="fonte_primaria")  # type: ignore[arg-type]

    base: dict[str, object] = {
        "family": "Teste",
        "model": "Teste-8B",
        "params_billion": sv(8.0),
        "kv_layers": sv(32),
        "kv_heads": sv(8),
        "head_dim": sv(128),
        "context_advertised": sv(131072),
        "license": sv("apache-2.0"),
        "ollama_tags": {
            "Q8_0": None,
            "Q5_K_M": None,
            "Q4_K_M": OllamaTagInfo(
                tag="teste:8b-q4_K_M",
                catalog_size_gb=4.9,
                catalog_context="128K",
                source="https://ollama.com/library/teste/tags",
                accessed_on="2026-10-12",
            ),
            "Q3_K_M": None,
        },
    }
    base.update(overrides)
    return ArchitectureSpec.model_validate(base)


def _personal(vram_mib: int = 6141, ram_total: float = 7.71) -> HardwareProfile:
    profile = unconfirmed_profile("pessoal-teste", "fixture")
    return profile.model_copy(
        update={
            "line": "pessoal",
            "status": "observado",
            "gpus": parse_nvidia_smi_csv(
                f"NVIDIA GeForce RTX 4050 Laptop GPU, {vram_mib} MiB, 572.83"
            ),
            "ram_total_gib": SourcedValue(value=ram_total, status="medido"),
            "notes": [],
        }
    )


class FakeRunner:
    """Simula subprocess.run com saídas fixas e registra os comandos recebidos."""

    def __init__(self, outputs: dict[tuple[str, ...], str]) -> None:
        self.outputs = outputs
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], **_: object) -> SimpleNamespace:
        self.calls.append(command)
        key = tuple(command)
        if key not in self.outputs:
            raise FileNotFoundError(command[0])
        return SimpleNamespace(returncode=0, stdout=self.outputs[key], stderr="")


def _machine_outputs(ollama_version: str) -> dict[tuple[str, ...], str]:
    return {
        (
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv",
        ): NVIDIA_SMI_CSV,
        ("nvidia-smi",): NVIDIA_SMI_BANNER,
        ("ollama", "--version"): ollama_version,
        ("ollama", "list"): OLLAMA_LIST,
        ("ollama", "show", "qwen3:8b-q4_K_M"): OLLAMA_SHOW,
        ("ollama", "show", "llama3.2:3b"): OLLAMA_SHOW,
    }


# --------------------------------------------------------------------------
# Estimativa de memória
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("params", "quant", "expected_gib"),
    [
        (8.0, "Q8_0", 8.0e9 * 8.5008 / 8 / GIB),
        (8.0, "Q4_K_M", 8.0e9 * 4.8944 / 8 / GIB),
        (4.0, "Q3_K_M", 4.0e9 * 3.9960 / 8 / GIB),
    ],
)
def test_weights_bytes_uses_params_times_effective_bits_over_eight(
    params: float, quant: str, expected_gib: float
) -> None:
    assert weights_bytes(params, BITS_PER_WEIGHT[quant]) / GIB == pytest.approx(expected_gib)  # type: ignore[index]


def test_weights_bytes_matches_llamacpp_reference_size_for_llama31_8b() -> None:
    # A tabela do llama.cpp dá 4,58 GiB para Llama-3.1-8B em Q4_K_M (8,03B parâmetros).
    assert weights_bytes(8.03, BITS_PER_WEIGHT["Q4_K_M"]) / GIB == pytest.approx(4.58, abs=0.01)


def test_kv_cache_bytes_follows_two_times_layers_heads_dim_context_bytes() -> None:
    # Llama-3.1-8B: 32 camadas, 8 cabeças KV, dimensão 128, f16 → 0,5 GiB em 4k.
    assert kv_cache_bytes(32, 8, 128, 4096) == 2 * 32 * 8 * 128 * 4096 * 2
    assert kv_cache_bytes(32, 8, 128, 4096) / GIB == pytest.approx(0.5)
    assert kv_cache_bytes(32, 8, 128, 8192) == 2 * kv_cache_bytes(32, 8, 128, 4096)


@pytest.mark.parametrize("bad", [0, -1])
def test_memory_inputs_must_be_positive(bad: int) -> None:
    with pytest.raises(ValueError):
        kv_cache_bytes(bad, 8, 128, 4096)
    with pytest.raises(ValueError):
        weights_bytes(bad, 4.8944)


@pytest.mark.parametrize(
    ("required", "expected"),
    [
        (5.0, "gpu_inteira"),  # cabe em 6,0 − 0,7 = 5,3 GiB
        (5.3, "gpu_inteira"),  # exatamente no limite
        (6.0, "offload_parcial"),  # excede a VRAM útil, cabe com 3,7 GiB de RAM
        (9.0, "offload_parcial"),
        (9.1, "inviavel"),
    ],
)
def test_classify_fit_reserves_runtime_slack_from_vram(required: float, expected: str) -> None:
    klass, _ = classify_fit(required, vram_gib=6.0, ram_budget_gib=3.7, runtime_reserve_gib=0.7)
    assert klass == expected


def test_classify_fit_negative_ram_budget_never_enables_offload() -> None:
    klass, _ = classify_fit(5.5, vram_gib=6.0, ram_budget_gib=-1.0)
    assert klass == "inviavel"


def test_record_memory_is_labelled_estimate_with_both_contexts() -> None:
    records = build_records([_spec()], [_personal()])
    q4 = next(r for r in records if r.quantization == "Q4_K_M")
    assert q4.memory.kind == "estimativa"
    assert [c.context_tokens for c in q4.memory.per_context] == [4096, 8192]
    four_k = q4.memory.per_context[0]
    assert four_k.kv_cache_gib == pytest.approx(0.5)
    assert four_k.total_gib == pytest.approx(
        weights_bytes(8.0, 4.8944) / GIB + 0.5 + 0.7, abs=0.001
    )
    assert q4.context.usable.status == "nao_medido"
    assert q4.context.advertised.value == 131072


def test_recurrent_state_is_added_once_independent_of_context() -> None:
    spec = _spec(recurrent_state_gib=SourcedValue(value=0.05, status="derivado"))
    q4 = next(r for r in build_records([spec], [_personal()]) if r.quantization == "Q4_K_M")
    four_k, eight_k = q4.memory.per_context
    assert four_k.recurrent_state_gib == eight_k.recurrent_state_gib == pytest.approx(0.05)
    assert eight_k.total_gib - four_k.total_gib == pytest.approx(
        eight_k.kv_cache_gib - four_k.kv_cache_gib, abs=0.002
    )


def test_unpublished_quantization_keeps_estimate_without_tag_or_catalog_size() -> None:
    q8 = next(r for r in build_records([_spec()], [_personal()]) if r.quantization == "Q8_0")
    assert q8.tag is None
    assert q8.memory.catalog_size_gib is None
    assert all(f.classification_by_catalog_size is None for f in q8.memory.fit)
    assert any("não publicado" in note for note in q8.notes)


def test_catalog_size_can_flip_classification_against_formula() -> None:
    # Pesos pela fórmula cabem; o arquivo publicado (maior) não cabe.
    tag = OllamaTagInfo(
        tag="teste:8b-q4_K_M",
        catalog_size_gb=5.4,
        catalog_context="128K",
        source="https://ollama.com/library/teste/tags",
        accessed_on="2026-10-12",
    )
    spec = _spec(
        params_billion=SourcedValue(value=8.2, status="fonte_primaria"),
        kv_layers=SourcedValue(value=36, status="fonte_primaria"),
        ollama_tags={"Q8_0": None, "Q5_K_M": None, "Q4_K_M": tag, "Q3_K_M": None},
    )
    q4 = next(r for r in build_records([spec], [_personal()]) if r.quantization == "Q4_K_M")
    fit_4k = next(f for f in q4.memory.fit if f.context_tokens == 4096)
    assert fit_4k.classification == "gpu_inteira"
    assert fit_4k.classification_by_catalog_size == "offload_parcial"


# --------------------------------------------------------------------------
# T7-26 — candidato condicionado sem hardware confirmado
# --------------------------------------------------------------------------


def test_t7_26_unconfirmed_lab_profile_never_claims_viability() -> None:
    lab = unconfirmed_profile("ime-se2-lab", "laboratório não confirmado")
    records = build_records(CANDIDATES, [_personal(), lab])
    lab_fits = [f for r in records for f in r.memory.fit if f.hardware_profile_id == lab.profile_id]
    assert lab_fits
    assert {f.classification for f in lab_fits} == {"condicionado_hardware_nao_confirmado"}
    assert all(f.vram_margin_gib is None for f in lab_fits)
    assert all("não confirmado" in f.basis for f in lab_fits)


def test_t7_26_profile_without_gpu_observation_is_conditioned() -> None:
    no_gpu = _personal().model_copy(update={"gpus": []})
    q4 = next(r for r in build_records([_spec()], [no_gpu]) if r.quantization == "Q4_K_M")
    assert {f.classification for f in q4.memory.fit} == {"condicionado_hardware_nao_confirmado"}


def test_installed_tested_selected_are_independent_and_nothing_is_tested() -> None:
    personal = _personal().model_copy(
        update={"ollama_installed": parse_ollama_list(OLLAMA_LIST.replace("qwen3:8b", "teste:8b"))}
    )
    records = build_records([_spec()], [personal])
    q4 = next(r for r in records if r.quantization == "Q4_K_M")
    assert q4.installed is True
    assert q4.digest.status == "medido"
    assert q4.digest.value == "500a1f067a9f"
    assert all(r.tested is False and r.selected is False for r in records)
    assert all(r.decision.status == "pendente" for r in records)
    assert all(r.round_id is None for r in records)
    assert all(r.screening.legacy_runs.status == "pendente_M7-02" for r in records)
    assert not any(r.installed for r in records if r.quantization != "Q4_K_M")


# --------------------------------------------------------------------------
# Parsers
# --------------------------------------------------------------------------


def test_parse_nvidia_smi_csv_skips_header_and_reads_mib() -> None:
    gpus = parse_nvidia_smi_csv(NVIDIA_SMI_CSV)
    assert len(gpus) == 1
    assert gpus[0].name == "NVIDIA GeForce RTX 4050 Laptop GPU"
    assert gpus[0].memory_total_mib == 6141
    assert gpus[0].driver_version == "572.83"


def test_parse_nvidia_smi_csv_handles_multiple_gpus_and_noise() -> None:
    text = "name, memory.total [MiB], driver_version\nA, 8192 MiB, 1\n\nlixo\nB, [N/A], 2\n"
    gpus = parse_nvidia_smi_csv(text)
    assert [g.name for g in gpus] == ["A", "B"]
    assert gpus[1].memory_total_mib is None


@pytest.mark.parametrize("text", ["", "NVIDIA-SMI has failed because it couldn't communicate"])
def test_parse_nvidia_smi_csv_without_gpu_returns_empty(text: str) -> None:
    assert parse_nvidia_smi_csv(text) == []


def test_parse_cuda_versions() -> None:
    assert parse_cuda_driver_version(NVIDIA_SMI_BANNER) == "12.8"
    assert parse_cuda_driver_version("") is None
    assert parse_nvcc_version(NVCC) == "12.4"
    assert parse_nvcc_version("") is None


@pytest.mark.parametrize(
    ("text", "version", "reachable"),
    [
        (OLLAMA_VERSION_UP, "0.40.3", True),
        (OLLAMA_VERSION_DOWN, "0.40.3", False),
        ("", None, False),
    ],
)
def test_parse_ollama_version_detects_server(
    text: str, version: str | None, reachable: bool
) -> None:
    assert parse_ollama_version(text) == (version, reachable)


def test_parse_ollama_list_reads_rows_and_ignores_header() -> None:
    models = parse_ollama_list(OLLAMA_LIST)
    assert [m.name for m in models] == ["qwen3:8b-q4_K_M", "llama3.2:3b"]
    assert models[0].model_id == "500a1f067a9f"
    assert models[0].size == "5.2 GB"


def test_parse_ollama_list_empty_installation() -> None:
    assert parse_ollama_list("NAME    ID    SIZE    MODIFIED \n") == []


def test_parse_ollama_show_reads_only_model_section() -> None:
    details = parse_ollama_show(OLLAMA_SHOW)
    assert details == {
        "architecture": "qwen3",
        "parameters": "8.2B",
        "context length": "40960",
        "embedding length": "4096",
        "quantization": "Q4_K_M",
    }


def test_read_ollama_manifests_lists_tags_and_short_digest(tmp_path: Path) -> None:
    library = tmp_path / "manifests" / "registry.ollama.ai" / "library" / "qwen3"
    library.mkdir(parents=True)
    (library / "8b").write_text('{"schemaVersion":2}', encoding="utf-8")
    other = tmp_path / "manifests" / "hf.co" / "org" / "modelo"
    other.mkdir(parents=True)
    (other / "Q4_K_M").write_text("{}", encoding="utf-8")

    models = read_ollama_manifests(tmp_path)

    assert {m.name for m in models} == {"qwen3:8b", "hf.co/org/modelo:Q4_K_M"}
    assert all(m.model_id and len(m.model_id) == 12 for m in models)
    assert read_ollama_manifests(tmp_path / "inexistente") == []


# --------------------------------------------------------------------------
# Coleta: comandos ausentes, Ollama somente leitura (T7-40, recorte M7-09)
# --------------------------------------------------------------------------


def test_collect_marks_missing_commands_as_unavailable(tmp_path: Path) -> None:
    runner = FakeRunner({})
    profile = collect_hardware_profile(
        runner, project_root=tmp_path, collected_on="2026-10-12", ollama_models_dir=tmp_path
    )
    assert profile.gpus == []
    assert profile.gpu_probe.status == "indisponivel"
    assert profile.cuda_driver_max.status == "indisponivel"
    assert profile.cuda_toolkit.status == "indisponivel"
    assert profile.ollama_version.status == "indisponivel"
    assert profile.ollama_server.status == "indisponivel"
    assert profile.profile_id == "pessoal-sem-gpu-nvidia"


def test_collect_with_server_up_uses_list_and_show(tmp_path: Path) -> None:
    runner = FakeRunner(_machine_outputs(OLLAMA_VERSION_UP))
    profile = collect_hardware_profile(runner, project_root=tmp_path, collected_on="2026-10-12")
    assert profile.gpus[0].memory_total_mib == 6141
    assert profile.cuda_driver_max.value == "12.8"
    assert profile.ollama_server.value == "no_ar"
    assert [m.name for m in profile.ollama_installed] == ["qwen3:8b-q4_K_M", "llama3.2:3b"]
    assert profile.ollama_installed[0].details["quantization"] == "Q4_K_M"


def test_t7_40_collect_never_calls_list_or_show_when_server_is_down(tmp_path: Path) -> None:
    # No Windows, list/show tentam abrir o app do Ollama; a coleta não pode iniciar serviço.
    runner = FakeRunner(_machine_outputs(OLLAMA_VERSION_DOWN))
    manifests = tmp_path / "models" / "manifests" / "registry.ollama.ai" / "library" / "qwen3"
    manifests.mkdir(parents=True)
    (manifests / "8b").write_text("{}", encoding="utf-8")

    profile = collect_hardware_profile(
        runner,
        project_root=tmp_path,
        collected_on="2026-10-12",
        ollama_models_dir=tmp_path / "models",
    )

    ollama_calls = [c for c in runner.calls if c[0] == "ollama"]
    assert ollama_calls == [["ollama", "--version"]]
    assert profile.ollama_server.value == "fora_do_ar"
    assert profile.ollama_installed_source.value == "manifests em disco"
    assert [m.name for m in profile.ollama_installed] == ["qwen3:8b"]


@pytest.mark.parametrize(
    "subcommand", ["run", "pull", "serve", "create", "cp", "rm", "push", "stop", "ps"]
)
def test_t7_40_ollama_runner_refuses_non_metadata_subcommands(subcommand: str) -> None:
    runner = FakeRunner({})
    with pytest.raises(ValueError, match="não autorizado"):
        run_ollama_readonly(runner, [subcommand, "qwen3:8b"])
    assert runner.calls == []


def test_t7_40_collect_uses_only_readonly_ollama_subcommands(tmp_path: Path) -> None:
    runner = FakeRunner(_machine_outputs(OLLAMA_VERSION_UP))
    collect_hardware_profile(runner, project_root=tmp_path, collected_on="2026-10-12")
    used = {c[1] for c in runner.calls if c[0] == "ollama"}
    assert used <= {"--version", "list", "show"}


def test_collect_tolerates_timeouts(tmp_path: Path) -> None:
    def runner(command: list[str], **_: object) -> SimpleNamespace:
        raise subprocess.TimeoutExpired(command, 1)

    profile = collect_hardware_profile(
        runner, project_root=tmp_path, collected_on="2026-10-12", ollama_models_dir=tmp_path
    )
    assert profile.gpu_probe.status == "indisponivel"


# --------------------------------------------------------------------------
# Privacidade e saídas
# --------------------------------------------------------------------------


def test_redact_profile_removes_user_profile_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USERNAME", "fulano")
    profile = _personal().model_copy(
        update={"notes": [r"lido em C:\Users\fulano\.ollama\models por fulano"]}
    )
    dumped = json.dumps(redact_profile(profile).model_dump(mode="json"))
    assert "fulano" not in dumped
    assert "Users" not in dumped


def test_outputs_round_trip_and_markdown_is_generated_from_files(tmp_path: Path) -> None:
    profiles = [_personal(), unconfirmed_profile("ime-se2-lab", "não confirmado")]
    records = build_records(CANDIDATES, profiles)
    write_outputs(tmp_path, profiles, records)

    loaded_profiles, loaded_records = load_outputs(tmp_path)

    assert loaded_records == records
    assert [p.profile_id for p in loaded_profiles] == ["pessoal-teste", "ime-se2-lab"]
    assert len(loaded_records) == len(CANDIDATES) * 4
    assert b"\r\n" not in (tmp_path / "models.jsonl").read_bytes()
    markdown = render_markdown(loaded_profiles, loaded_records)
    assert "ESTIMATIVA" in markdown
    assert markdown.count("| Qwen3.5-9B |") >= 1
    assert "condicionado" in markdown


def test_committed_outputs_are_consistent_with_current_sources() -> None:
    out_dir = Path(__file__).resolve().parents[3] / "research" / "M7" / "prospection"
    profiles, records = load_outputs(out_dir)
    assert records == build_records(CANDIDATES, profiles)
    assert (out_dir / "prospeccao.md").read_text(encoding="utf-8") == render_markdown(
        profiles, records
    )
