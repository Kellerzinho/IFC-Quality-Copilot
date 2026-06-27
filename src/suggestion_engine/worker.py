"""Worker que processa issues em background, gerando sugestões via LLM."""

from __future__ import annotations

import inspect
import threading
import time
from functools import lru_cache

from loguru import logger


@lru_cache(maxsize=32)
def _generate_params(func: object) -> frozenset[str]:
    """Cache de inspect.signature(generator.generate).parameters."""
    return frozenset(inspect.signature(func).parameters)


from src.bsdd.context_builder import BSDDContextBuilder
from src.models import BSDDContext, IDSContext, ReadinessProfile, SuggestionMetrics, SuggestionSet
from src.suggestion_engine.issue_store import IssueStore
from src.suggestion_engine.suggestion import SuggestionGenerator


class SuggestionWorker:
    """Worker que processa issues em background, gerando sugestões via LLM.

    Suporta:
    - Reuse via reuse_map (issues estruturalmente equivalentes).
    - Backpressure via IssueStore.can_accept_processing().
    - Status finos: ready / cached / reused / review_required / failed.
    """

    def __init__(
        self,
        store: IssueStore,
        generator: SuggestionGenerator,
        building_context: dict,
        profile: ReadinessProfile | None = None,
        ids_context_map: dict[str, IDSContext] | None = None,
        bsdd_context_map: dict[str, BSDDContext] | None = None,
        context_builder: BSDDContextBuilder | None = None,
        reuse_map: dict[str, str] | None = None,
        warm_up: bool = True,
    ) -> None:
        self.store = store
        self.generator = generator
        self.building_context = building_context
        self.profile = profile
        self.ids_context_map = ids_context_map or {}
        self.bsdd_context_map = bsdd_context_map or {}
        self.context_builder = context_builder
        self.reuse_map = reuse_map or {}
        self._warm_up = warm_up
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._enqueue_times: dict[str, float] = {}
        self._primary_results: dict[str, SuggestionSet] = {}

    def start(self) -> None:
        """Inicia processamento em thread separada."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("SuggestionWorker iniciado")

    def stop(self) -> None:
        """Sinaliza parada e aguarda thread finalizar."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("SuggestionWorker parado")

    def _run(self) -> None:
        """Loop principal: pega próxima issue queued, gera sugestão, atualiza status."""
        params = _generate_params(self.generator.generate)

        if self._warm_up and self._should_warm_up():
            client = getattr(self.generator, "client", None)
            warm_up_fn = getattr(client, "warm_up", None) if client is not None else None
            if callable(warm_up_fn):
                try:
                    warm_up_fn()
                except Exception as exc:
                    logger.debug("Warm-up Ollama falhou: {}", exc)

        while not self._stop_event.is_set():
            if not self.store.can_accept_processing():
                self._stop_event.wait(timeout=0.1)
                continue

            issue_id = self.store.get_next_queued()
            if issue_id is None:
                if self.store.is_all_done():
                    break
                self._stop_event.wait(timeout=0.5)
                continue

            issue = self.store.get_issue(issue_id)
            if issue is None:
                logger.warning("Worker: issue {} não encontrada, pulando.", issue_id)
                continue

            self.store.mark_processing(issue_id)
            queue_wait_ms = self._pop_queue_wait(issue_id)

            # ----- Reuse (deduplicação) -----
            primary_id = self.reuse_map.get(issue_id)
            if primary_id and primary_id != issue_id and primary_id in self._primary_results:
                primary = self._primary_results[primary_id]
                metrics = SuggestionMetrics(
                    issue_id=issue_id,
                    queue_wait_ms=queue_wait_ms,
                    reused_from_issue_id=primary_id,
                    final_status="reused",
                )
                reused = SuggestionSet(
                    issue_id=issue_id,
                    suggestions=[s.model_copy() for s in primary.suggestions],
                    error=primary.error,
                    prompt_hash=primary.prompt_hash,
                    metrics=metrics,
                )
                self.store.mark_reused(issue_id, reused, from_issue_id=primary_id)
                continue

            # ----- Geração normal (cache lookup acontece dentro do generator) -----
            try:
                ids_context = self._issue_ids_context(issue)
                bsdd_context = self._issue_bsdd_context(issue, ids_context)
                kwargs = {}
                if "profile" in params:
                    kwargs["profile"] = self.profile
                if "ids_context" in params:
                    kwargs["ids_context"] = ids_context
                if "bsdd_context" in params:
                    kwargs["bsdd_context"] = bsdd_context

                t0 = time.perf_counter()
                suggestion_set = self.generator.generate(issue, self.building_context, **kwargs)
                gen_ms = (time.perf_counter() - t0) * 1000

                # Atualiza queue_wait_ms se existir métrica
                if suggestion_set.metrics is None:
                    suggestion_set.metrics = SuggestionMetrics(issue_id=issue_id)
                suggestion_set.metrics.queue_wait_ms = queue_wait_ms
                if suggestion_set.metrics.llm_total_ms == 0 and not suggestion_set.metrics.cache_hit:
                    suggestion_set.metrics.llm_total_ms = gen_ms

                # Decisão de status final baseada em métricas + grounding
                if not suggestion_set.suggestions:
                    self.store.mark_failed(issue_id, suggestion_set.error or "sem sugestoes")
                elif suggestion_set.metrics.cache_hit:
                    suggestion_set.metrics.final_status = "cached"
                    self.store.mark_cached(issue_id, suggestion_set)
                elif self._all_review_required(suggestion_set):
                    suggestion_set.metrics.final_status = "review_required"
                    self.store.mark_review_required(issue_id, suggestion_set)
                else:
                    suggestion_set.metrics.final_status = "ready"
                    self.store.mark_ready(issue_id, suggestion_set)

                self._primary_results[issue_id] = suggestion_set
            except Exception as e:
                self.store.mark_failed(issue_id, str(e))
                logger.error("Falha na issue {}: {}", issue_id, e)

    @staticmethod
    def _all_review_required(suggestion_set: SuggestionSet) -> bool:
        """True se todas as sugestões estão marcadas como review_required."""
        return bool(suggestion_set.suggestions) and all(s.review_required for s in suggestion_set.suggestions)

    def _should_warm_up(self) -> bool:
        """Evita warm-up real quando generate foi substituido por mock/test double."""
        generate_fn = getattr(self.generator, "generate", None)
        if not inspect.ismethod(generate_fn):
            return False
        underlying = getattr(generate_fn, "__func__", generate_fn)
        return getattr(underlying, "__module__", None) == "src.suggestion_engine.suggestion"

    def _pop_queue_wait(self, issue_id: str) -> float:
        enqueued = self._enqueue_times.pop(issue_id, None)
        if enqueued is None:
            return 0.0
        return (time.perf_counter() - enqueued) * 1000

    def mark_enqueued(self, issue_id: str) -> None:
        """Hook opcional para o pipeline registrar timestamp de enfileiramento."""
        self._enqueue_times[issue_id] = time.perf_counter()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    # Resolução de contexto
    # ------------------------------------------------------------------

    def _issue_ids_context(self, issue) -> IDSContext | None:
        payload = issue.context.get("ids_context")
        if isinstance(payload, IDSContext):
            self.ids_context_map.setdefault(issue.id, payload)
            return payload
        if isinstance(payload, dict):
            try:
                context = IDSContext.model_validate(payload)
            except Exception as exc:
                logger.warning("Worker: falha ao reconstruir IDSContext da issue {}: {}", issue.id, exc)
            else:
                if context.issue_id is None:
                    context.issue_id = issue.id
                self.ids_context_map[issue.id] = context
                return context

        context = self.ids_context_map.get(issue.id)
        if context is not None and context.issue_id is None:
            context.issue_id = issue.id
        return context

    def _issue_bsdd_context(
        self,
        issue,
        ids_context: IDSContext | None = None,
    ) -> BSDDContext | None:
        if self.context_builder is None:
            return None
        if issue.id in self.bsdd_context_map:
            return self.bsdd_context_map[issue.id]

        context = self.context_builder.build(issue, ids_context)
        if context is not None:
            self.bsdd_context_map[issue.id] = context
        return context
