"""Mini-benchmark de QUALIDADE dos candidatos contra o ground truth do projeto.

Velocidade e encaixe na VRAM se medem direto; "mais inteligente" so se responde
com a tarefa real. Usa o runner do experimento com amostra estratificada pequena,
para comparar top-1/top-3 entre modelos em minutos em vez de horas.
"""

import json
import sys
import time
from pathlib import Path

import httpx

from src.experiment.runner import ExperimentRunner

PROJECT = Path(__file__).resolve()
EVAL = Path("data/evaluation/predio")
IDS = Path("data/ids_templates/residencial_nbr15575.ids")
BUILDING = {
    "building_type": "Residencial multifamiliar",
    "bioclimatic_zone": "3",
    "city": "Rio de Janeiro",
    "state": "RJ",
}
N_ISSUES = int(sys.argv[1]) if len(sys.argv) > 1 else 60
MODELOS = sys.argv[2:] or ["qwen3.5:9b", "gemma2:9b", "qwen2.5:7b-instruct"]


def unload(model: str) -> None:
    try:
        httpx.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": "", "keep_alive": 0},
            timeout=180,
        )
    except Exception:
        pass


def main() -> int:
    runner = ExperimentRunner()
    linhas = []
    print(f"amostra estratificada: {N_ISSUES} issues | dataset: predio_v1")
    print("=" * 96)
    print(f"{'modelo':30} {'top1':>7} {'top3':>7} {'F1':>7} {'min':>7} {'s/sug':>7} {'falhas':>7}")
    print("-" * 96)
    for model in MODELOS:
        unload(model)
        t0 = time.perf_counter()
        try:
            res = runner.run_single(
                ifc_path=str(EVAL / "predio_v1.ifc"),
                ground_truth_path=str(EVAL / "ground_truth.yaml"),
                building_context=BUILDING,
                ids_path=str(IDS),
                model_name=model,
                cache_enabled=False,
                max_issues=N_ISSUES,
                sample_seed=42,
            )
        except Exception as exc:
            print(f"{model:30} ERRO: {type(exc).__name__}: {str(exc)[:44]}")
            unload(model)
            continue
        dt = time.perf_counter() - t0
        ev, st, tm = res.evaluation, res.stability, res.timing
        n = tm.samples or 1
        linhas.append(
            {
                "model": model,
                "top1": ev.accuracy_top1,
                "top3": ev.accuracy_top3,
                "f1": ev.f1,
                "min": dt / 60,
                "s_por_sug": dt / n,
                "falhas": st.failed_count,
                "avaliadas": ev.total_evaluated,
            }
        )
        print(
            f"{model:30} {ev.accuracy_top1:7.4f} {ev.accuracy_top3:7.4f} {ev.f1:7.4f} "
            f"{dt/60:7.1f} {dt/n:7.2f} {st.failed_count:7}"
        )
        unload(model)

    print("-" * 96)
    if linhas:
        melhor_q = max(linhas, key=lambda r: r["top1"])
        melhor_v = min(linhas, key=lambda r: r["s_por_sug"])
        print(f"melhor qualidade : {melhor_q['model']} (top1={melhor_q['top1']:.4f})")
        print(f"melhor velocidade: {melhor_v['model']} ({melhor_v['s_por_sug']:.2f} s/sugestao)")
        print(f"issues avaliadas contra GT: {linhas[0]['avaliadas']}")
        out = Path("src/experiment/results/smoke_qualidade.json")
        out.write_text(json.dumps(linhas, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
