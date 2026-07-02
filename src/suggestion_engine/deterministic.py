"""Pré-preenchimento determinístico para casos triviais (Fase A.3).

Para propriedades booleanas deriváveis diretamente do modelo IFC (lista fechada
e conservadora), gera sugestão pré-computada SEM chamar o LLM. A sugestão é
apresentada ao engenheiro como qualquer outra — **sempre com aprovação humana**,
nunca escrita automática — e carrega ``source="deterministic"`` para preservar a
proveniência na auditoria (AuditEntry.source).

Lista fechada atual (revisada com o orientador antes de ampliar):

- ``IsExternal`` — quando o analisador já computou a análise de fronteira
  (``is_external``/``is_on_exterior`` no contexto da issue).
- ``LoadBearing``/``IsLoadBearing`` — quando a classe IFC é estrutural por
  definição (IfcBeam, IfcColumn e variantes StandardCase).
"""

from __future__ import annotations

from loguru import logger

from src.models import Issue, Suggestion

_LOAD_BEARING_CLASSES: frozenset[str] = frozenset(
    {
        "IfcBeam",
        "IfcBeamStandardCase",
        "IfcColumn",
        "IfcColumnStandardCase",
    }
)

_BOOLEAN_TRUE = frozenset({"true", "sim", "yes", "1"})
_BOOLEAN_FALSE = frozenset({"false", "nao", "não", "no", "0"})


def _coerce_context_bool(value: object) -> bool | None:
    """Converte valor do contexto em bool estrito; None quando ambíguo."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in _BOOLEAN_TRUE:
            return True
        if normalized in _BOOLEAN_FALSE:
            return False
    return None


def _is_external_suggestion(issue: Issue) -> Suggestion | None:
    """Deriva IsExternal da análise de fronteira já computada pelo analyzer."""
    raw = issue.context.get("is_external")
    if raw is None:
        raw = issue.context.get("is_on_exterior")
    derived = _coerce_context_bool(raw)
    if derived is None:
        return None
    return Suggestion(
        label=str(derived),
        value=derived,
        justification=(
            "Derivado da análise de fronteira do modelo (elemento "
            f"{'em contato com o exterior' if derived else 'interno'}); sem LLM."
        ),
        confidence="alta",
        source="deterministic",
        semantic_hint="boundary_analysis",
    )


def _load_bearing_suggestion(issue: Issue) -> Suggestion | None:
    """Deriva LoadBearing=True para classes estruturais inequívocas (viga/pilar)."""
    if issue.element_class not in _LOAD_BEARING_CLASSES:
        return None
    return Suggestion(
        label="True",
        value=True,
        justification=(
            f"{issue.element_class} é elemento estrutural portante por definição "
            "(ISO 16739-1); sem LLM."
        ),
        confidence="alta",
        source="deterministic",
        semantic_hint="ifc_class_semantics",
    )


def generate_deterministic_suggestions(issue: Issue) -> list[Suggestion]:
    """Gera sugestões determinísticas para a issue, se ela estiver na lista fechada.

    Retorna lista vazia quando o caso não é trivialmente derivável — o fluxo
    normal (LLM com grounding) segue nesse caso. Nunca escreve no IFC: o
    resultado passa pela mesma revisão humana das sugestões de LLM.
    """
    if issue.issue_type != "pset_missing":
        return []

    check_property = str(issue.context.get("check_property") or "").strip()
    suggestion: Suggestion | None = None

    if check_property == "IsExternal":
        suggestion = _is_external_suggestion(issue)
    elif check_property in ("LoadBearing", "IsLoadBearing"):
        suggestion = _load_bearing_suggestion(issue)

    if suggestion is None:
        return []

    logger.debug(
        "Prefill deterministico para issue {} ({}={})",
        issue.id,
        check_property,
        suggestion.value,
    )
    return [suggestion]
