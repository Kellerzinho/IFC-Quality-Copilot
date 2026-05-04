"""Gerador de sugestões de correção via LLM."""

import hashlib
from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING
from numbers import Number

from loguru import logger

from src.models import BSDDContext, IDSContext, Issue, OperationalRule, ReadinessProfile, Suggestion, SuggestionSet
from src.suggestion_engine.normalization import normalize_suggestion, normalize_value_for_issue, suggestion_identity_key
from src.suggestion_engine.ollama_client import OllamaClient
from src.suggestion_engine.prompt_templates import SYSTEM_PROMPT, build_prompt, parse_llm_response

if TYPE_CHECKING:
    from src.suggestion_engine.prompt_router import PromptRouter


class SuggestionGenerator:
    """Gera sugestões de correção usando LLM."""

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
        bsdd_context: BSDDContext | None = None,
        ids_context: IDSContext | None = None,
        grounding_mode: str = "none",
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
        use_grounded_prompt = grounding_mode != "none" and (
            bsdd_context is not None or ids_context is not None
        )

        if use_grounded_prompt:
            from src.bsdd.context_builder import build_grounding_block
            from src.suggestion_engine.prompt_templates import build_grounded_prompt

            grounding_block = build_grounding_block(ids_context, bsdd_context, grounding_mode)
            system = SYSTEM_PROMPT
            user = build_grounded_prompt(
                issue=issue,
                building_context=self._format_building_context(building_context),
                grounding_block=grounding_block,
                grounding_mode=grounding_mode,
            )
        elif self.prompt_router is not None:
            system, user = self._build_prompt_via_router(issue, building_context, profile, rule)
        else:
            system, user = build_prompt(
                issue,
                building_context,
                profile_id=profile.id if profile is not None else None,
                bsdd_context=bsdd_context,
                ids_context=ids_context,
                grounding_mode=grounding_mode,
            )

        prompt_hash = self._hash_prompt(system, user)

        last_exc: Exception | None = None
        current_user_prompt = user
        for attempt in range(self._MAX_ATTEMPTS):
            try:
                raw = self.client.generate(prompt=current_user_prompt, system=system)
                suggestions = parse_llm_response(raw, issue.issue_type)
                suggestions = self._validate_suggestions(
                    suggestions,
                    issue,
                    bsdd_context=bsdd_context,
                    ids_context=ids_context,
                )
                if bsdd_context is not None:
                    suggestions = self._validate_against_bsdd(suggestions, bsdd_context, issue)
                error = None
                if not suggestions:
                    error = "Saida do LLM invalida ou fora do schema esperado"
                    if attempt < self._MAX_ATTEMPTS - 1:
                        logger.debug(
                            "Resposta LLM rejeitada pelo validador para issue {} na tentativa {}/{}; tentando novamente. Raw: {!r}",
                            issue.id,
                            attempt + 1,
                            self._MAX_ATTEMPTS,
                            raw[:1000],
                        )
                        current_user_prompt = self._build_retry_prompt(issue, user)
                        continue
                    logger.warning(
                        "Resposta LLM vazia/invalidada para issue {} na tentativa {}/{}. Raw: {!r}",
                        issue.id,
                        attempt + 1,
                        self._MAX_ATTEMPTS,
                        raw[:1000],
                    )
                return SuggestionSet(issue_id=issue.id, suggestions=suggestions, error=error, prompt_hash=prompt_hash)
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
            prompt_hash=prompt_hash,
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

    def _build_retry_prompt(self, issue: Issue, original_prompt: str) -> str:
        """Monta prompt corretivo quando a resposta parseada nao sobrevive a validacao."""
        check_property = str(issue.context.get("check_property") or "").strip()
        extra = ""
        if issue.issue_type == "pset_missing" and check_property == "FireRating":
            extra = (
                " Para FireRating, o campo value deve ser um rating gravavel como "
                '"REI 30", "REI 60", "EI 30" ou "EI 60". '
                "Use duracoes usuais como 30, 60, 90 ou 120 minutos. "
                'Nao retorne null, "N/A", "R 1", "A1", "FireRating", texto explicativo ou nome da propriedade como value.'
            )
        elif issue.issue_type == "pset_missing" and check_property == "ThermalTransmittance":
            extra = " Para ThermalTransmittance, o campo value deve ser numerico, sem unidade."

        return (
            f"{original_prompt}\n\nA resposta anterior foi rejeitada pelo validador. "
            'Retorne somente JSON valido no formato {"opcoes":[{"value": ..., '
            '"label": "...", "justification": "...", "confidence": "alta"}]}. '
            "O campo value nao pode ser nulo nem descritivo; ele deve ser o valor que pode ser escrito no IFC."
            f"{extra}"
        )

    def generate_batch(
        self,
        issues: list[Issue],
        building_context: dict,
        on_progress: Callable[[int, int], None] | None = None,
        ids_context_map: dict[str, IDSContext] | None = None,
        bsdd_context_map: dict[str, BSDDContext] | None = None,
        grounding_mode: str = "none",
    ) -> list[SuggestionSet]:
        """Gera sugestões para várias issues sequencialmente.

        Processa uma issue por vez (Ollama é single-threaded).
        Chama on_progress(current, total) após cada issue processada.
        Retorna lista na mesma ordem das issues recebidas.
        """
        total = len(issues)
        results: list[SuggestionSet] = []

        for i, issue in enumerate(issues, start=1):
            result = self.generate(
                issue,
                building_context,
                bsdd_context=bsdd_context_map.get(issue.id) if bsdd_context_map else None,
                ids_context=ids_context_map.get(issue.id) if ids_context_map else None,
                grounding_mode=grounding_mode,
            )
            results.append(result)
            if on_progress is not None:
                on_progress(i, total)

        return results

    def _format_building_context(self, building_context: dict) -> str:
        """Serializa building_context em texto simples para o prompt grounded."""
        if not building_context:
            return "N/D"

        lines: list[str] = []
        for key, value in building_context.items():
            if value is None:
                rendered = "N/D"
            elif isinstance(value, list):
                rendered = ", ".join(str(item) for item in value) if value else "nenhum"
            elif isinstance(value, dict):
                rendered = ", ".join(f"{k}: {v}" for k, v in value.items()) if value else "nenhum"
            else:
                rendered = str(value)
            lines.append(f"- {key}: {rendered}")
        return "\n".join(lines)

    def _validate_suggestions(
        self,
        suggestions: list[Suggestion],
        issue: Issue,
        bsdd_context: BSDDContext | None = None,
        ids_context: IDSContext | None = None,
    ) -> list[Suggestion]:
        """Valida e limpa sugestões geradas pelo LLM.

        - Remove sugestões com label vazio ou só espaços
        - Remove duplicatas (por label)
        - Limita a 3 sugestões
        """
        seen: set[str] = set()
        clean: list[Suggestion] = []

        for s in suggestions:
            normalized = normalize_suggestion(issue, s, bsdd_context=bsdd_context)
            if normalized is None or not normalized.label.strip():
                continue
            dedupe_key = suggestion_identity_key(issue, normalized)
            if dedupe_key in seen:
                continue
            if ids_context is not None and normalized.ids_requirement_id is None:
                normalized.ids_requirement_id = ids_context.requirement_id
            seen.add(dedupe_key)
            clean.append(normalized)

        return clean[:3]

    def _validate_against_bsdd(
        self,
        suggestions: list[Suggestion],
        bsdd_context: BSDDContext,
        issue: Issue,
    ) -> list[Suggestion]:
        """Rebaixa confiança de sugestões inconsistentes com o vocabulário bSDD."""
        issue_type = issue.issue_type
        target_property = str(issue.context.get("check_property") or "").strip().casefold()
        for suggestion in suggestions:
            if issue_type == "pset_missing":
                for prop in bsdd_context.properties:
                    if target_property and prop.name.strip().casefold() != target_property:
                        continue
                    if prop.data_type and not self._matches_bsdd_data_type(suggestion.value, prop.data_type):
                        self._downgrade_for_bsdd(
                            suggestion,
                            f"tipo incompatível com bSDD ({prop.data_type})",
                        )
                        break

                    if prop.allowed_values:
                        allowed_values = {
                            str(normalize_value_for_issue(issue, value) or value)
                            for value in prop.allowed_values
                        }
                        if str(suggestion.value) not in allowed_values:
                            self._downgrade_for_bsdd(
                                suggestion,
                                "valor fora do vocabulário bSDD",
                            )
                            break

            elif issue_type in {"space_unnamed", "system_unclassified"} and bsdd_context.classes:
                allowed_labels = {
                    str(normalize_value_for_issue(issue, cls.name) or cls.name).strip().casefold()
                    for cls in bsdd_context.classes
                    if cls.name
                }
                if allowed_labels and str(suggestion.value).strip().casefold() not in allowed_labels:
                    self._downgrade_for_bsdd(
                        suggestion,
                        "valor fora do vocabulário bSDD",
                    )

        return suggestions

    def _matches_bsdd_data_type(self, value: object, data_type: str) -> bool:
        """Valida compatibilidade simples entre valor sugerido e tipo esperado pelo bSDD."""
        normalized = data_type.strip().lower()

        if normalized in {"real", "float", "double", "number", "numeric", "decimal"}:
            if isinstance(value, bool):
                return False
            if isinstance(value, Number):
                return True
            if isinstance(value, str):
                try:
                    float(value.replace(",", "."))
                    return True
                except ValueError:
                    return False
            return False

        if normalized in {"integer", "int"}:
            if isinstance(value, bool):
                return False
            if isinstance(value, int):
                return True
            if isinstance(value, float):
                return value.is_integer()
            if isinstance(value, str):
                stripped = value.strip()
                if stripped.startswith(("+", "-")):
                    stripped = stripped[1:]
                return stripped.isdigit()
            return False

        if normalized in {"boolean", "bool"}:
            if isinstance(value, bool):
                return True
            if isinstance(value, str):
                return value.strip().lower() in {"true", "false", "yes", "no", "sim", "nao", "não", "0", "1"}
            return False

        return True

    def _downgrade_for_bsdd(self, suggestion: Suggestion, note: str) -> None:
        """Rebaixa confiança e anota inconsistência com o bSDD sem remover a sugestão."""
        suggestion.confidence = "baixa"
        marker = f"({note})"
        if marker not in suggestion.justification:
            suggestion.justification = f"{suggestion.justification} {marker}".strip()

    def _hash_prompt(self, system_prompt: str, user_prompt: str) -> str:
        """Gera hash estável do prompt final."""
        payload = f"{system_prompt}\n---\n{user_prompt}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]
