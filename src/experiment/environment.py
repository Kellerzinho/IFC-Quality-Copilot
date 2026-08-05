"""Identidade do modelo e do hardware que executaram um run (P0 de escala).

Sem estes dois registros, dois resultados do mesmo benchmark são
indistinguíveis quando algo fora do código muda:

- **digest do modelo**: o ``models.lock.json`` diz qual modelo *deveria* rodar,
  mas nada provava qual rodou. Um ``ollama pull`` no meio do experimento troca o
  binário em silêncio, e tags móveis (``:latest``) tornam isso provável.
- **hardware**: enquanto houve uma máquina só, ela era implícita. Com duas, os
  JSONs ficam indistinguíveis e a comparação entre máquinas não é reconstruível
  a posteriori.

Tudo aqui é *best-effort*: nenhuma coleta pode derrubar um estágio de horas, e
campo ausente vale ``None`` (o run continua válido, só menos descritível).
"""

from __future__ import annotations

import platform
import re
import subprocess
from typing import Any

import httpx
from loguru import logger

_TIMEOUT = 10.0


def _normalize_tag(name: str) -> str:
    """Normaliza a tag do Ollama: ``modelo`` e ``modelo:latest`` são o mesmo."""
    return name if ":" in name else f"{name}:latest"


def ollama_model_digest(model: str, base_url: str) -> str | None:
    """Digest real do modelo carregado pelo Ollama, ou None se indisponível.

    É o digest do run, não o do lock: comparar os dois é o que detecta um
    ``ollama pull`` no meio do experimento.
    """
    alvo = _normalize_tag(model)
    try:
        resp = httpx.get(f"{base_url}/api/tags", timeout=_TIMEOUT)
        resp.raise_for_status()
        for entry in resp.json().get("models", []):
            if _normalize_tag(str(entry.get("name", ""))) == alvo:
                return entry.get("digest") or None
    except Exception as exc:
        logger.warning("Digest de {} indisponivel: {}", model, exc)
    return None


def gpu_residency(model: str, base_url: str) -> dict[str, Any] | None:
    """Quanto do modelo está na GPU **agora**, via ``/api/ps``.

    Esta é a variável que decide o desempenho na classe de máquina do
    experimento: quando o modelo não cabe, o Ollama move camadas para a CPU e a
    latência muda por ordens de grandeza (ver ``OllamaClient._fit_num_ctx``).
    Sem registrá-la, latência entre máquinas diferentes mistura "modelo mais
    lento" com "modelo transbordando" — que é justamente o que um estudo
    multi-hardware precisa separar.

    Deve ser chamada com o modelo ainda residente (logo após a geração).
    """
    alvo = _normalize_tag(model)
    try:
        resp = httpx.get(f"{base_url}/api/ps", timeout=_TIMEOUT)
        resp.raise_for_status()
        for entry in resp.json().get("models", []):
            if _normalize_tag(str(entry.get("name", ""))) != alvo:
                continue
            size = entry.get("size")
            size_vram = entry.get("size_vram")
            fracao = (
                (size_vram / size) if isinstance(size, int) and isinstance(size_vram, int) and size
                else None
            )
            return {
                "size_bytes": size,
                "size_vram_bytes": size_vram,
                "gpu_fraction": round(fracao, 4) if fracao is not None else None,
                "context_length": entry.get("context_length"),
            }
        logger.debug("Modelo {} nao esta residente em /api/ps", model)
    except Exception as exc:
        logger.warning("Residencia de GPU de {} indisponivel: {}", model, exc)
    return None


def _nvidia_smi() -> list[dict[str, str]]:
    """Lê nome, VRAM e driver de cada GPU via nvidia-smi; lista vazia se não houver."""
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            check=False,
        )
        gpus: list[dict[str, str]] = []
        for line in (out.stdout or "").strip().splitlines():
            partes = [p.strip() for p in line.split(",")]
            if len(partes) == 3:
                gpus.append({"name": partes[0], "memory_total": partes[1], "driver": partes[2]})
        return gpus
    except Exception as exc:
        logger.debug("nvidia-smi indisponivel: {}", exc)
        return []


def _ram_total_gb() -> float | None:
    """RAM total em GB, ou None se não der para medir."""
    try:
        # psutil nao e dependencia declarada: import local e best-effort de proposito.
        import psutil  # type: ignore[import-untyped]

        return round(psutil.virtual_memory().total / 1024**3, 1)
    except Exception:
        return None


def hardware_snapshot() -> dict[str, Any]:
    """Retrato da máquina que está executando a fila.

    Coletado uma vez por estágio; os campos que faltarem ficam ``None`` em vez
    de derrubar o run.
    """
    gpus = _nvidia_smi()
    return {
        "gpus": gpus,
        "gpu_count": len(gpus),
        "cpu": platform.processor() or None,
        "cpu_count": _cpu_count(),
        "ram_total_gb": _ram_total_gb(),
        "os": f"{platform.system()} {platform.release()}",
        "hostname": platform.node() or None,
        "python": platform.python_version(),
    }


def _cpu_count() -> int | None:
    """Número de CPUs lógicas, ou None."""
    try:
        return __import__("os").cpu_count()
    except Exception:
        return None


def lock_digest_mismatch(model: str, run_digest: str | None, lock_digest: str | None) -> str | None:
    """Compara o digest do run com o do lock; retorna a mensagem se divergirem.

    O lock guarda digest **curto** e o ``/api/tags`` devolve o completo, então a
    comparação é por prefixo. Ausência de qualquer um dos dois não é divergência
    — é simplesmente falta de informação para comparar.
    """
    if not run_digest or not lock_digest:
        return None
    if run_digest.startswith(lock_digest) or lock_digest.startswith(run_digest):
        return None
    return (
        f"{model}: digest do run ({run_digest[:12]}) diverge do models.lock.json "
        f"({lock_digest[:12]}) — o modelo mudou desde o lock"
    )


def parse_nvidia_smi_line(line: str) -> dict[str, str] | None:
    """Auxiliar testável: converte uma linha CSV do nvidia-smi em dict."""
    partes = [p.strip() for p in line.split(",")]
    if len(partes) != 3:
        return None
    return {"name": partes[0], "memory_total": partes[1], "driver": partes[2]}


_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+)")


def parse_version(text: str) -> str | None:
    """Extrai ``X.Y.Z`` de um texto de versão, ou None."""
    match = _VERSION_RE.search(text or "")
    return match.group(1) if match else None
