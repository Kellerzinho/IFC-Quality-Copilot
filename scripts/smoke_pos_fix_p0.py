"""Smoke pós-fix P0 (prompt v5): masked (sentinela da regressão) + predio.

Valida as correções de roteamento de prompt de 2026-07-27 contra os dois
cenários que o benchmark expôs:

- **masked / space_unnamed** (82 issues, reuso como no benchmark): era 0-5% de
  top-1 com falhas ``empty`` em série; em 02/07, com os templates ricos, dava
  34-56%. É o sinal decisivo do fix.
- **predio / amostra estratificada n=60** (sem reuso, como o smoke padrão):
  compara com a matriz de 26-27/07 (todos ~0,333 de top-1 no n=33 com GT).

Uso (idealmente via Start-Process com log redirecionado):

    python -u scripts/smoke_pos_fix_p0.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import httpx
from loguru import logger

from src.experiment.runner import ExperimentRunner

EVAL = PROJECT_ROOT / "data" / "evaluation" / "predio"
IDS = PROJECT_ROOT / "data" / "ids_templates" / "residencial_nbr15575.ids"
BUILDING = {"building_type": "Residencial multifamiliar", "bioclimatic_zone": "3"}
OUT_JSON = PROJECT_ROOT / "src" / "experiment" / "results" / "smoke_pos_fix_p0.json"
DONE_MARKER = OUT_JSON.with_suffix(".done")

STAGES: list[dict] = [
    # (sentinela) masked: nomeação de espaços, mesma configuração do benchmark
    {
        "dataset": "masked",
        "ifc": EVAL / "predio_v1_masked.ifc",
        "gt": EVAL / "ground_truth_spaces.yaml",
        "issue_types": ["space_unnamed"],
        "max_issues": None,
        "reuse": True,
        "models": ["gemma2:9b", "qwen3.5:9b"],
    },
    # predio: amostra estratificada n=60, sem reuso (comparável ao smoke padrão)
    {
        "dataset": "predio",
        "ifc": EVAL / "predio_v1.ifc",
        "gt": EVAL / "ground_truth.yaml",
        "issue_types": None,
        "max_issues": 60,
        "reuse": False,
        "models": ["gemma2:9b", "qwen2.5:7b-instruct", "qwen3.5:9b"],
    },
]


def _unload(model: str) -> None:
    """Descarrega o modelo da VRAM (8 GB não comportam dois residentes)."""
    try:
        httpx.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": "", "keep_alive": 0},
            timeout=180,
        )
    except Exception:
        pass


def main() -> int:
    """Roda os estágios do smoke e grava JSON + marcador de conclusão."""
    DONE_MARKER.unlink(missing_ok=True)
    runner = ExperimentRunner()
    rows: list[dict] = []
    t_all = time.perf_counter()

    for stage in STAGES:
        for model in stage["models"]:
            _unload(model)
            label = f"{stage['dataset']}/{model}"
            logger.info("SMOKE START: {}", label)
            t0 = time.perf_counter()
            try:
                res = runner.run_single(
                    ifc_path=str(stage["ifc"]),
                    ground_truth_path=str(stage["gt"]),
                    building_context=BUILDING,
                    ids_path=str(IDS),
                    model_name=model,
                    cache_enabled=False,
                    max_issues=stage["max_issues"],
                    sample_seed=42,
                    issue_types=stage["issue_types"],
                    reuse_equivalent=stage["reuse"],
                )
            except Exception as exc:
                logger.exception("SMOKE FAIL: {} ({})", label, exc)
                rows.append({"stage": label, "error": f"{type(exc).__name__}: {exc}"})
                _unload(model)
                continue
            dt = time.perf_counter() - t0
            ev, st, rp = res.evaluation, res.stability, res.review_proxy
            rows.append(
                {
                    "stage": label,
                    "top1": ev.accuracy_top1,
                    "top3": ev.accuracy_top3,
                    "n_eval": ev.total_evaluated,
                    "gerados": st.total_generated,
                    "falhas": st.failed_count,
                    "falhas_por_motivo": st.failure_reasons,
                    "accepted": rp.accepted,
                    "edited": rp.edited,
                    "review": rp.review,
                    "minutos": round(dt / 60, 1),
                    "prompt_version": res.metadata.prompt_version,
                }
            )
            logger.info(
                "SMOKE OK: {} em {:.0f} min | top1={} top3={} | falhas={} | acc/edit/rev={}/{}/{}",
                label,
                dt / 60,
                ev.accuracy_top1,
                ev.accuracy_top3,
                st.failed_count,
                rp.accepted,
                rp.edited,
                rp.review,
            )
            _unload(model)

    OUT_JSON.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    total_min = (time.perf_counter() - t_all) / 60
    logger.info("SMOKE CONCLUIDO em {:.0f} min → {}", total_min, OUT_JSON)
    DONE_MARKER.write_text("done", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
