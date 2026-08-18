"""Orquestração principal: diagnóstico → regras → LLM → validação → escrita."""

import json
import os
import inspect
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=64)
def _cached_signature_params(func: Any) -> frozenset[str]:
    """Cache de inspect.signature(func).parameters keys; evita reflexão em hot paths."""
    return frozenset(inspect.signature(func).parameters)

import ifcopenshell
from loguru import logger

from src.audit.logger import AuditLogger
from src.bcf.exporter import BCFExporter
from src.bsdd.client import BSDDClient
from src.bsdd.context_builder import BSDDContextBuilder, build_grounding_block
from src.config import get_settings
from src.ifc_analyzer.analyzer import IFCAnalyzer
from src.models import (
    AuditEntry,
    BSDDContext,
    DiagnosticReport,
    IDSContext,
    Issue,
    OperationalRule,
    ReadinessProfile,
    ReadinessScore,
    SuggestionSet,
    ValidationResult,
)
from src.semantic.property_match import properties_match
from src.suggestion_engine.issue_deduplicator import IssueDeduplicator
from src.suggestion_engine.issue_store import IssueStore
from src.suggestion_engine.normalization import normalize_value_for_issue
from src.suggestion_engine.ollama_client import OllamaClient
from src.suggestion_engine.suggestion import SuggestionGenerator
from src.suggestion_engine.suggestion_cache import PROMPT_VERSION, SuggestionCache
from src.suggestion_engine.worker import SuggestionWorker
from src.translator.ids_parser import parse_ids
from src.translator.rule_generator import apply_rules, generate_rules
from src.validation.post_validator import PostValidator
from src.writer.ifc_writer import IFCWriter

# Mapeamento element_class → pset padrão para correções pset_missing
_PSET_FOR_CLASS: dict[str, str] = {
    "IfcWall": "Pset_WallCommon",
    "IfcWallStandardCase": "Pset_WallCommon",
    "IfcDoor": "Pset_DoorCommon",
    "IfcWindow": "Pset_WindowCommon",
    "IfcSlab": "Pset_SlabCommon",
    "IfcSlabStandardCase": "Pset_SlabCommon",
    "IfcSpace": "Pset_SpaceCommon",
    "IfcColumn": "Pset_ColumnCommon",
    "IfcBeam": "Pset_BeamCommon",
    "IfcRoof": "Pset_RoofCommon",
    "IfcStair": "Pset_StairCommon",
    "IfcCurtainWall": "Pset_CurtainWallCommon",
}


class QualityPipeline:
    """Orquestração principal: diagnóstico → regras → LLM → validação → escrita."""

    def __init__(
        self,
        ifc_path: str,
        building_context: dict,
        ids_path: str | None = None,
        profile: ReadinessProfile | None = None,
        use_bsdd: bool = True,
    ) -> None:
        """Inicializa o pipeline.

        Args:
            use_bsdd: quando False, o pipeline não instancia o cliente bSDD e
                nenhuma issue recebe contexto do dicionário. É o braço de
                tratamento da condição de ablação de grounding
                (docs/condicao-ablacao-bsdd-2026-08-18.md) — o padrão do
                produto e de toda rodada anterior é True.
        """
        self.ifc_path = ifc_path
        self.building_context = building_context
        self.profile = profile
        self.use_bsdd = use_bsdd
        self.settings = get_settings()

        # ids_path explícito tem prioridade; se não fornecido, tenta inferir do perfil
        if ids_path is not None:
            self.ids_path: str | None = ids_path
        elif profile is not None and profile.ids_filename is not None:
            ids_template_dir = Path(__file__).parent.parent / "data" / "ids_templates"
            candidate = ids_template_dir / profile.ids_filename
            self.ids_path = str(candidate) if candidate.exists() else None
            if self.ids_path is None:
                logger.warning(
                    "IDS do perfil '{}' não encontrado em '{}'",
                    profile.ids_filename,
                    ids_template_dir,
                )
        else:
            self.ids_path = None

        self.analyzer = IFCAnalyzer(ifc_path)
        self.ifc_file = self.analyzer.ifc_file  # mesmo objeto, sem double-open
        self.writer = IFCWriter(self.ifc_file)
        self.audit_logger = AuditLogger(model_name=Path(ifc_path).stem)
        self._ollama_client = OllamaClient()
        self.suggestion_cache: SuggestionCache | None = None
        if self.settings.suggestion_cache_enabled:
            try:
                cache_path = Path(self.settings.suggestion_cache_path)
                if not cache_path.is_absolute():
                    cache_path = Path(__file__).parent.parent / cache_path
                self.suggestion_cache = SuggestionCache(cache_path)
                # Invalidacao por modelo NAO e feita aqui: apagaria o cache dos demais
                # modelos e inviabilizaria o benchmark multi-modelo. Use `make clean-cache`.
                self.suggestion_cache.invalidate_by_prompt(PROMPT_VERSION)
            except Exception as exc:
                logger.warning("SuggestionCache desabilitado: {}", exc)
                self.suggestion_cache = None
        self.suggestion_gen = SuggestionGenerator(self._ollama_client, cache=self.suggestion_cache)
        self.deduplicator = IssueDeduplicator()
        self._reuse_map: dict[str, str] = {}
        self.suggestion_metrics: list[dict] = []
        # Ablação de grounding: sem builder, `_issue_bsdd_context` devolve None
        # para toda issue e o prompt perde o bloco BSDD_CONTEXT.
        self.bsdd_client: BSDDClient | None = BSDDClient() if use_bsdd else None
        self.bsdd_builder: BSDDContextBuilder | None = (
            BSDDContextBuilder(self.bsdd_client) if self.bsdd_client is not None else None
        )
        if not use_bsdd:
            logger.warning("bSDD DESLIGADO nesta execucao (ablacao de grounding)")
        self.operational_rules: list[OperationalRule] = []
        self.post_validator = PostValidator(
            self.ifc_file,
            self.operational_rules,
            run_schema_on_element_validation=False,
        )
        self.bcf_exporter = BCFExporter()

        self.report: DiagnosticReport | None = None
        self.issues_suggestions: list[tuple[Issue, SuggestionSet]] = []
        self.issue_store: IssueStore | None = None
        self.worker: SuggestionWorker | None = None
        self.ids_context_map: dict[str, IDSContext] = {}
        self.bsdd_context_map: dict[str, BSDDContext] = {}
        # Memoizacao por (classe, issue_type, propriedade): e disso que a consulta
        # ao bSDD depende, nao do GUID da issue.
        self._bsdd_context_by_key: dict[tuple[str, str, str], BSDDContext] = {}
        self._validation_results: dict[str, ValidationResult] = {}
        self.applied_entries: dict[str, AuditEntry] = {}

        self._ids_loaded: bool = False
        self._ids_specs_count: int = 0
        self._ids_rules_count: int = 0
        self._ids_issues_count: int = 0

        logger.info("QualityPipeline iniciado: {}", ifc_path)

    def close(self) -> None:
        """Libera recursos do pipeline (fecha conexão HTTP do Ollama e cache)."""
        self.stop_worker()
        self._ollama_client.close()
        if self.bsdd_client is not None:
            self.bsdd_client.close()
        if self.suggestion_cache is not None:
            try:
                self.suggestion_cache.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Diagnóstico
    # ------------------------------------------------------------------

    def diagnose(self) -> DiagnosticReport:
        """Executa análise completa do modelo e armazena o relatório.

        Se ids_path foi fornecido, integra as regras do IDS ao diagnóstico,
        mesclando issues adicionais (deduplicadas por guid + issue_type + check_property).
        Falhas no parse do IDS são logadas como warning e o pipeline continua normalmente.
        """
        self.report = self.analyzer.analyze()

        if self.ids_path is not None:
            self._integrate_ids()

        logger.info(
            "diagnose: {} issues encontradas em '{}'",
            self.report.total_issues,
            self.report.model_name,
        )
        return self.report

    def _integrate_ids(self) -> None:
        """Parseia o IDS, gera regras e mescla issues ao relatório (sem duplicatas)."""
        try:
            specs = parse_ids(self.ids_path)  # type: ignore[arg-type]
            rules = generate_rules(specs)
            ids_issues = apply_rules(self.ifc_file, rules)

            existing_keys: set[tuple[str, str, str]] = {
                (i.element_guid, i.issue_type, i.context.get("check_property", ""))
                for i in self.report.issues  # type: ignore[union-attr]
            }
            new_issues: list[Issue] = []
            for issue in ids_issues:
                key = (issue.element_guid, issue.issue_type, issue.context.get("check_property", ""))
                if key not in existing_keys:
                    new_issues.append(issue)
                    existing_keys.add(key)

            self.operational_rules = rules
            self.post_validator = PostValidator(
                self.ifc_file,
                self.operational_rules,
                run_schema_on_element_validation=False,
            )
            self._ids_specs_count = len(specs)
            self._ids_rules_count = len(rules)
            self._ids_issues_count = len(new_issues)
            self._ids_loaded = True

            self.report.issues.extend(new_issues)  # type: ignore[union-attr]
            self._build_ids_context_map()
            logger.info(
                "IDS carregado: {} specs → {} regras → {} issues adicionais",
                len(specs),
                len(rules),
                len(new_issues),
            )
        except Exception as exc:
            logger.warning("Falha ao integrar IDS '{}': {}", self.ids_path, exc)

    # ------------------------------------------------------------------
    # Geração de sugestões
    # ------------------------------------------------------------------

    def generate_suggestions(
        self,
        on_progress: Callable[[int, int], None] | None = None,
        reuse_equivalent: bool = False,
    ) -> list[tuple[Issue, SuggestionSet]]:
        """LLM com grounding bSDD/IDS para todas as issues do relatório.

        Retorna lista de (Issue, SuggestionSet) na mesma ordem das issues
        do DiagnosticReport.

        Args:
            on_progress: callback de progresso (processadas, total).
            reuse_equivalent: quando True, issues estruturalmente equivalentes
                copiam a sugestão da primária em vez de repetir a chamada ao LLM
                — o mesmo mecanismo que a interface já usa em lote. Reduz muito o
                tempo em modelos grandes (num modelo real, 4720 issues colapsam em
                1069 estímulos distintos), ao custo de o ``n`` de chamadas deixar
                de coincidir com o ``n`` de issues na telemetria.
        """
        if self.report is None:
            raise RuntimeError("Chame diagnose() antes de generate_suggestions()")

        self._prepare_grounding_contexts(self.report.issues)
        reuse_map: dict[str, str] | None = None
        if reuse_equivalent:
            reuse_map = self.deduplicator.build_reuse_map(list(self.report.issues))
            if reuse_map:
                logger.info(
                    "Reuso de equivalentes: {} de {} issues reaproveitam sugestao ({} grupos)",
                    len(reuse_map),
                    len(self.report.issues),
                    len(set(reuse_map.values())),
                )
        llm_sets = self._generate_batch_with_compat(
            list(self.report.issues),
            on_progress=on_progress,
            reuse_map=reuse_map,
        )
        combined: list[tuple[Issue, SuggestionSet]] = list(zip(self.report.issues, llm_sets))
        issue_order = {issue.id: idx for idx, issue in enumerate(self.report.issues)}

        if self.profile is not None:
            profile_types = set(self.profile.issue_types)
            combined.sort(key=lambda pair: (
                0 if pair[0].issue_type in profile_types else 1,
                issue_order.get(pair[0].id, len(self.report.issues)),
            ))
        else:
            combined.sort(key=lambda pair: issue_order.get(pair[0].id, len(self.report.issues)))

        self.issues_suggestions = combined
        logger.info("generate_suggestions: {} via LLM", len(combined))
        return self.issues_suggestions

    def diagnose_and_start_suggestions(self) -> DiagnosticReport:
        """Fase 1: diagnóstico rápido.
        Fase 2: inicia worker LLM em background para issues pendentes.

        1. Rodar diagnose() (rápido)
        2. Criar IssueStore, adicionar todas issues
        3. Iniciar SuggestionWorker em background
        4. Retornar DiagnosticReport (UI ja pode mostrar)
        """
        report = self.diagnose()

        priority_types = list(self.profile.issue_types) if self.profile else None

        self.issue_store = IssueStore(max_concurrent=self.settings.max_concurrent_llm_calls)
        self.issue_store.add_issues(report.issues, priority_issue_types=priority_types)
        self._prepare_grounding_contexts(report.issues)
        self._reuse_map = self.deduplicator.build_reuse_map(list(report.issues))
        if self._reuse_map:
            logger.info(
                "Deduplicacao: {} issues secundarias reusarao sugestoes ({} grupos)",
                len(self._reuse_map),
                len(set(self._reuse_map.values())),
            )

        self.worker = SuggestionWorker(
            store=self.issue_store,
            generator=self.suggestion_gen,
            building_context=self.building_context,
            profile=self.profile,
            ids_context_map=self.ids_context_map,
            bsdd_context_map=self.bsdd_context_map,
            context_builder=self.bsdd_builder,
            reuse_map=self._reuse_map,
            warm_up=True,
        )
        self.worker.start()

        logger.info(
            "diagnose_and_start_suggestions: {} enfileiradas para LLM",
            len(report.issues),
        )
        return report

    def get_suggestions_progress(self) -> dict:
        """Retorna progresso do IssueStore para polling da UI."""
        if self.issue_store is None:
            return {
                "total": 0,
                "queued": 0,
                "processing": 0,
                "ready": 0,
                "cached": 0,
                "reused": 0,
                "invalid": 0,
                "failed": 0,
                "review_required": 0,
                "cancelled": 0,
                "percent_complete": 0.0,
            }
        return self.issue_store.get_progress()

    def collect_suggestion_metrics(self) -> list[dict]:
        """Coleta métricas de todas as sugestões geradas até agora.

        Útil para exportação ao final ou debug. Retorna lista de dicts.
        """
        out: list[dict] = []
        if self.issue_store is None:
            return out
        for item in self.issue_store.get_all_with_status():
            sset = item.get("suggestion")
            if sset is None or sset.metrics is None:
                continue
            payload = sset.metrics.model_dump()
            payload["status"] = item["status"]
            out.append(payload)
        return out

    def get_available_issues(self) -> list[tuple[Issue, SuggestionSet | None, str]]:
        """Retorna issues com sugestões prontas + issues ainda em processamento.

        Cada item: (issue, suggestion_set_or_none, status)
        """
        if self.issue_store is None:
            return []
        return [
            (item["issue"], item["suggestion"], item["status"])
            for item in self.issue_store.get_all_with_status()
        ]

    def stop_worker(self) -> None:
        """Para o worker em background (chamado ao sair da sessão)."""
        if self.worker is not None:
            self.worker.stop()
            self.worker = None
            logger.info("Worker de sugestões parado")

    # ------------------------------------------------------------------
    # Aplicação de correções
    # ------------------------------------------------------------------

    def apply_correction(
        self, issue_id: str, value: Any, decision: str, user: str
    ) -> AuditEntry:
        """Aplica correção aprovada pelo engenheiro e registra na auditoria."""
        pair = self.get_issue_by_id(issue_id)
        if pair is None:
            raise ValueError(f"Issue não encontrada: {issue_id}")

        issue, suggestion_set = pair
        top = suggestion_set.top_suggestion
        validation_result = ValidationResult(guid=issue.element_guid, status="skip")

        normalized_value = value
        old_value: Any = None
        if decision in ("accepted", "edited"):
            normalized_value = self._normalize_decision_value(issue, value)
            old_value = self._write_correction(issue, normalized_value)
            validation_result = self._validate_after_write(issue)
            if validation_result.status == "fail":
                logger.warning(
                    "Post-validacao falhou apos correcao: issue={} guid={} errors={}",
                    issue.id,
                    issue.element_guid,
                    validation_result.errors,
                )

        entry = AuditEntry(
            element_guid=issue.element_guid,
            element_class=issue.element_class,
            action=self._action_for(issue),
            field=self._field_for(issue),
            old_value=old_value,
            new_value=normalized_value,
            decision=decision,
            confidence=top.confidence if top else "baixa",
            normative_ref=top.normative_ref if top else None,
            source=top.source if top else "llm",
            user=user,
            grounding_sources=self._grounding_sources_for(issue.id),
            bsdd_uri=(top.bsdd_uri if top and top.bsdd_uri else self._default_bsdd_uri(issue.id)),
            ids_requirement=(
                top.ids_requirement_id
                if top and top.ids_requirement_id
                else self._default_ids_requirement(issue.id)
            ),
            post_validation=validation_result.status,
            prompt_hash=suggestion_set.prompt_hash,
        )
        self.audit_logger.log(entry)
        self.applied_entries[issue.id] = entry
        self._validation_results[issue.id] = validation_result
        issue.resolve(value=normalized_value, decision=decision)

        logger.debug(
            "apply_correction: issue={} decision={} value={}",
            issue_id,
            decision,
            normalized_value,
        )
        return entry

    def skip_issue(self, issue_id: str, user: str) -> None:
        """Marca uma issue como pulada sem escrever no modelo."""
        pair = self.get_issue_by_id(issue_id)
        if pair is None:
            raise ValueError(f"Issue não encontrada: {issue_id}")
        issue, _ = pair
        issue.resolve(value=None, decision="skipped")
        logger.debug("skip_issue: issue={} user={}", issue_id, user)

    # ------------------------------------------------------------------
    # Exportação
    # ------------------------------------------------------------------

    def export(self, output_dir: str) -> dict[str, str]:
        """Exporta IFC corrigido, logs de auditoria e métricas para output_dir."""
        os.makedirs(output_dir, exist_ok=True)
        stem = Path(self.ifc_path).stem

        ifc_out = os.path.join(output_dir, f"{stem}_corrigido.ifc")
        csv_out = os.path.join(output_dir, f"{stem}_auditoria.csv")
        json_out = os.path.join(output_dir, f"{stem}_auditoria.jsonl")
        metrics_out = os.path.join(output_dir, f"{stem}_metricas.json")
        bcf_out = os.path.join(output_dir, f"{stem}_issues.bcf")

        saved_ifc = self.writer.salvar(ifc_out)
        saved_csv = self.audit_logger.export_csv(csv_out)
        saved_json = self.audit_logger.export_json(json_out)
        issues = self._get_export_issues()
        saved_bcf = self.bcf_exporter.export(issues, Path(bcf_out))

        metrics: dict[str, Any] = {
            "model": stem,
            "ids_file": self.ids_path,
            "ids_specs_count": self._ids_specs_count,
            "ids_rules_count": self._ids_rules_count,
            "issues_from_ids_count": self._ids_issues_count,
            "profile_id": self.profile.id if self.profile else None,
            "profile_name": self.profile.name if self.profile else None,
            "post_validation": {
                issue_id: result.status for issue_id, result in self._validation_results.items()
            },
        }
        if self.profile is not None and self.report is not None:
            try:
                score = self.compute_readiness()
                metrics["readiness_score"] = score.score_percent
                metrics["readiness_status"] = score.status
                metrics["readiness_blocking_issues"] = score.blocking_issues
            except Exception as exc:
                logger.warning("compute_readiness no export falhou: {}", exc)

        suggestion_metrics = self.collect_suggestion_metrics()
        if suggestion_metrics:
            metrics["suggestion_metrics"] = suggestion_metrics
            cache_hits = sum(1 for m in suggestion_metrics if m.get("cache_hit"))
            reused = sum(1 for m in suggestion_metrics if m.get("reused_from_issue_id"))
            metrics["llm_call_summary"] = {
                "total": len(suggestion_metrics),
                "cache_hits": cache_hits,
                "reused": reused,
                "fresh_calls": len(suggestion_metrics) - cache_hits - reused,
            }
        with open(metrics_out, "w", encoding="utf-8") as fh:
            json.dump(metrics, fh, ensure_ascii=False, indent=2)

        logger.info("Arquivo BCF exportado: {}", saved_bcf)
        logger.info(
            "export: IFC={} CSV={} JSON={} BCF={} metrics={}",
            saved_ifc, saved_csv, saved_json, saved_bcf, metrics_out,
        )
        return {
            "ifc": saved_ifc,
            "csv": saved_csv,
            "json": saved_json,
            "bcf": saved_bcf,
            "metrics": metrics_out,
        }

    # ------------------------------------------------------------------
    # Sumário do IDS
    # ------------------------------------------------------------------

    def get_ids_summary(self) -> dict | None:
        """Retorna sumário do IDS carregado, ou None se não há IDS.

        Chaves retornadas:
            - specs_count: número de specifications parseadas
            - rules_count: número de regras geradas
            - rules_by_severity: {high, medium, low} com contagens
            - issues_from_ids: issues adicionais geradas pelo IDS (pós-dedup)
        """
        if not self._ids_loaded:
            return None

        rules_by_severity: dict[str, int] = {}
        for rule in self.operational_rules:
            rules_by_severity[rule.severity] = rules_by_severity.get(rule.severity, 0) + 1

        return {
            "specs_count": self._ids_specs_count,
            "rules_count": self._ids_rules_count,
            "rules_by_severity": rules_by_severity,
            "issues_from_ids": self._ids_issues_count,
        }

    # ------------------------------------------------------------------
    # Readiness
    # ------------------------------------------------------------------

    def compute_readiness(self) -> ReadinessScore:
        """Calcula o ReadinessScore do modelo para o perfil ativo.

        Raises:
            RuntimeError: se diagnose() ainda não foi executado.
            ValueError: se nenhum perfil estiver selecionado.
        """
        if self.report is None:
            raise RuntimeError("Chame diagnose() antes de compute_readiness()")
        if self.profile is None:
            raise ValueError("Nenhum perfil selecionado")

        relevant_issues = [
            i for i in self.report.issues
            if i.issue_type in self.profile.issue_types
        ]
        # total_checks = regras aplicadas via IDS + total de issues do diagnóstico base
        total_checks = self._ids_rules_count + self.report.total_issues
        if total_checks == 0:
            total_checks = 1

        return ReadinessScore.compute(
            profile=self.profile,
            issues=relevant_issues,
            total_checks=total_checks,
        )

    def get_readiness_summary(self) -> dict:
        """Retorna resumo do score de readiness para o perfil ativo.

        Retorna dict vazio se não há perfil ou diagnóstico executado.
        Chaves: score, status, blocking_issues, issues_by_type_for_profile.
        """
        if self.profile is None or self.report is None:
            return {}

        score = self.compute_readiness()
        relevant_issues = [
            i for i in self.report.issues
            if i.issue_type in self.profile.issue_types
        ]
        issues_by_type: dict[str, int] = {}
        for issue in relevant_issues:
            issues_by_type[issue.issue_type] = issues_by_type.get(issue.issue_type, 0) + 1

        return {
            "score": score.score_percent,
            "status": score.status,
            "blocking_issues": score.blocking_issues,
            "issues_by_type_for_profile": issues_by_type,
        }

    # ------------------------------------------------------------------
    # Consulta de estado
    # ------------------------------------------------------------------

    def get_progress(self) -> dict:
        """Retorna progresso: total, resolved, pending, percentage."""
        total = len(self.issues_suggestions)
        if total == 0:
            return {"total": 0, "resolved": 0, "pending": 0, "percentage": 0.0}

        resolved = sum(
            1
            for issue, _ in self.issues_suggestions
            if issue.status in ("accepted", "edited", "rejected", "skipped")
        )
        pending = total - resolved
        percentage = resolved / total * 100

        return {
            "total": total,
            "resolved": resolved,
            "pending": pending,
            "percentage": percentage,
        }

    def get_issue_by_id(self, issue_id: str) -> tuple[Issue, SuggestionSet] | None:
        """Retorna (Issue, SuggestionSet) pelo ID da issue, ou None se não encontrado.

        Pesquisa primeiro em issues_suggestions (modo legado) e depois no
        issue_store (modo progressivo), onde issues_suggestions fica vazio.
        """
        for issue, suggestion_set in self.issues_suggestions:
            if issue.id == issue_id:
                return issue, suggestion_set
        if self.issue_store is not None:
            for item in self.issue_store.get_all_with_status():
                if item["issue"].id == issue_id and item["suggestion"] is not None:
                    return item["issue"], item["suggestion"]
        return None

    def get_post_validation_result(self, issue_id: str) -> ValidationResult | None:
        """Retorna o resultado de pÃ³s-validaÃ§Ã£o armazenado para a issue."""
        return self._validation_results.get(issue_id)

    @property
    def validation_results(self) -> dict[str, ValidationResult]:
        """Compatibilidade com consumidores legados da UI."""
        return self._validation_results

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _action_for(self, issue: Issue) -> str:
        """Retorna nome da ação de auditoria para o tipo de issue."""
        return {
            "space_unnamed": "renomear_espaco",
            "pset_missing": "preencher_pset",
            "quantity_missing": "preencher_base_quantities",
            "classification_missing": "mapear_classificacao",
            "relation_broken": "criar_relacao_fills",
            "system_unclassified": "classificar_sistema",
        }.get(issue.issue_type, "correcao_generica")

    def _field_for(self, issue: Issue) -> str:
        """Retorna o campo alvo da correção para o tipo de issue."""
        if issue.issue_type == "space_unnamed":
            return "LongName"
        if issue.issue_type == "pset_missing":
            return issue.context.get("check_property", "propriedade")
        if issue.issue_type == "quantity_missing":
            return issue.context.get("check_property", "quantidade")
        if issue.issue_type == "classification_missing":
            return "IfcClassificationReference"
        if issue.issue_type == "material_unmapped":
            return "material"
        if issue.issue_type == "relation_broken":
            return "IfcRelFillsElement"
        if issue.issue_type == "system_unclassified":
            return "Sistema Construtivo"
        return "valor"

    def _resolve_target_pset(self, issue: Issue) -> str:
        """Resolve em qual Pset a correção de pset_missing deve ser escrita.

        Precedência: o pset exigido pelo IDS (``check_pset``, gravado por
        apply_rules) vem primeiro, depois o pset apontado pelo diagnóstico
        programático (``pset_name``) e, por último, o pset padrão da classe.
        """
        ctx = issue.context or {}
        pset = ctx.get("check_pset") or ctx.get("pset_name")
        if isinstance(pset, str) and pset.strip():
            return pset.strip()
        return _PSET_FOR_CLASS.get(issue.element_class, "Pset_WallCommon")

    def _write_correction(self, issue: Issue, value: Any) -> Any:
        """Executa a escrita no IFC e retorna o valor anterior."""
        if issue.issue_type == "space_unnamed":
            _, old = self.writer.renomear_espaco(issue.element_guid, str(value))
            return old

        if issue.issue_type == "pset_missing":
            prop = issue.context.get("check_property", "")
            pset = self._resolve_target_pset(issue)
            _, old_props = self.writer.preencher_pset(
                issue.element_guid, pset, {prop: value}
            )
            return old_props.get(prop)

        if issue.issue_type == "quantity_missing":
            quantity = issue.context.get("check_property", "")
            qto = issue.context.get("check_pset", "")
            if not qto or not quantity:
                raise ValueError(f"Contexto Qto incompleto para issue {issue.id}")
            _, old_quantities = self.writer.preencher_base_quantities(
                issue.element_guid, qto, {quantity: float(value)}
            )
            return old_quantities.get(quantity)

        if issue.issue_type == "classification_missing":
            _, old = self.writer.mapear_classificacao(
                issue.element_guid,
                "Sistema de classificacao orcamentaria",
                str(value),
                str(value),
            )
            return old

        if issue.issue_type == "material_unmapped":
            raise ValueError(
                "Material nao mapeado exige revisao manual; nao ha escrita automatica segura"
            )

        if issue.issue_type == "relation_broken":
            wall_guid = issue.context.get("wall_host_guid") or ""
            if not wall_guid:
                # Sem parede hospedeira detectada: sugestão é descritiva, não executável.
                # Registra na auditoria mas não tenta escrever no modelo.
                logger.info(
                    "_write_correction: relation_broken sem wall_host_guid — "
                    "correção marcada como aceita sem escrita automática (element={})",
                    issue.element_guid,
                )
                return None
            self.writer.criar_relacao_fills(issue.element_guid, wall_guid)
            return None

        if issue.issue_type == "system_unclassified":
            _, old = self.writer.classificar_sistema(issue.element_guid, str(value))
            return old

        return None

    def _normalize_decision_value(self, issue: Issue, value: Any) -> Any:
        """Normaliza o valor aprovado antes de escrever no IFC."""
        normalized = normalize_value_for_issue(issue, value)
        if normalized is None:
            raise ValueError(f"Valor invalido para issue {issue.issue_type}: {value!r}")
        return normalized

    def _generate_batch_with_compat(
        self,
        issues: list[Issue],
        on_progress: Callable[[int, int], None] | None = None,
        reuse_map: dict[str, str] | None = None,
    ) -> list[SuggestionSet]:
        """Chama generate_batch aceitando implementações legadas/mocadas."""
        for issue in issues:
            self._resolve_grounding_for_issue(issue)

        kwargs: dict[str, Any] = {"on_progress": on_progress}
        params = _cached_signature_params(self.suggestion_gen.generate_batch)
        if "ids_context_map" in params:
            kwargs["ids_context_map"] = self.ids_context_map
        if "bsdd_context_map" in params:
            kwargs["bsdd_context_map"] = self.bsdd_context_map
        if reuse_map and "reuse_map" in params:
            kwargs["reuse_map"] = reuse_map
        return self.suggestion_gen.generate_batch(issues, self.building_context, **kwargs)

    def _generate_with_grounding(
        self,
        issues: list[Issue],
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[SuggestionSet]:
        """Resolve grounding por issue e chama generate() sequencialmente."""
        params = _cached_signature_params(self.suggestion_gen.generate)
        total = len(issues)
        results: list[SuggestionSet] = []

        for index, issue in enumerate(issues, start=1):
            ids_context, bsdd_context, _grounding_block = self._resolve_grounding_for_issue(issue)
            kwargs: dict[str, Any] = {}
            if "profile" in params:
                kwargs["profile"] = self.profile
            if "ids_context" in params:
                kwargs["ids_context"] = ids_context
            if "bsdd_context" in params:
                kwargs["bsdd_context"] = bsdd_context
            results.append(self.suggestion_gen.generate(issue, self.building_context, **kwargs))
            if on_progress is not None:
                on_progress(index, total)

        return results

    def _build_ids_context_map(self) -> None:
        """Reconstrói o mapa issue_id -> IDSContext a partir das regras operacionais."""
        rule_by_id = {rule.id: rule for rule in self.operational_rules}
        self.ids_context_map = {}
        if self.report is None:
            return

        for issue in self.report.issues:
            rule_id = issue.context.get("rule_id")
            if not rule_id:
                continue
            rule = rule_by_id.get(rule_id)
            if rule is None:
                continue
            self.ids_context_map[issue.id] = IDSContext(
                issue_id=issue.id,
                requirement_id=rule.id,
                specification_name=rule.source_spec,
                check_pset=rule.check_pset,
                check_property=rule.check_property,
                check_type=rule.check_type,
                expected_value=rule.expected_value,
                severity=rule.severity,
                unit=rule.evidence_source,
                requirement_text=issue.description,
            )

    def _prepare_grounding_contexts(self, issues: list[Issue]) -> None:
        """Pré-carrega mapas de grounding conforme o modo ativo."""
        if self.ids_path is not None and not self.ids_context_map:
            self._build_ids_context_map()

        for issue in issues:
            ids_context = self._issue_ids_context(issue)
            if ids_context is not None:
                self.ids_context_map.setdefault(issue.id, ids_context)

    def _issue_ids_context(self, issue: Issue) -> IDSContext | None:
        """Resolve IDSContext a partir da issue ou do cache legado."""
        payload = issue.context.get("ids_context")
        if isinstance(payload, IDSContext):
            self.ids_context_map.setdefault(issue.id, payload)
            return payload
        if isinstance(payload, dict):
            try:
                context = IDSContext.model_validate(payload)
            except Exception as exc:
                logger.warning("Falha ao reconstruir IDSContext da issue {}: {}", issue.id, exc)
            else:
                if context.issue_id is None:
                    context.issue_id = issue.id
                self.ids_context_map[issue.id] = context
                return context

        context = self.ids_context_map.get(issue.id)
        if context is not None and context.issue_id is None:
            context.issue_id = issue.id
        return context

    @staticmethod
    def _bsdd_context_key(issue: Issue) -> tuple[str, str, str]:
        """Chave estrutural do contexto bSDD: o que a consulta de fato depende."""
        ctx = issue.context or {}
        prop = str(
            ctx.get("check_property")
            or ctx.get("property_name")
            or ctx.get("classification_query")
            or ""
        )
        return (issue.element_class, issue.issue_type, prop)

    def _issue_bsdd_context(
        self,
        issue: Issue,
        ids_context: IDSContext | None = None,
    ) -> BSDDContext | None:
        """Resolve BSDDContext sob demanda, memoizando por combinacao estrutural.

        A consulta ao bSDD depende de (classe, issue_type, propriedade) e nao do
        GUID: num modelo real sao milhares de issues para pouco mais de vinte
        combinacoes. Cachear apenas por ``issue.id`` reconstruia — e revalidava no
        Pydantic — o mesmo contexto uma vez por issue.
        """
        if self.bsdd_builder is None:
            return None
        if issue.id in self.bsdd_context_map:
            return self.bsdd_context_map[issue.id]

        key = self._bsdd_context_key(issue)
        cached = self._bsdd_context_by_key.get(key)
        if cached is not None:
            # issue_id identifica a issue que originou a consulta; a copia mantem
            # o mapa por issue coerente para os consumidores a jusante.
            context = cached.model_copy(update={"issue_id": issue.id})
            self.bsdd_context_map[issue.id] = context
            return context

        context = self.bsdd_builder.build(issue, ids_context)
        if context is not None:
            self.bsdd_context_map[issue.id] = context
            self._bsdd_context_by_key[key] = context
        return context

    def _resolve_grounding_for_issue(
        self,
        issue: Issue,
    ) -> tuple[IDSContext | None, BSDDContext | None, str]:
        """Resolve IDS + bSDD para a issue e monta o bloco final de grounding."""
        ids_context = self._issue_ids_context(issue)
        bsdd_context = self._issue_bsdd_context(issue, ids_context)
        grounding_block = build_grounding_block(ids_context, bsdd_context)
        return ids_context, bsdd_context, grounding_block

    def _validate_after_write(self, issue: Issue) -> ValidationResult:
        """Executa o gate pós-correção para a issue alterada."""
        if not self.settings.post_validation_enabled:
            return ValidationResult(guid=issue.element_guid, status="skip")
        return self.post_validator.validate_element(issue.element_guid)

    def _revert_correction(self, issue: Issue, old_value: Any) -> None:
        """Reverte a correção quando o gate pós-validação falha."""
        if issue.issue_type == "space_unnamed":
            self.writer.renomear_espaco(issue.element_guid, str(old_value or ""))
            return

        if issue.issue_type == "pset_missing":
            prop = issue.context.get("check_property", "")
            pset = self._resolve_target_pset(issue)
            if old_value is not None:
                self.writer.preencher_pset(issue.element_guid, pset, {prop: old_value})
            return

        if issue.issue_type == "quantity_missing":
            quantity = issue.context.get("check_property", "")
            qto = issue.context.get("check_pset", "")
            if old_value is not None and qto and quantity:
                self.writer.preencher_base_quantities(
                    issue.element_guid, qto, {quantity: float(old_value)}
                )
            return

        if issue.issue_type == "system_unclassified" and old_value:
            self.writer.classificar_sistema(issue.element_guid, str(old_value))

    def _grounding_sources_for(self, issue_id: str) -> list[str]:
        """Lista as fontes de grounding efetivamente usadas pela issue."""
        sources: list[str] = []
        if issue_id in self.ids_context_map:
            sources.append("ids")
        if issue_id in self.bsdd_context_map:
            sources.append("bsdd")
        return sources

    def _default_bsdd_uri(self, issue_id: str) -> str | None:
        """Retorna URI bSDD padrão da issue, se houver."""
        context = self.bsdd_context_map.get(issue_id)
        pair = self.get_issue_by_id(issue_id)
        issue = pair[0] if pair is not None else None
        if context and issue is not None:
            if issue.issue_type == "pset_missing":
                target_property = str(issue.context.get("check_property") or "").strip()
                for prop in context.properties:
                    # name humano ("Fire Rating") ou code PascalCase do bSDD vs
                    # check_property do IFC — matcher compartilhado (fix 2026-08-04).
                    matches = bool(
                        (prop.code and properties_match(target_property, prop.code))
                        or properties_match(target_property, prop.name)
                    )
                    if matches and prop.uri:
                        return prop.uri
            if context.source_uris:
                return context.source_uris[0]
        return None

    def _default_ids_requirement(self, issue_id: str) -> str | None:
        """Retorna requirement_id IDS padrão da issue, se houver."""
        context = self.ids_context_map.get(issue_id)
        return context.requirement_id if context is not None else None

    def _get_export_issues(self) -> list[Issue]:
        """Retorna a lista completa de issues para exportação de artefatos."""
        if self.issue_store is not None:
            return [item["issue"] for item in self.issue_store.get_all_with_status()]
        if self.report is not None:
            return list(self.report.issues)
        return []
