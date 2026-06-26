"""Gerador de sugestões de correção via LLM.

Integra grounding compacto, cache persistente e métricas leves.
"""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from collections.abc import Callable
from numbers import Number
from typing import TYPE_CHECKING, Any

from loguru import logger

from src.config import get_settings
from src.models import (
    BSDDContext,
    IDSContext,
    Issue,
    OperationalRule,
    ReadinessProfile,
    Suggestion,
    SuggestionMetrics,
    SuggestionSet,
)
from src.suggestion_engine.grounding import GroundedIssueContext, prepare_llm_grounding
from src.suggestion_engine.issue_deduplicator import (
    _bucket_area,
    _bucket_thickness,
    _context_text_hints,
    _fingerprint_adjacent_spaces,
    _fingerprint_contained_elements,
    _fingerprint_existing_psets,
    _fingerprint_material_layers,
    _rounded_measure,
    is_safe_to_reuse,
)
from src.suggestion_engine.normalization import (
    normalize_suggestion,
    normalize_value_for_issue,
    suggestion_identity_key,
)
from src.suggestion_engine.ollama_client import OllamaClient
from src.suggestion_engine.prompt_templates import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_COMPACT,
    build_compact_prompt,
    build_prompt,
    parse_llm_response,
)
from src.suggestion_engine.suggestion_cache import (
    SuggestionCache,
    compute_signature as compute_cache_signature,
)

if TYPE_CHECKING:
    from src.suggestion_engine.prompt_router import PromptRouter


def _ns_to_ms(ns: int | float) -> float:
    """Converte nanossegundos do Ollama em milissegundos."""
    try:
        return float(ns) / 1_000_000.0
    except (TypeError, ValueError):
        return 0.0


def _coerce_generate_result(raw_result: Any) -> tuple[str, dict]:
    """Aceita tanto str (mocks legados) quanto (str, dict) do OllamaClient novo."""
    if isinstance(raw_result, tuple) and len(raw_result) == 2:
        text, metrics = raw_result
        return str(text), dict(metrics or {})
    return str(raw_result), {}


class SuggestionGenerator:
    """Gera sugestões de correção usando LLM, com cache e métricas."""

    _MAX_ATTEMPTS = 3

    def __init__(
        self,
        ollama_client: OllamaClient,
        prompt_router: "PromptRouter | None" = None,
        cache: SuggestionCache | None = None,
    ) -> None:
        self.client = ollama_client
        self.prompt_router = prompt_router
        self.cache = cache
        self._model_version = getattr(ollama_client, "model", "unknown")

    # ------------------------------------------------------------------
    # Geração principal
    # ------------------------------------------------------------------

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

        Fluxo:
        1. Prepara grounding compacto.
        2. Calcula assinatura de cache; retorna cache hit se disponível.
        3. Chama LLM com prompt compacto (ou legacy quando router fornecido).
        4. Parse + validação Pydantic + rejeição de campos extras.
        5. Persiste no cache em sucesso.
        """
        settings = get_settings()
        metrics = SuggestionMetrics(issue_id=issue.id, final_status="processing")

        t0 = time.perf_counter()
        grounded = prepare_llm_grounding(issue, ids_context=ids_context, bsdd_context=bsdd_context)
        metrics.grounding_ms = (time.perf_counter() - t0) * 1000

        # ----- Cache lookup -----
        signature: str | None = None
        if self.cache is not None and settings.suggestion_cache_enabled:
            t1 = time.perf_counter()
            signature = self._compute_signature(grounded, issue)
            cached = self.cache.get(signature)
            metrics.cache_lookup_ms = (time.perf_counter() - t1) * 1000
            if cached:
                metrics.cache_hit = True
                metrics.final_status = "cached"
                logger.debug("Cache HIT issue={} sig={}", issue.id, signature[:12])
                return SuggestionSet(
                    issue_id=issue.id,
                    suggestions=cached,
                    error=None,
                    prompt_hash=signature[:16],
                    metrics=metrics,
                )

        # ----- Selecionar prompt -----
        use_compact = self._should_use_compact(grounded, profile, rule)
        if use_compact:
            system, user = build_compact_prompt(grounded)
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

        # ----- Chamada LLM com retry seletivo (apenas para falha JSON/schema) -----
        last_exc: Exception | None = None
        current_user_prompt = user
        suggestions: list[Suggestion] = []
        ollama_metrics: dict = {}
        error: str | None = None

        for attempt in range(self._MAX_ATTEMPTS):
            try:
                t_llm = time.perf_counter()
                raw_result = self.client.generate(prompt=current_user_prompt, system=system)
                raw, ollama_metrics = _coerce_generate_result(raw_result)
                metrics.llm_total_ms += (time.perf_counter() - t_llm) * 1000

                t_parse = time.perf_counter()
                parsed = parse_llm_response(raw, issue.issue_type)
                metrics.parse_ms += (time.perf_counter() - t_parse) * 1000

                t_val = time.perf_counter()
                suggestions = self._validate_suggestions(
                    parsed,
                    issue,
                    bsdd_context=bsdd_context,
                    ids_context=ids_context,
                )
                if bsdd_context is not None:
                    suggestions = self._validate_against_bsdd(suggestions, bsdd_context, issue)
                # Aplicar review_required automático se o grounding está ausente
                if not grounded.has_official_candidates and grounded.is_grounded is False:
                    for s in suggestions:
                        s.review_required = True
                metrics.validation_ms += (time.perf_counter() - t_val) * 1000

                if suggestions:
                    error = None
                    break

                # JSON inválido / sem opções aproveitáveis: retry com instrução corretiva
                error = "Saida do LLM invalida ou fora do schema esperado"
                if attempt < self._MAX_ATTEMPTS - 1:
                    logger.debug(
                        "LLM rejeitado para issue {} (tentativa {}/{}). Raw: {!r}",
                        issue.id,
                        attempt + 1,
                        self._MAX_ATTEMPTS,
                        raw[:300],
                    )
                    current_user_prompt = self._build_retry_prompt(issue, user)
                    continue
                logger.warning(
                    "LLM vazio/invalido para issue {} apos {} tentativas",
                    issue.id,
                    self._MAX_ATTEMPTS,
                )
            except Exception as exc:
                last_exc = exc
                error = str(exc)
                logger.warning(
                    "Geracao LLM para issue {} falhou sem retry externo: {}",
                    issue.id,
                    exc,
                )
                break

        # ----- MÃƒÂ©tricas Ollama -----
        if ollama_metrics:
            metrics.ollama_load_ms = _ns_to_ms(ollama_metrics.get("load_duration", 0))
            metrics.ollama_prompt_eval_ms = _ns_to_ms(ollama_metrics.get("prompt_eval_duration", 0))
            metrics.ollama_eval_ms = _ns_to_ms(ollama_metrics.get("eval_duration", 0))
            metrics.prompt_tokens = int(ollama_metrics.get("prompt_eval_count", 0) or 0)
            metrics.output_tokens = int(ollama_metrics.get("eval_count", 0) or 0)

        # ----- Salvar no cache em sucesso -----
        if suggestions and self.cache is not None and signature is not None:
            try:
                self.cache.set(signature, suggestions, self._model_version, PROMPT_VERSION)
            except Exception as exc:
                logger.warning("Cache set falhou para issue {}: {}", issue.id, exc)

        if not suggestions and error is None:
            error = (
                f"Falha na geracao apos {self._MAX_ATTEMPTS} tentativas: {last_exc}"
                if last_exc
                else "Saida do LLM invalida"
            )

        metrics.final_status = "ready" if suggestions else "failed"

        return SuggestionSet(
            issue_id=issue.id,
            suggestions=suggestions,
            error=error,
            prompt_hash=prompt_hash,
            metrics=metrics,
        )


    def _should_use_compact(
        self,
        grounded: GroundedIssueContext,
        profile: ReadinessProfile | None,
        rule: OperationalRule | None,
    ) -> bool:
        """Compact prompt quando há grounding suficiente para issues estruturadas."""
        if not grounded.is_grounded:
            return False
        # PromptRouter customizado tem prioridade (paths legados/ específicos)
        if self.prompt_router is not None and (profile is not None or rule is not None):
            return False
        return True

    def _compute_signature(self, grounded: GroundedIssueContext, issue: Issue) -> str:
        """Calcula assinatura de cache para o par (issue, grounding).

        Inclui características específicas do elemento para evitar cache hits
        indevidos entre elementos com o mesmo tipo de issue mas conteúdo distinto
        (ex: espaços com móveis diferentes, portas de madeira vs vidro).
        """
        context_payload: dict[str, Any] = {
            "expected_value": grounded.expected_value,
            "current_value": grounded.current_value,
            "constraints": grounded.relevant_constraints,
            "aliases": grounded.controlled_aliases,
            "element_class": issue.element_class,
        }
        if not is_safe_to_reuse(issue):
            context_payload["element_guid"] = issue.element_guid

        if issue.issue_type == "space_unnamed":
            context_payload["elements_fp"] = _fingerprint_contained_elements(
                issue.context.get("contained_elements")
            )
            context_payload["adjacent_spaces_fp"] = _fingerprint_adjacent_spaces(
                issue.context.get("adjacent_spaces")
            )
            context_payload["area_bucket"] = _bucket_area(issue.context.get("area_m2"))
            context_payload["area_rounded"] = _rounded_measure(issue.context.get("area_m2"), 0.5)
            context_payload["height_rounded"] = _rounded_measure(issue.context.get("height_m"), 0.1)
            context_payload["perimeter_rounded"] = _rounded_measure(issue.context.get("perimeter_m"), 0.5)
            context_payload["is_on_exterior"] = issue.context.get("is_on_exterior")
            context_payload["floor"] = issue.context.get("floor")
            context_payload["text_hints_fp"] = _context_text_hints(issue)

        elif issue.issue_type == "pset_missing":
            context_payload["material_name"] = str(
                issue.context.get("material_name") or ""
            ).strip().casefold()
            context_payload["thickness_bucket"] = _bucket_thickness(
                issue.context.get("thickness_m")
            )
            context_payload["layers_fp"] = _fingerprint_material_layers(issue.context.get("layers"))
            context_payload["materials_fp"] = _fingerprint_material_layers(
                issue.context.get("materials")
            )
            context_payload["is_external"] = issue.context.get("is_external")
            context_payload["existing_psets_fp"] = _fingerprint_existing_psets(
                issue.context.get("existing_psets")
            )
            context_payload["elements_fp"] = _fingerprint_contained_elements(
                issue.context.get("contained_elements")
            )
            context_payload["adjacent_spaces_fp"] = _fingerprint_adjacent_spaces(
                issue.context.get("adjacent_spaces")
            )
            context_payload["area_rounded"] = _rounded_measure(issue.context.get("area_m2"), 0.5)
            context_payload["text_hints_fp"] = _context_text_hints(issue)

        elif issue.issue_type == "system_unclassified":
            context_payload["materials_fp"] = _fingerprint_material_layers(
                issue.context.get("materials")
            )
            context_payload["thickness_bucket"] = _bucket_thickness(
                issue.context.get("total_thickness")
            )
            context_payload["predefined_type"] = str(
                issue.context.get("predefined_type") or ""
            ).casefold()
            context_payload["element_name"] = str(issue.element_name or "").strip().casefold()

        elif issue.issue_type == "relation_broken":
            context_payload["element_name"] = str(issue.element_name or "").strip().casefold()

        return compute_cache_signature(
            model_version=self._model_version,
            prompt_version=PROMPT_VERSION,
            issue_type=grounded.issue_type,
            ifc_class=grounded.ifc_class,
            target_pset=grounded.canonical_pset,
            target_property=grounded.canonical_property,
            expected_type=grounded.expected_datatype,
            expected_unit=grounded.expected_unit,
            requirement_id=grounded.requirement_id,
            candidates=grounded.official_candidates,
            context_payload=context_payload,
        )

    # ------------------------------------------------------------------
    # Retry / batch / legacy paths
    # ------------------------------------------------------------------

    def _build_prompt_via_router(
        self,
        issue: Issue,
        building_context: dict,
        profile: ReadinessProfile | None,
        rule: OperationalRule | None,
    ) -> tuple[str, str]:
        """Usa o PromptRouter para selecionar template e montar contexto."""
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
                " Para FireRating, suggested_value deve ser rating como "
                '"REI 30","REI 60","EI 30","EI 60". Nunca null/N/A/nome da propriedade.'
            )
        elif issue.issue_type == "pset_missing" and check_property == "ThermalTransmittance":
            extra = " Para ThermalTransmittance, suggested_value deve ser numerico, sem unidade."

        return (
            f"{original_prompt}\n\nResposta anterior rejeitada. "
            'Retorne SOMENTE JSON {"opcoes":[{"suggested_value":...,"label":"...",'
            '"justification":"...","confidence":"alta"}]}.'
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
        reuse_map: dict[str, str] | None = None,
    ) -> list[SuggestionSet]:
        """Gera sugestões para várias issues sequencialmente.

        Se reuse_map for fornecido, issues secundárias copiam o resultado da
        primária ao invés de chamar o LLM.
        """
        total = len(issues)
        results: list[SuggestionSet] = []
        primary_results: dict[str, SuggestionSet] = {}
        reuse_map = reuse_map or {}

        for i, issue in enumerate(issues, start=1):
            primary_id = reuse_map.get(issue.id)
            if primary_id and primary_id in primary_results:
                primary_set = primary_results[primary_id]
                metrics = SuggestionMetrics(
                    issue_id=issue.id,
                    cache_hit=False,
                    reused_from_issue_id=primary_id,
                    final_status="reused",
                )
                result = SuggestionSet(
                    issue_id=issue.id,
                    suggestions=[s.model_copy() for s in primary_set.suggestions],
                    error=primary_set.error,
                    prompt_hash=primary_set.prompt_hash,
                    metrics=metrics,
                )
            else:
                result = self.generate(
                    issue,
                    building_context,
                    bsdd_context=bsdd_context_map.get(issue.id) if bsdd_context_map else None,
                    ids_context=ids_context_map.get(issue.id) if ids_context_map else None,
                    grounding_mode=grounding_mode,
                )
                primary_results[issue.id] = result

            results.append(result)
            if on_progress is not None:
                on_progress(i, total)

        return results

    # ------------------------------------------------------------------
    # Validação
    # ------------------------------------------------------------------

    def _format_building_context(self, building_context: dict) -> str:
        """Serializa building_context em texto simples."""
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
        """Valida e limpa sugestões geradas pelo LLM."""
        seen: set[str] = set()
        clean: list[Suggestion] = []

        for s in suggestions:
            # Rejeitar URI/bsdd_uri inventada pelo LLM (não aceitar do prompt compacto)
            s.bsdd_uri = None
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

        return sorted(clean, key=lambda s: s.confidence_order)[:3]

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
        """Rebaixa confiança e anota inconsistência com o bSDD."""
        suggestion.confidence = "baixa"
        marker = f"({note})"
        if marker not in suggestion.justification:
            suggestion.justification = f"{suggestion.justification} {marker}".strip()

    def _hash_prompt(self, system_prompt: str, user_prompt: str) -> str:
        """Gera hash estável do prompt final."""
        payload = f"{system_prompt}\n---\n{user_prompt}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]
