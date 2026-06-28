"""Harness experimental (Fase 0.5 / F2+F6+F7+F12).

Dado ``(ifc_path, ids_path, ground_truth_path, model_name, n_réplicas, cache)``:

1. constrói o pipeline sobre uma **cópia descartável** do IFC (o original nunca é tocado);
2. roda ``diagnose()`` → gera sugestões (grounding IDS+bSDD);
3. avalia vs ground truth (``Evaluator`` — Fase 0.3);
4. aplica o **revisor simulado** (F6) e mede conformidade IDS pós-correção na cópia;
5. agrega ``ExperimentResult`` (metadados + avaliação + proxy + estabilidade + eficiência)
   e exporta JSON versionável.

Uso:

    python -m src.experiment.runner --ifc modelo.ifc --ids perfil.ids \\
        --ground-truth gt.yaml --model qwen2.5:7b-instruct --replicas 3 \\
        --no-cache --output src/experiment/results/2026-06-28
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from loguru import logger

from src.config import get_settings
from src.experiment.evaluator import Evaluator, GroundTruth
from src.experiment.metrics import (
    ExperimentResult,
    RunMetadata,
    aggregate_stability,
    aggregate_timing,
    calculate_metrics,
)
from src.experiment.reviewer import simulate_review
from src.models import ReadinessProfile
from src.pipeline import QualityPipeline
from src.suggestion_engine.suggestion_cache import PROMPT_VERSION

# Tipo do injetor de geração (para mockar o LLM em testes)
BatchFn = Callable[..., list]


def sha256_of(path: str | Path | None) -> str | None:
    """Calcula o SHA256 de um arquivo, ou None se o caminho for None/inexistente."""
    if path is None:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    digest = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_commit() -> str | None:
    """Retorna o commit HEAD do repositório (best-effort), ou None."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        commit = out.stdout.strip()
        return commit or None
    except Exception:
        return None


@contextmanager
def _settings_override(model_name: str | None, cache_enabled: bool):
    """Aplica modelo e toggle de cache via env + limpa o cache de get_settings."""
    saved = {
        "OLLAMA_MODEL": os.environ.get("OLLAMA_MODEL"),
        "SUGGESTION_CACHE_ENABLED": os.environ.get("SUGGESTION_CACHE_ENABLED"),
    }
    try:
        if model_name:
            os.environ["OLLAMA_MODEL"] = model_name
        os.environ["SUGGESTION_CACHE_ENABLED"] = "true" if cache_enabled else "false"
        get_settings.cache_clear()
        yield get_settings()
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()


def _sanitize(name: str) -> str:
    """Torna um nome de modelo seguro para uso em caminho de arquivo."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


class ExperimentRunner:
    """Executa o experimento de benchmark sobre cópias descartáveis do IFC."""

    def __init__(self, suggestion_batch_fn: BatchFn | None = None) -> None:
        """Configura o runner.

        Args:
            suggestion_batch_fn: injeção opcional para substituir
                ``pipeline.suggestion_gen.generate_batch`` (mock do LLM em testes).
                Se None, usa o LLM real via Ollama.
        """
        self.suggestion_batch_fn = suggestion_batch_fn

    # ------------------------------------------------------------------
    # Execução de uma réplica
    # ------------------------------------------------------------------

    def run_single(
        self,
        ifc_path: str,
        ground_truth_path: str,
        building_context: dict[str, Any],
        ids_path: str | None = None,
        model_name: str | None = None,
        cache_enabled: bool = False,
        replica_index: int = 0,
        profile: ReadinessProfile | None = None,
        timestamp: str | None = None,
    ) -> ExperimentResult:
        """Executa uma réplica e retorna o ExperimentResult agregado.

        O pipeline roda sobre uma cópia descartável do IFC; o arquivo original
        em ``ifc_path`` nunca é modificado.
        """
        ground_truth = GroundTruth.from_yaml(ground_truth_path)
        evaluator = Evaluator()

        ifc_hash = sha256_of(ifc_path)
        tmp_dir = tempfile.mkdtemp(prefix="ifc_exp_")
        copy_path = os.path.join(tmp_dir, Path(ifc_path).name)
        shutil.copy2(ifc_path, copy_path)

        try:
            with _settings_override(model_name, cache_enabled) as settings:
                pipeline = QualityPipeline(
                    copy_path,
                    building_context,
                    ids_path=ids_path,
                    profile=profile,
                )
                try:
                    if self.suggestion_batch_fn is not None:
                        pipeline.suggestion_gen.generate_batch = self.suggestion_batch_fn  # type: ignore[method-assign]

                    pipeline.diagnose()
                    pipeline.generate_suggestions()

                    # 1) Avaliação vs ground truth (antes de qualquer mutação do modelo)
                    evaluation = evaluator.evaluate(
                        pipeline.issues_suggestions, ground_truth, profile=profile
                    )

                    # 2) Telemetria de estabilidade/eficiência (F12)
                    metrics_list = [
                        ss.metrics
                        for _, ss in pipeline.issues_suggestions
                        if ss.metrics is not None
                    ]
                    stability = aggregate_stability(metrics_list)
                    timing = aggregate_timing(metrics_list)

                    # 3) Revisor simulado + conformidade IDS na cópia descartável (F6)
                    review_proxy, _decisions = simulate_review(
                        pipeline, ground_truth, evaluator
                    )

                    reviewed_issues = [issue for issue, _ in pipeline.issues_suggestions]
                    decisions = calculate_metrics(reviewed_issues)
                    issue_counts = {
                        "total_issues": len(reviewed_issues),
                        "issues_from_ids": pipeline._ids_issues_count,
                        "ids_rules": pipeline._ids_rules_count,
                        "with_ground_truth": evaluation.total_evaluated,
                    }

                    metadata = RunMetadata(
                        model_name=settings.ollama_model,
                        ollama_version=None,
                        seed=settings.ollama_seed,
                        temperature=settings.ollama_temperature,
                        top_p=settings.ollama_top_p,
                        num_ctx=settings.ollama_num_ctx,
                        num_predict=settings.ollama_num_predict,
                        repeat_penalty=settings.ollama_repeat_penalty,
                        ifc_sha256=ifc_hash or "",
                        ids_sha256=sha256_of(ids_path),
                        ground_truth_sha256=sha256_of(ground_truth_path),
                        prompt_version=PROMPT_VERSION,
                        repo_commit=_repo_commit(),
                        cache_enabled=cache_enabled,
                        replica_index=replica_index,
                        timestamp=timestamp,
                    )

                    return ExperimentResult(
                        metadata=metadata,
                        evaluation=evaluation,
                        review_proxy=review_proxy,
                        stability=stability,
                        timing=timing,
                        decisions=decisions,
                        issue_counts=issue_counts,
                    )
                finally:
                    pipeline.close()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            # Garantia: o IFC original permanece byte-idêntico.
            if ifc_hash is not None and sha256_of(ifc_path) != ifc_hash:
                logger.error("INVARIANTE VIOLADA: o IFC original foi alterado pelo harness!")

    # ------------------------------------------------------------------
    # Execução de N réplicas + exportação
    # ------------------------------------------------------------------

    def run(
        self,
        ifc_path: str,
        ground_truth_path: str,
        building_context: dict[str, Any],
        ids_path: str | None = None,
        model_name: str | None = None,
        cache_enabled: bool = False,
        n_replicas: int = 3,
        profile: ReadinessProfile | None = None,
        output_dir: str | None = None,
        timestamp: str | None = None,
    ) -> list[ExperimentResult]:
        """Executa N réplicas e, se ``output_dir`` for dado, exporta um JSON por réplica."""
        results: list[ExperimentResult] = []
        for i in range(n_replicas):
            logger.info("Réplica {}/{} (model={})", i + 1, n_replicas, model_name or "default")
            result = self.run_single(
                ifc_path=ifc_path,
                ground_truth_path=ground_truth_path,
                building_context=building_context,
                ids_path=ids_path,
                model_name=model_name,
                cache_enabled=cache_enabled,
                replica_index=i,
                profile=profile,
                timestamp=timestamp,
            )
            results.append(result)
            if output_dir is not None:
                self._export(result, output_dir)
        return results

    @staticmethod
    def _export(result: ExperimentResult, output_dir: str) -> str:
        """Exporta um ExperimentResult como JSON versionável e retorna o caminho."""
        model_dir = Path(output_dir) / _sanitize(result.metadata.model_name)
        model_dir.mkdir(parents=True, exist_ok=True)
        out_path = model_dir / f"run_{result.metadata.replica_index}.json"
        out_path.write_text(
            json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("ExperimentResult exportado: {}", out_path)
        return str(out_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.experiment.runner",
        description="Harness experimental do IFC Quality Copilot (benchmark de LLMs locais).",
    )
    parser.add_argument("--ifc", required=True, help="Caminho do IFC de entrada (com lacunas).")
    parser.add_argument("--ids", default=None, help="Caminho do perfil IDS (.ids).")
    parser.add_argument("--ground-truth", required=True, help="Caminho do ground_truth.yaml.")
    parser.add_argument("--model", default=None, help="Modelo Ollama (ex.: qwen2.5:7b-instruct).")
    parser.add_argument("--replicas", type=int, default=3, help="Número de réplicas (default 3).")
    parser.add_argument(
        "--cache",
        dest="cache",
        action="store_true",
        help="Habilita o cache de sugestões (default: desabilitado para variância).",
    )
    parser.add_argument(
        "--no-cache",
        dest="cache",
        action="store_false",
        help="Desabilita o cache de sugestões (default).",
    )
    parser.set_defaults(cache=False)
    parser.add_argument("--output", default=None, help="Diretório de saída dos JSON por réplica.")
    parser.add_argument("--building-context", default=None, help="JSON inline do building_context.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada da CLI do harness."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    building_context: dict[str, Any] = {}
    if args.building_context:
        building_context = json.loads(args.building_context)

    runner = ExperimentRunner()
    results = runner.run(
        ifc_path=args.ifc,
        ground_truth_path=args.ground_truth,
        building_context=building_context,
        ids_path=args.ids,
        model_name=args.model,
        cache_enabled=args.cache,
        n_replicas=args.replicas,
        output_dir=args.output,
    )
    logger.info("Concluído: {} réplicas.", len(results))
    if results:
        ev = results[0].evaluation
        logger.info(
            "Réplica 0 — top1={} top3={} f1={} | conformidade IDS proxy={}",
            ev.accuracy_top1,
            ev.accuracy_top3,
            ev.f1,
            results[0].review_proxy.ids_conformity_rate,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
