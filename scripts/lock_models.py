"""Congela a matriz de modelos do benchmark em models.lock.json (Fase B.0).

Lê ``ollama list`` (nome, digest curto, tamanho) e ``ollama show`` (arquitetura,
parâmetros, quantização) das tags da matriz e grava
``src/experiment/results/models.lock.json`` — a referência citável de
reprodutibilidade do artigo.

Uso (após os ``ollama pull``):

    python scripts/lock_models.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT = PROJECT_ROOT / "src" / "experiment" / "results" / "models.lock.json"

# Matriz oficial (plano de orquestração §B.0) + teto de qualidade já instalado.
BENCHMARK_MODELS = [
    "qwen2.5:7b-instruct",
    "llama3.1:8b",
    "mistral:7b",
    "gemma2:9b",
    "phi3.5",
    "qwen3:14b",
]


def _ollama_list() -> dict[str, dict]:
    """Indexa a saída de ``ollama list`` por nome de modelo."""
    out = subprocess.run(["ollama", "list"], capture_output=True, text=True, check=True)
    table: dict[str, dict] = {}
    for line in out.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 4:
            table[parts[0]] = {"digest": parts[1], "size": f"{parts[2]} {parts[3]}"}
    return table


def _ollama_show(model: str) -> dict:
    """Extrai arquitetura/parâmetros/quantização de ``ollama show``."""
    out = subprocess.run(["ollama", "show", model], capture_output=True, text=True)
    info: dict = {}
    patterns = {
        "architecture": r"architecture\s+(\S+)",
        "parameters": r"parameters\s+(\S+)",
        "context_length": r"context length\s+(\S+)",
        "quantization": r"quantization\s+(\S+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, out.stdout)
        if match:
            info[key] = match.group(1)
    return info


def _resolve(model: str, installed: dict[str, dict]) -> str | None:
    """Resolve o nome no índice do ollama list (tags sem ':' viram ':latest')."""
    if model in installed:
        return model
    if ":" not in model and f"{model}:latest" in installed:
        return f"{model}:latest"
    return None


def main() -> int:
    """Gera o lock; falha se algum modelo da matriz não estiver instalado."""
    installed = _ollama_list()
    resolved = {m: _resolve(m, installed) for m in BENCHMARK_MODELS}
    missing = [m for m, r in resolved.items() if r is None]
    if missing:
        print(f"ERRO: modelos ausentes (rodar ollama pull): {missing}", file=sys.stderr)
        return 1

    lock = {
        "locked_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": (
            "Matriz de modelos do benchmark (Fase B). Digests fixados para "
            "reprodutibilidade; nao atualizar os modelos durante o experimento."
        ),
        "models": [
            {"name": resolved[model], **installed[resolved[model]], **_ollama_show(resolved[model])}
            for model in BENCHMARK_MODELS
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(lock, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"models.lock.json: {len(lock['models'])} modelos -> {OUTPUT}")
    for entry in lock["models"]:
        print(f"  {entry['name']}: digest={entry['digest']} quant={entry.get('quantization', '?')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
