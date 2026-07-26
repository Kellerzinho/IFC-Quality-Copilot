"""Orquestrador do benchmark completo (Fase B) — fila retomável por estágios.

Executa a matriz oficial (``models.lock.json``) sobre os dois datasets
congelados do prédio, em ordem **réplica-major**: a réplica 0 de todos os
modelos conclui antes da réplica 1 começar — sob interrupção, é melhor ter
1 réplica de tudo do que 3 réplicas de dois modelos.

Propriedades operacionais:

- **Retomável**: um estágio (dataset × modelo × réplica) cujo JSON de saída já
  existe é pulado — relançar o script continua de onde parou.
- **Parada graciosa**: criar o arquivo ``BENCHMARK_STOP`` na raiz do projeto
  encerra a fila no fim do estágio corrente (sem corromper nada).
- **Gate do 14B**: antes do primeiro estágio do ``qwen3:14b``, uma sondagem
  mínima verifica se o modelo responde (na RTX 4060 8GB ele exige RAM livre);
  se falhar, os estágios do 14B são pulados e registrados — a fila continua.
- **Instância única**: um pidfile (``BENCHMARK_RUNNING``) impede fila dupla.
- Dataset mascarado roda com ``issue_types=["space_unnamed"]`` (82 issues),
  evitando regerar as ~2790 issues já cobertas pelo dataset principal.

Uso (idealmente via ``Start-Process`` com log redirecionado):

    python scripts/run_benchmark.py [--replicas 3] [--only-model TAG]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger

from src.experiment.runner import ExperimentRunner, _sanitize
from src.suggestion_engine.ollama_client import OllamaClient

STOP_FILE = PROJECT_ROOT / "BENCHMARK_STOP"
PID_FILE = PROJECT_ROOT / "BENCHMARK_RUNNING"
LOCK_FILE = PROJECT_ROOT / "src" / "experiment" / "results" / "models.lock.json"

BUILDING_CONTEXT = {"building_type": "Residencial multifamiliar", "bioclimatic_zone": "3"}
IDS_PATH = PROJECT_ROOT / "data" / "ids_templates" / "residencial_nbr15575.ids"
EVAL_DIR = PROJECT_ROOT / "data" / "evaluation" / "predio"

# Modelo cuja viabilidade depende de RAM livre (offload) — protegido por gate.
GATED_MODELS = {"qwen3:14b"}

DATASETS: list[dict] = [
    {
        "key": "predio",
        "ifc": EVAL_DIR / "predio_v1.ifc",
        "gt": EVAL_DIR / "ground_truth.yaml",
        "issue_types": None,  # tarefas: preenchimento de Pset + classificação
    },
    {
        "key": "predio-masked",
        "ifc": EVAL_DIR / "predio_v1_masked.ifc",
        "gt": EVAL_DIR / "ground_truth_spaces.yaml",
        "issue_types": ["space_unnamed"],  # tarefa: nomeação de espaços
    },
]


def _locked_models() -> list[str]:
    """Lê a ordem oficial dos modelos do models.lock.json."""
    lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    return [m["name"] for m in lock["models"]]


def _probe_model(model: str) -> bool:
    """Sondagem mínima: o modelo carrega e responde? (gate do 14B)."""
    logger.info("Gate: sondando {} (pode levar minutos no primeiro load)…", model)
    try:
        client = OllamaClient(model=model)
        text, _ = client.generate(prompt="Responda apenas: ok", system=None)
        ok = bool(str(text).strip())
        logger.info("Gate: {} respondeu ({} chars) → {}", model, len(str(text)), ok)
        return ok
    except Exception as exc:
        logger.error("Gate: {} indisponível ({}). Estágios serão pulados.", model, exc)
        return False


def _stage_done(output_root: Path, model: str, replica: int) -> bool:
    """True se o JSON deste estágio já existe (retomada)."""
    return (output_root / _sanitize(model) / f"run_{replica}.json").is_file()


def _unload_model(model: str) -> None:
    """Descarrega o modelo da VRAM antes de trocar de estágio.

    A GPU do experimento tem 8 GB e os modelos da matriz ocupam 4–6 GB cada.
    Com ``keep_alive`` de 15 min, o modelo anterior continua residente quando o
    proximo carrega: os dois nao cabem juntos e o entrante sofre offload parcial
    para a CPU, que e ordens de magnitude mais lento. Descarregar e barato — o
    proximo estagio dura horas.
    """
    import httpx

    from src.config import get_settings

    try:
        httpx.post(
            f"{get_settings().ollama_url}/api/generate",
            json={"model": model, "prompt": "", "keep_alive": 0},
            timeout=60,
        )
        logger.info("Modelo {} descarregado da VRAM", model)
    except Exception as exc:
        logger.warning("Falha ao descarregar {} (segue adiante): {}", model, exc)


def main(argv: list[str] | None = None) -> int:
    """Roda a fila completa do benchmark; retorna 1 se algum estágio falhou."""
    parser = argparse.ArgumentParser(prog="python scripts/run_benchmark.py")
    parser.add_argument("--replicas", type=int, default=1, help="Réplicas por estágio (default 1)")
    parser.add_argument("--only-model", default=None, help="Restringe a fila a um único modelo")
    parser.add_argument(
        "--results-root",
        default=None,
        help="Raiz dos resultados (default: src/experiment/results/<data>-benchmark)",
    )
    parser.add_argument(
        "--reuse-equivalent",
        action="store_true",
        help=(
            "Issues estruturalmente equivalentes reaproveitam a sugestão da primária "
            "em vez de repetir a chamada ao LLM (no modelo do experimento, 4720 issues "
            "correspondem a 1069 estímulos distintos: ~77%% menos chamadas). Fica "
            "registrado em reuse_equivalent no metadata do run."
        ),
    )
    args = parser.parse_args(argv)

    # Instância única
    if PID_FILE.exists():
        logger.error("Fila já em execução? Remova {} se for engano.", PID_FILE)
        return 1
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")

    launch_stamp = datetime.now().strftime("%Y-%m-%d")
    results_root = Path(
        args.results_root
        or PROJECT_ROOT / "src" / "experiment" / "results" / f"{launch_stamp}-benchmark"
    )

    models = _locked_models()
    if args.only_model:
        models = [m for m in models if m == args.only_model]
        if not models:
            logger.error("Modelo {} não está no lock.", args.only_model)
            PID_FILE.unlink(missing_ok=True)
            return 1

    runner = ExperimentRunner()
    gate_results: dict[str, bool] = {}
    failures: list[str] = []
    completed = 0
    skipped = 0
    t_queue = time.perf_counter()

    try:
        logger.info(
            "Fila do benchmark: {} modelos × {} datasets × {} réplicas → {}",
            len(models),
            len(DATASETS),
            args.replicas,
            results_root,
        )
        modelo_residente: str | None = None
        for replica in range(args.replicas):
            for model in models:
                if modelo_residente is not None and modelo_residente != model:
                    _unload_model(modelo_residente)
                modelo_residente = model
                for dataset in DATASETS:
                    stage = f"{dataset['key']}/{model}/run_{replica}"
                    if STOP_FILE.exists():
                        logger.warning(
                            "BENCHMARK_STOP detectado — encerrando após {} estágios.", completed
                        )
                        return 0

                    output_root = results_root / dataset["key"]
                    if _stage_done(output_root, model, replica):
                        skipped += 1
                        logger.info("SKIP (já existe): {}", stage)
                        continue

                    if model in GATED_MODELS:
                        if model not in gate_results:
                            gate_results[model] = _probe_model(model)
                        if not gate_results[model]:
                            failures.append(f"{stage} (gate)")
                            logger.warning("SKIP (gate fechado): {}", stage)
                            continue

                    logger.info("STAGE START: {}", stage)
                    t0 = time.perf_counter()
                    try:
                        result = runner.run_single(
                            ifc_path=str(dataset["ifc"]),
                            ground_truth_path=str(dataset["gt"]),
                            building_context=BUILDING_CONTEXT,
                            ids_path=str(IDS_PATH),
                            model_name=model,
                            cache_enabled=False,
                            replica_index=replica,
                            timestamp=launch_stamp,
                            issue_types=dataset["issue_types"],
                            reuse_equivalent=args.reuse_equivalent,
                        )
                        ExperimentRunner._export(result, str(output_root))
                        completed += 1
                        dt = time.perf_counter() - t0
                        ev = result.evaluation
                        logger.info(
                            "STAGE OK: {} em {:.0f} min | top1={} top3={} | falhas_llm={}",
                            stage,
                            dt / 60,
                            ev.accuracy_top1,
                            ev.accuracy_top3,
                            result.stability.failed_count,
                        )
                    except Exception as exc:
                        failures.append(stage)
                        logger.exception("STAGE FAIL: {} ({})", stage, exc)

        # Relatórios por dataset (best-effort)
        from src.experiment.report import generate_report

        for dataset in DATASETS:
            root = results_root / dataset["key"]
            if root.is_dir():
                try:
                    generate_report(root, root / "report")
                except Exception as exc:
                    logger.warning("Relatório de {} falhou: {}", dataset["key"], exc)

        total_h = (time.perf_counter() - t_queue) / 3600
        logger.info(
            "FILA CONCLUÍDA em {:.1f} h: {} estágios ok, {} pulados, {} falhas: {}",
            total_h,
            completed,
            skipped,
            len(failures),
            failures or "nenhuma",
        )
        return 1 if failures else 0
    finally:
        PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
