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
import random
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
from src.experiment.per_issue import build_issue_outcomes, write_outcomes_jsonl
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


_REPO_COMMIT_AT_IMPORT: str | None = _repo_commit()
"""Commit do repositorio quando o processo carregou este modulo.

O metadata precisa descrever o codigo EXECUTADO. Lendo o HEAD ao final de um
estagio de horas, um commit feito no meio da medicao era gravado como se tivesse
rodado — aconteceu em 2026-07-28, com o run registrando um commit criado ~40 min
depois de o processo iniciar.
"""


def _ollama_version() -> str | None:
    """Retorna a versão do Ollama instalado (best-effort), ou None."""
    try:
        out = subprocess.run(
            ["ollama", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        match = re.search(r"(\d+\.\d+\.\d+)", out.stdout or "")
        return match.group(1) if match else None
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


def filter_issues_by_type(issues: list, issue_types: list[str]) -> list:
    """Filtra issues pelos tipos pedidos, com dedup por ``(guid, issue_type)``.

    O IDS pode gerar uma issue própria para o mesmo elemento/tarefa que o
    diagnóstico base já apontou (ex.: ``space_unnamed`` via requisito de
    atributo do IfcSpace). Mantém a **primeira** ocorrência — o diagnóstico
    base vem antes da integração IDS, tem o contexto rico e a chave natural
    ``(guid, tipo, "")`` que casa o ground truth. Sem o dedup, o dataset
    mascarado dobra as issues de nomeação e dilui as taxas do revisor simulado.
    """
    allowed = set(issue_types)
    seen_keys: set[tuple[str, str]] = set()
    filtered: list = []
    for issue in issues:
        if issue.issue_type not in allowed:
            continue
        key = (issue.element_guid, issue.issue_type)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        filtered.append(issue)
    return filtered


def stratified_sample(issues: list, max_issues: int, seed: int = 42) -> list:
    """Amostra determinística de issues, estratificada por ``issue_type``.

    Aloca cotas proporcionais ao tamanho de cada estrato (mínimo 1 por tipo
    enquanto couber) e sorteia dentro do estrato com ``random.Random(seed)``.
    Como os ``Issue.id`` são determinísticos (Fase 0.2) e a ordem do diagnose
    é estável, a amostra é reprodutível entre execuções. A ordem original do
    diagnóstico é preservada no resultado.
    """
    if max_issues <= 0 or len(issues) <= max_issues:
        return list(issues)

    by_type: dict[str, list] = {}
    for issue in issues:
        by_type.setdefault(issue.issue_type, []).append(issue)

    total = len(issues)
    # Cotas proporcionais (piso), depois distribui o resto aos maiores estratos
    quotas = {
        t: max(1, (max_issues * len(members)) // total) for t, members in by_type.items()
    }
    while sum(quotas.values()) > max_issues:
        largest = max(quotas, key=lambda t: quotas[t])
        quotas[largest] -= 1
    remainders = sorted(
        by_type,
        key=lambda t: (max_issues * len(by_type[t])) % total,
        reverse=True,
    )
    idx = 0
    while sum(quotas.values()) < max_issues:
        t = remainders[idx % len(remainders)]
        if quotas[t] < len(by_type[t]):
            quotas[t] += 1
        idx += 1

    rng = random.Random(seed)
    selected_ids: set[str] = set()
    for t, members in by_type.items():
        quota = min(quotas.get(t, 0), len(members))
        selected_ids.update(issue.id for issue in rng.sample(members, quota))

    return [issue for issue in issues if issue.id in selected_ids]


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
        max_issues: int | None = None,
        sample_seed: int = 42,
        issue_types: list[str] | None = None,
        reuse_equivalent: bool = False,
    ) -> ExperimentResult:
        """Executa uma réplica e retorna o ExperimentResult agregado.

        O pipeline roda sobre uma cópia descartável do IFC; o arquivo original
        em ``ifc_path`` nunca é modificado.

        Args:
            max_issues: se fornecido, limita a geração de sugestões a uma
                amostra determinística estratificada por issue_type (smoke
                tests e runs econômicos). None = todas as issues.
            sample_seed: semente da amostragem (reprodutibilidade).
            issue_types: se fornecido, restringe a geração às issues desses
                tipos (ex.: ``["space_unnamed"]`` no dataset mascarado, cuja
                única tarefa é nomeação — evita regerar as milhares de issues
                de Pset/sistemas já cobertas pelo dataset principal).
            reuse_equivalent: issues estruturalmente equivalentes reaproveitam a
                sugestão da primária em vez de repetir a chamada ao LLM. No modelo
                do experimento, 4720 issues correspondem a 1069 estímulos
                distintos, então o tempo cai ~77%. Registrado no metadata do run:
                as métricas de qualidade não mudam (o estímulo é idêntico), mas a
                telemetria de latência passa a medir estímulos, não issues.
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

                    report = pipeline.diagnose()
                    total_diagnosed = len(report.issues)
                    if issue_types:
                        report.issues = filter_issues_by_type(report.issues, issue_types)
                        logger.info(
                            "Filtro issue_types {} (dedup por guid): {}/{} issues",
                            sorted(issue_types),
                            len(report.issues),
                            total_diagnosed,
                        )
                    if max_issues is not None and len(report.issues) > max_issues:
                        sampled = stratified_sample(report.issues, max_issues, sample_seed)
                        report.issues = sampled
                        logger.info(
                            "Amostragem estratificada: {}/{} issues (seed={})",
                            len(sampled),
                            total_diagnosed,
                            sample_seed,
                        )
                    pipeline.generate_suggestions(reuse_equivalent=reuse_equivalent)

                    # 1) Avaliação vs ground truth (antes de qualquer mutação do modelo)
                    evaluation = evaluator.evaluate(
                        pipeline.issues_suggestions, ground_truth, profile=profile
                    )

                    # 1b) Resultado por issue (P1): o agregado sozinho esconde qual
                    # estrato acerta e impede teste pareado/analise de erro depois.
                    outcomes = build_issue_outcomes(
                        pipeline.issues_suggestions, ground_truth, evaluator
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
                        "sampled_from": total_diagnosed,
                        "sample_seed": sample_seed if max_issues is not None else None,
                        "issue_types_filter": sorted(issue_types) if issue_types else None,
                    }

                    metadata = RunMetadata(
                        model_name=settings.ollama_model,
                        ollama_version=_ollama_version(),
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
                        repo_commit=_REPO_COMMIT_AT_IMPORT,
                        cache_enabled=cache_enabled,
                        reuse_equivalent=reuse_equivalent,
                        bsdd_cache_sha256=sha256_of(settings.bsdd_cache_path),
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
                        outcomes=outcomes,
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
        max_issues: int | None = None,
        sample_seed: int = 42,
        issue_types: list[str] | None = None,
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
                max_issues=max_issues,
                sample_seed=sample_seed,
                issue_types=issue_types,
            )
            results.append(result)
            if output_dir is not None:
                self._export(result, output_dir)
        return results

    @staticmethod
    def _export(result: ExperimentResult, output_dir: str) -> str:
        """Exporta o JSON agregado + o JSONL por issue; retorna o caminho do JSON."""
        model_dir = Path(output_dir) / _sanitize(result.metadata.model_name)
        model_dir.mkdir(parents=True, exist_ok=True)
        replica = result.metadata.replica_index
        out_path = model_dir / f"run_{replica}.json"
        out_path.write_text(
            json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("ExperimentResult exportado: {}", out_path)

        # Resultado por issue: base do breakdown por estrato e do teste pareado.
        jsonl_path = model_dir / f"run_{replica}_issues.jsonl"
        write_outcomes_jsonl(result.outcomes, jsonl_path)
        logger.info("Resultados por issue exportados: {} ({} itens)", jsonl_path, len(result.outcomes))
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
    parser.add_argument(
        "--max-issues",
        type=int,
        default=None,
        help="Limita a amostra de issues (estratificada por tipo, determinística).",
    )
    parser.add_argument(
        "--sample-seed",
        type=int,
        default=42,
        help="Semente da amostragem estratificada (default 42).",
    )
    parser.add_argument(
        "--issue-types",
        default=None,
        help="Restringe a geração a estes issue_types (separados por vírgula).",
    )
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
        max_issues=args.max_issues,
        sample_seed=args.sample_seed,
        issue_types=(
            [t.strip() for t in args.issue_types.split(",") if t.strip()]
            if args.issue_types
            else None
        ),
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
