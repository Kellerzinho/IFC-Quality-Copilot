"""Regenera models.lock.json a partir do estado real do Ollama local.

Uso: python atualiza_lock.py <modelo> [modelo...]
A ordem dos argumentos vira a ordem oficial da fila do benchmark.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import httpx

BASE = "http://localhost:11434"
LOCK = Path("src/experiment/results/models.lock.json")


def humaniza(nbytes: int) -> str:
    return f"{nbytes / 1e9:.1f} GB"


def main() -> int:
    modelos = sys.argv[1:]
    if not modelos:
        print("uso: atualiza_lock.py <modelo> [modelo...]")
        return 1

    tags = {m["name"]: m for m in httpx.get(f"{BASE}/api/tags", timeout=10).json()["models"]}
    entradas = []
    for nome in modelos:
        # aceita nome sem :latest
        tag = tags.get(nome) or tags.get(f"{nome}:latest")
        if not tag:
            print(f"ERRO: {nome} nao esta instalado no Ollama")
            return 1
        show = httpx.post(f"{BASE}/api/show", json={"model": nome}, timeout=30).json()
        det, info = show.get("details", {}), show.get("model_info", {})
        arch = info.get("general.architecture", det.get("family", "?"))
        entradas.append(
            {
                "name": tag["name"],
                "digest": tag["digest"][:12],
                "size": humaniza(tag["size"]),
                "architecture": arch,
                "parameters": det.get("parameter_size", "?"),
                "context_length": str(info.get(f"{arch}.context_length", "?")),
                "quantization": det.get("quantization_level", "?"),
            }
        )
        print(f"  {tag['name']:28} {entradas[-1]['digest']}  {entradas[-1]['size']:>8}  "
              f"{arch:10} {entradas[-1]['parameters']:>6} {entradas[-1]['quantization']}")

    doc = {
        "locked_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": (
            "Matriz de modelos do benchmark (Fase B). Digests fixados para "
            "reprodutibilidade; nao atualizar os modelos durante o experimento. "
            "Selecao 2026-07-26: 10 melhores entre 17 candidatos medidos "
            "(fit VRAM ctx2048 + JSON + smoke estratificado n=60/33GT)."
        ),
        "models": entradas,
    }
    LOCK.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nlock atualizado: {LOCK} ({len(entradas)} modelos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
