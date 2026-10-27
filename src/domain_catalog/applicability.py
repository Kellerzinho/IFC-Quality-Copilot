"""Aplicabilidade cadastral declarativa (M1-05).

Avalia uma ``ApplicabilityRule`` em lógica de três valores: falta de classe, de
PredefinedType efetivo, de schema ou de fato do contexto produz ``indeterminate``,
nunca falso. O PredefinedType vem do M2 com origem ocorrência/tipo; só a ausência nos
dois níveis consultados exclui a regra que o exige, e leituras divergentes que levem a
estados diferentes ficam indeterminadas. Nenhuma expressão é executada: só os
operadores fechados do modelo. A aplicabilidade do catálogo orienta uso e receita; a
formal continua sendo a do IDS, avaliada pelo M2.
"""

from collections.abc import Iterable
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field

from src.domain_catalog.contracts import (
    ApplicabilityState,
    Facts,
    FrozenFacts,
    PredefinedTypeContext,
)
from src.domain_catalog.models import ApplicabilityRule, IfcSchemaId


class ApplicabilityContext(BaseModel):
    """O que se sabe do elemento; ausência de informação não é negação."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ifc_schema: IfcSchemaId | None = None
    entity: str | None = None
    predefined_type: PredefinedTypeContext | None = None
    facts: Facts = Field(default_factory=FrozenFacts)


class ApplicabilityResult(BaseModel):
    """Estado da aplicabilidade e motivos de exclusão ou indeterminação."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    state: ApplicabilityState
    reasons: tuple[str, ...] = ()


@lru_cache(maxsize=512)
def _entity_and_supertypes(schema: str, entity: str) -> frozenset[str] | None:
    """Nomes (maiúsculos) da classe e de seus supertipos no schema; ``None`` se desconhecida."""
    import ifcopenshell.ifcopenshell_wrapper as wrapper

    try:
        declaration = wrapper.schema_by_name(schema).declaration_by_name(entity)
    except RuntimeError:
        return None
    current = declaration.as_entity()
    if current is None:
        return None
    names: set[str] = set()
    while current is not None:
        names.add(current.name().upper())
        current = current.supertype()
    return frozenset(names)


def _entity_component(
    rule: ApplicabilityRule, context: ApplicabilityContext
) -> tuple[ApplicabilityState, str | None]:
    """Classe exata ou, se a regra declarar, subtipo segundo o schema do contexto."""
    if context.entity is None:
        return "indeterminate", "classe IFC não informada"
    wanted = {name.upper() for name in rule.entity_classes}
    if context.entity.upper() in wanted:
        return "applicable", None
    if not rule.include_subtypes:
        return "not_applicable", f"classe {context.entity} fora de {list(rule.entity_classes)}"
    if context.ifc_schema is None:
        return "indeterminate", "schema IFC necessário para avaliar subtipos"
    lineage = _entity_and_supertypes(context.ifc_schema, context.entity)
    if lineage is None:
        return "indeterminate", f"classe {context.entity} desconhecida em {context.ifc_schema}"
    if wanted & lineage:
        return "applicable", None
    return "not_applicable", f"classe {context.entity} não deriva de {list(rule.entity_classes)}"


def _predefined_component(
    rule: ApplicabilityRule, context: ApplicabilityContext
) -> tuple[ApplicabilityState, str | None]:
    """PredefinedType exigido pela regra, sobre o efetivo informado pelo M2, sem caixa.

    Leituras divergentes entre ocorrência e tipo associado só decidem quando todas levam
    ao mesmo estado; do contrário o resultado é indeterminado, sem escolher um lado.
    """
    if rule.predefined_types is None:
        return "applicable", None
    wanted = list(rule.predefined_types)
    predefined = context.predefined_type
    if predefined is None:
        return "indeterminate", "PredefinedType não informado"
    if predefined.status == "absent":
        return (
            "not_applicable",
            f"ocorrência e tipo associado consultados, sem PredefinedType; exigido {wanted}",
        )
    if predefined.status == "undetermined":
        return "indeterminate", f"PredefinedType efetivo indeterminado: {predefined.reason}"
    accepted = {reading.value.upper() in rule.predefined_types for reading in predefined.readings}
    if accepted == {True}:
        return "applicable", None
    if accepted == {False}:
        return (
            "not_applicable",
            f"PredefinedType {predefined.effective} ({predefined.effective_origin}) fora de "
            f"{wanted}",
        )
    readings = ", ".join(f"{r.origin}={r.value}" for r in predefined.readings)
    return (
        "indeterminate",
        f"PredefinedType divergente entre os níveis ({readings}); o catálogo não escolhe "
        "entre eles",
    )


def _condition_components(
    rule: ApplicabilityRule, context: ApplicabilityContext
) -> Iterable[tuple[ApplicabilityState, str | None]]:
    """Cada condição sobre fato do contexto; fato ausente é indeterminado."""
    for condition in rule.conditions:
        value = context.facts.get(condition.fact)
        if value is None:
            yield "indeterminate", f"fato {condition.fact} não informado"
            continue
        matched = value in condition.values
        satisfied = matched if condition.operator == "in" else not matched
        if satisfied:
            yield "applicable", None
        else:
            yield (
                "not_applicable",
                f"{condition.fact}={value} não atende {condition.operator} "
                f"{list(condition.values)}",
            )


def evaluate_applicability(
    rule: ApplicabilityRule, context: ApplicabilityContext
) -> ApplicabilityResult:
    """Combina classe, PredefinedType e condições: falso domina, depois indeterminado."""
    components = [
        _entity_component(rule, context),
        _predefined_component(rule, context),
        *_condition_components(rule, context),
    ]
    states = {state for state, _ in components}
    if "not_applicable" in states:
        state: ApplicabilityState = "not_applicable"
    elif "indeterminate" in states:
        state = "indeterminate"
    else:
        state = "applicable"
    reasons = tuple(reason for _, reason in components if reason is not None)
    return ApplicabilityResult(state=state, reasons=reasons)
