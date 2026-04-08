"""Gerador de sugestões de correção via LLM para issues não resolvidas pelo Rule Engine."""

from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING

from loguru import logger

from src.models import Issue, OperationalRule, ReadinessProfile, Suggestion, SuggestionSet
from src.suggestion_engine.ollama_client import OllamaClient
from src.suggestion_engine.prompt_templates import build_prompt, parse_llm_response

if TYPE_CHECKING:
    from src.suggestion_engine.prompt_router import PromptRouter


class SuggestionGenerator:
    """Gera sugestões de correção usando LLM para issues não resolvidas pelo Rule Engine."""

    _MAX_ATTEMPTS = 3

    def __init__(
        self,
        ollama_client: OllamaClient,
        prompt_router: "PromptRouter | None" = None,
    ) -> None:
        self.client = ollama_client
        self.prompt_router = prompt_router

    def generate(
        self,
        issue: Issue,
        building_context: dict,
        profile: ReadinessProfile | None = None,
        rule: OperationalRule | None = None,
    ) -> SuggestionSet:
        """Gera SuggestionSet para uma issue.

        Se prompt_router foi fornecido no construtor, usa-o para selecionar o template
        e montar o contexto (recebe profile e rule opcionais).
        Caso contrário, usa build_prompt() diretamente (modo legacy).

        1. Monta prompt (via router ou build_prompt)
        2. Chama ollama_client.generate()
        3. Parseia resposta via parse_llm_response()
        4. Valida e limpa sugestões
        5. Se falhar 3x → retorna SuggestionSet com error
        """
        if self.prompt_router is not None:
            system, user = self._build_prompt_via_router(issue, building_context, profile, rule)
        else:
            system, user = build_prompt(issue, building_context)

        last_exc: Exception | None = None
        for attempt in range(self._MAX_ATTEMPTS):
            try:
                raw = self.client.generate(prompt=user, system=system)
                suggestions = parse_llm_response(raw, issue.issue_type)
                suggestions = self._validate_suggestions(suggestions, issue)
                return SuggestionSet(issue_id=issue.id, suggestions=suggestions)
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Tentativa {}/{} para issue {} falhou: {}",
                    attempt + 1,
                    self._MAX_ATTEMPTS,
                    issue.id,
                    exc,
                )

        logger.error("Geração falhou após {} tentativas para issue {}", self._MAX_ATTEMPTS, issue.id)
        return SuggestionSet(
            issue_id=issue.id,
            suggestions=[],
            error=f"Falha na geração após {self._MAX_ATTEMPTS} tentativas",
        )

    def _build_prompt_via_router(
        self,
        issue: Issue,
        building_context: dict,
        profile: ReadinessProfile | None,
        rule: OperationalRule | None,
    ) -> tuple[str, str]:
        """Usa o PromptRouter para selecionar template e montar contexto.

        Retorna (system_prompt, user_prompt) com placeholders preenchidos.
        """
        system_prompt, template = self.prompt_router.route(issue, profile, rule)
        fill_ctx = self.prompt_router.build_context(issue, building_context, profile)
        safe_ctx: defaultdict = defaultdict(lambda: "N/D", fill_ctx)
        user_prompt = template.format_map(safe_ctx)
        return system_prompt, user_prompt

    def generate_batch(
        self,
        issues: list[Issue],
        building_context: dict,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[SuggestionSet]:
        """Gera sugestões para várias issues sequencialmente.

        Processa uma issue por vez (Ollama é single-threaded).
        Chama on_progress(current, total) após cada issue processada.
        Retorna lista na mesma ordem das issues recebidas.
        """
        total = len(issues)
        results: list[SuggestionSet] = []

        for i, issue in enumerate(issues, start=1):
            result = self.generate(issue, building_context)
            results.append(result)
            if on_progress is not None:
                on_progress(i, total)

        return results

    def _validate_suggestions(self, suggestions: list[Suggestion], issue: Issue) -> list[Suggestion]:
        """Valida e limpa sugestões geradas pelo LLM.

        - Remove sugestões com label vazio ou só espaços
        - Remove duplicatas (por label)
        - Limita a 3 sugestões
        """
        seen: set[str] = set()
        clean: list[Suggestion] = []

        for s in suggestions:
            if not s.label.strip():
                continue
            if s.label in seen:
                continue
            seen.add(s.label)
            clean.append(s)

        return clean[:3]
