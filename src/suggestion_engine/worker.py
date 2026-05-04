"""Worker que processa issues em background, gerando sugestões via LLM."""

import inspect
import threading
from functools import lru_cache

from loguru import logger


@lru_cache(maxsize=32)
def _generate_params(func: object) -> frozenset[str]:
    """Cache de inspect.signature(generator.generate).parameters para evitar reflexão por issue."""
    return frozenset(inspect.signature(func).parameters)

from src.bsdd.context_builder import BSDDContextBuilder
from src.models import BSDDContext, IDSContext, ReadinessProfile
from src.suggestion_engine.issue_store import IssueStore
from src.suggestion_engine.suggestion import SuggestionGenerator


class SuggestionWorker:
    """Worker que processa issues em background, gerando sugestões via LLM."""

    def __init__(
        self,
        store: IssueStore,
        generator: SuggestionGenerator,
        building_context: dict,
        profile: ReadinessProfile | None = None,
        ids_context_map: dict[str, IDSContext] | None = None,
        bsdd_context_map: dict[str, BSDDContext] | None = None,
        context_builder: BSDDContextBuilder | None = None,
        grounding_mode: str = "ids_bsdd",
    ) -> None:
        self.store = store
        self.generator = generator
        self.building_context = building_context
        self.profile = profile
        self.ids_context_map = ids_context_map or {}
        self.bsdd_context_map = bsdd_context_map or {}
        self.context_builder = context_builder
        self.grounding_mode = "ids_bsdd"
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

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
        """Loop principal: pega próxima issue queued, gera sugestão, marca ready."""
        params = _generate_params(self.generator.generate)
        while not self._stop_event.is_set():
            issue_id = self.store.get_next_queued()
            if issue_id is None:
                if self.store.is_all_done():
                    break
                self._stop_event.wait(timeout=0.5)
                continue

            self.store.mark_processing(issue_id)
            issue = self.store.get_issue(issue_id)
            if issue is None:
                logger.warning("Worker: issue {} não encontrada no store, pulando.", issue_id)
                continue

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
                if "grounding_mode" in params:
                    kwargs["grounding_mode"] = self.grounding_mode
                suggestion_set = self.generator.generate(issue, self.building_context, **kwargs)
                self.store.mark_ready(issue_id, suggestion_set)
                logger.debug("Sugestão pronta para issue {}", issue_id)
            except Exception as e:
                self.store.mark_failed(issue_id, str(e))
                logger.error("Falha na issue {}: {}", issue_id, e)

    @property
    def is_running(self) -> bool:
        """Retorna True se a thread está ativa."""
        return self._thread is not None and self._thread.is_alive()

    def _issue_ids_context(self, issue) -> IDSContext | None:
        """Resolve IDSContext a partir da issue ou do cache legado."""
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
        """Resolve BSDDContext apenas quando o modo exige grounding bSDD."""
        if self.grounding_mode != "ids_bsdd" or self.context_builder is None:
            return None
        if issue.id in self.bsdd_context_map:
            return self.bsdd_context_map[issue.id]

        context = self.context_builder.build(issue, ids_context)
        if context is not None:
            self.bsdd_context_map[issue.id] = context
        return context
