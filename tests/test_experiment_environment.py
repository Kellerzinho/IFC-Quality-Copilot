"""Testes da identidade de modelo e hardware gravada em cada run (P0 de escala)."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.experiment.environment import (
    _normalize_tag,
    gpu_residency,
    hardware_snapshot,
    lock_digest_mismatch,
    ollama_model_digest,
    parse_nvidia_smi_line,
    parse_version,
)

BASE = "http://localhost:11434"


def _resp(body: dict) -> MagicMock:
    """Mock de httpx.Response com JSON já resolvido."""
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = body
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# digest do modelo
# ---------------------------------------------------------------------------


def test_digest_encontra_o_modelo_por_tag_exata():
    body = {"models": [{"name": "gemma2:9b", "digest": "ff02c3702f32aaaa"}]}
    with patch("httpx.get", return_value=_resp(body)):
        assert ollama_model_digest("gemma2:9b", BASE) == "ff02c3702f32aaaa"


def test_digest_normaliza_latest():
    """``phi4-mini`` e ``phi4-mini:latest`` sao a mesma tag."""
    body = {"models": [{"name": "phi4-mini:latest", "digest": "78fad5d182a7"}]}
    with patch("httpx.get", return_value=_resp(body)):
        assert ollama_model_digest("phi4-mini", BASE) == "78fad5d182a7"


def test_digest_none_quando_modelo_ausente():
    with patch("httpx.get", return_value=_resp({"models": []})):
        assert ollama_model_digest("inexistente:7b", BASE) is None


def test_digest_none_quando_ollama_cai():
    """Coleta de metadado nunca derruba um estagio de horas."""
    with patch("httpx.get", side_effect=httpx.ConnectError("recusado")):
        assert ollama_model_digest("gemma2:9b", BASE) is None


# ---------------------------------------------------------------------------
# divergencia vs models.lock.json
# ---------------------------------------------------------------------------


def test_lock_sem_divergencia_quando_prefixo_casa():
    """O lock guarda digest curto; /api/tags devolve o completo."""
    assert lock_digest_mismatch("gemma2:9b", "ff02c3702f322b9e075e", "ff02c3702f32") is None


def test_lock_detecta_pull_no_meio_do_experimento():
    aviso = lock_digest_mismatch("gemma2:9b", "aaaabbbbcccc1111", "ff02c3702f32")
    assert aviso is not None
    assert "diverge" in aviso


@pytest.mark.parametrize(
    ("run", "lock"),
    [(None, "ff02c3702f32"), ("ff02c3702f32", None), (None, None)],
)
def test_lock_ausencia_de_dado_nao_e_divergencia(run, lock):
    assert lock_digest_mismatch("gemma2:9b", run, lock) is None


# ---------------------------------------------------------------------------
# residencia na GPU
# ---------------------------------------------------------------------------


def test_residencia_calcula_fracao_na_gpu():
    body = {
        "models": [
            {"name": "gemma2:9b", "size": 1000, "size_vram": 720, "context_length": 2048}
        ]
    }
    with patch("httpx.get", return_value=_resp(body)):
        r = gpu_residency("gemma2:9b", BASE)
    assert r["gpu_fraction"] == 0.72
    assert r["size_vram_bytes"] == 720
    assert r["context_length"] == 2048


def test_residencia_fracao_none_sem_tamanhos():
    """Sem size/size_vram nao ha fracao — o campo fica None, nao 0.0."""
    body = {"models": [{"name": "gemma2:9b"}]}
    with patch("httpx.get", return_value=_resp(body)):
        assert gpu_residency("gemma2:9b", BASE)["gpu_fraction"] is None


def test_residencia_none_quando_modelo_ja_descarregado():
    with patch("httpx.get", return_value=_resp({"models": []})):
        assert gpu_residency("gemma2:9b", BASE) is None


# ---------------------------------------------------------------------------
# hardware
# ---------------------------------------------------------------------------


def test_hardware_snapshot_tem_as_chaves_do_contrato():
    snap = hardware_snapshot()
    for chave in ("gpus", "gpu_count", "cpu", "cpu_count", "ram_total_gb", "os"):
        assert chave in snap


def test_hardware_snapshot_omite_identificadores_pessoais():
    snapshot = hardware_snapshot()
    assert "hostname" not in snapshot
    assert "username" not in snapshot
    assert "serial" not in snapshot


def test_hardware_snapshot_sobrevive_sem_nvidia_smi():
    with patch("src.experiment.environment.subprocess.run", side_effect=FileNotFoundError):
        snap = hardware_snapshot()
    assert snap["gpus"] == []
    assert snap["gpu_count"] == 0
    assert snap["os"]


def test_parse_nvidia_smi_line():
    linha = "NVIDIA GeForce RTX 4060 Laptop GPU, 8188 MiB, 591.74"
    assert parse_nvidia_smi_line(linha) == {
        "name": "NVIDIA GeForce RTX 4060 Laptop GPU",
        "memory_total": "8188 MiB",
        "driver": "591.74",
    }


def test_parse_nvidia_smi_line_invalida():
    assert parse_nvidia_smi_line("lixo") is None


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [("ollama version is 0.32.5", "0.32.5"), ("sem versao", None)],
)
def test_parse_version(texto, esperado):
    assert parse_version(texto) == esperado


def test_normalize_tag():
    assert _normalize_tag("gemma2") == "gemma2:latest"
    assert _normalize_tag("gemma2:9b") == "gemma2:9b"
