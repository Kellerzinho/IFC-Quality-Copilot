"""Mede um estrato isolado, barato, para atribuir o efeito de UMA correção.

Rodar o prédio inteiro custa ~48 min por modelo, o que é caro demais para
responder "esta correção específica ajudou?". Com ``--reuse-equivalent``, um
único estrato colapsa em poucos estímulos distintos (``system_unclassified``:
11 para 872 issues), e a medição sai em minutos — com o mesmo ground truth,
o mesmo avaliador e o mesmo export por issue do benchmark completo.

Uso:

    python -u scripts/mede_estrato.py --model gemma2:9b \\
        --issue-types system_unclassified --tag pos-fix-bsdd
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import httpx
from loguru import logger

from src.experiment.per_issue import aggregate_by_stratum
from src.experiment.runner import ExperimentRunner

EVAL = PROJECT_ROOT / "data" / "evaluation" / "predio"
IDS = PROJECT_ROOT / "data" / "ids_templates" / "residencial_nbr15575.ids"
BUILDING = {"building_type": "Residencial multifamiliar", "bioclimatic_zone": "3"}
RESULTS = PROJECT_ROOT / "src" / "experiment" / "results"


def _unload(model: str) -> None:
    """Descarrega o modelo da VRAM antes e depois da medição."""
    try:
        httpx.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": "", "keep_alive": 0},
            timeout=180,
        )
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    """Mede um estrato e imprime o breakdown; grava JSON + JSONL por issue."""
    parser = argparse.ArgumentParser(prog="python scripts/mede_estrato.py")
    parser.add_argument("--model", default="gemma2:9b")
    parser.add_argument(
        "--issue-types",
        default="system_unclassified",
        help="Tipos separados por vírgula (default: system_unclassified).",
    )
    parser.add_argument("--tag", required=True, help="Rótulo do diretório de saída.")
    parser.add_argument(
        "--check-properties",
        default="",
        help="Restringe às propriedades alvo (separadas por vírgula). Vazio = todas.",
    )
    parser.add_argument(
        "--dataset",
        choices=("predio", "masked"),
        default="predio",
        help="predio (ground_truth.yaml) ou masked (ground_truth_spaces.yaml).",
    )
    args = parser.parse_args(argv)

    issue_types = [t.strip() for t in args.issue_types.split(",") if t.strip()]
    check_properties = [p.strip() for p in args.check_properties.split(",") if p.strip()]
    if args.dataset == "masked":
        ifc, gt = EVAL / "predio_v1_masked.ifc", EVAL / "ground_truth_spaces.yaml"
    else:
        ifc, gt = EVAL / "predio_v1.ifc", EVAL / "ground_truth.yaml"

    out_dir = RESULTS / f"estrato-{args.tag}"
    _unload(args.model)
    logger.info(
        "Medindo {} | estratos={} | propriedades={} | modelo={}",
        args.dataset,
        issue_types,
        check_properties or "todas",
        args.model,
    )
    t0 = time.perf_counter()
    result = ExperimentRunner().run_single(
        ifc_path=str(ifc),
        ground_truth_path=str(gt),
        building_context=BUILDING,
        ids_path=str(IDS),
        model_name=args.model,
        cache_enabled=False,
        issue_types=issue_types,
        check_properties=check_properties or None,
        reuse_equivalent=True,
    )
    ExperimentRunner._export(result, str(out_dir))
    _unload(args.model)

    dt = (time.perf_counter() - t0) / 60
    print(f"\n### {args.tag} — {args.model} — {args.dataset} — {dt:.1f} min")
    print(f"  chamadas ao LLM: {result.stability.total_generated} "
          f"(reuso cobriu {result.timing.reused} issues) | falhas: {result.stability.failed_count}")
    print(f"  top-1 global do recorte: {result.evaluation.accuracy_top1:.4f} "
          f"| top-3: {result.evaluation.accuracy_top3:.4f}")
    for row in aggregate_by_stratum(result.outcomes):
        extra = ""
        if "mape" in row:
            extra = f" | MAPE {row['mape']:.1f}% | <=10% {row['dentro_10pct']:.3f}"
        print(
            f"    {row['stratum']:<38} n={row['n']:>5} estim={row['estimulos']:>4} "
            f"top1={row['top1']:.3f} top3={row['top3']:.3f}{extra}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
