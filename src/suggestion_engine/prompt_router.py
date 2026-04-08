"""Roteador de prompts: seleciona template e monta contexto para o SuggestionGenerator."""

from typing import Any

from src.models import Issue, OperationalRule, ReadinessProfile
from src.suggestion_engine.prompt_templates import (
    PROFILE_TEMPLATES,
    SYSTEM_PROMPT,
    TEMPLATES,
    _format_elements,
    _format_material_layers,
    _format_spaces,
    _select_template,
)


class PromptRouter:
    """Seleciona o template de prompt correto baseado no perfil e tipo de issue."""

    def route(
        self,
        issue: Issue,
        profile: ReadinessProfile | None,
        rule: OperationalRule | None,
    ) -> tuple[str, str]:
        """Retorna (system_prompt, template_string) selecionando o melhor template.

        Prioridade:
        1. Se profile e issue_type existem em PROFILE_TEMPLATES → usar template do perfil
        2. Se rule.suggestion_strategy == "lookup_table" → usar template com tabela de lookup
        3. Se issue_type existe em TEMPLATES genérico → usar template genérico
        4. Fallback → template genérico de catch-all (pset_missing_generic)
        """
        # 1. Profile template
        if profile is not None:
            profile_template = PROFILE_TEMPLATES.get((profile.id, issue.issue_type))
            if profile_template is not None:
                return SYSTEM_PROMPT, profile_template

        # 2. lookup_table strategy → prefer the specific template for the issue
        if rule is not None and rule.suggestion_strategy == "lookup_table":
            template = _select_template(issue)
            return SYSTEM_PROMPT, template

        # 3. Generic template by issue_type
        template = TEMPLATES.get(issue.issue_type)
        if template is not None:
            return SYSTEM_PROMPT, template

        # 4. Fallback
        return SYSTEM_PROMPT, TEMPLATES["pset_missing_generic"]

    def build_context(
        self,
        issue: Issue,
        building_context: dict,
        profile: ReadinessProfile | None,
    ) -> dict[str, Any]:
        """Monta dict de contexto preenchendo todos os placeholders possíveis.

        Merge de: issue.context + building_context + dados do perfil.
        Substitui valores None por "não informado".
        """
        fill_ctx: dict[str, Any] = {
            **building_context,
            **issue.context,
            "guid": issue.element_guid[:8],
            "element_class": issue.element_class,
            "element_name": issue.element_name or "sem nome",
            "current_name": issue.element_name or "sem nome",
        }

        # Dados do perfil, se disponíveis
        if profile is not None:
            fill_ctx.setdefault("profile_id", profile.id)
            fill_ctx.setdefault("profile_name", profile.name)

        # Formatar listas para texto legível
        if "contained_elements" in fill_ctx:
            fill_ctx["contained_elements"] = _format_elements(fill_ctx["contained_elements"])
        if "adjacent_spaces" in fill_ctx:
            fill_ctx["adjacent_spaces"] = _format_spaces(fill_ctx["adjacent_spaces"])
        if "nearby_spaces" in fill_ctx:
            fill_ctx["nearby_spaces"] = _format_spaces(fill_ctx["nearby_spaces"])

        # system_unclassified: derivar material_layers e thickness_m
        if issue.issue_type == "system_unclassified":
            layers = fill_ctx.get("materials") or []
            fill_ctx["material_layers"] = _format_material_layers(layers)
            fill_ctx.setdefault("thickness_m", fill_ctx.get("total_thickness") or "N/D")

        # Substituir None por "não informado"
        return {k: "não informado" if v is None else v for k, v in fill_ctx.items()}
