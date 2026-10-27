"""Agregação própria: cardinalidade da especificação, status e cobertura (plano §5.3).

O status agregado usa **todos** os estados e o inventário, nunca a união de passes do
backend nem o status de um subconjunto executado: violação conhecida domina, depois
erro, depois falta de verificação; só então a especificação é satisfeita.
"""

from collections.abc import Sequence
from typing import Literal

from src.translator.ids_document import SpecificationCardinality
from src.validation.diagnostic_models import (
    CoverageSummary,
    RequirementResult,
    SpecificationResult,
)

CardinalityEvaluation = Literal["satisfied", "violated", "not_evaluated"]
SpecStatus = Literal["satisfied", "violated", "not_verified", "error"]


def evaluate_cardinality(card: SpecificationCardinality, members: int) -> CardinalityEvaluation:
    """Cardinalidade suportada contra a população conhecida."""
    pair = (card.min_effective, card.max_effective)
    if pair == (1, "unbounded"):
        return "satisfied" if members >= 1 else "violated"
    if pair == (0, 0):
        return "satisfied" if members == 0 else "violated"
    return "satisfied"


def specification_status(
    cardinality: CardinalityEvaluation, rows: Sequence[RequirementResult], *, undetermined: bool
) -> SpecStatus:
    """Violação > erro > não verificado > satisfeito."""
    states = {row.state for row in rows}
    if cardinality == "violated" or "non_compliant" in states:
        return "violated"
    if "error" in states:
        return "error"
    if undetermined or "not_verified" in states:
        return "not_verified"
    return "satisfied"


def coverage_summary(
    specifications: Sequence[SpecificationResult],
    rows: Sequence[RequirementResult],
    declared_requirements: int,
    requirements_per_spec: Sequence[int],
) -> CoverageSummary:
    """Contagens separadas; pares conhecidos só quando toda população é conhecida."""
    undetermined = sum(1 for s in specifications if s.population_state == "undetermined")
    known_pairs = (
        None
        if undetermined
        else sum(
            (s.member_count or 0) * count
            for s, count in zip(specifications, requirements_per_spec, strict=True)
        )
    )
    with_element = [r for r in rows if r.element is not None]
    return CoverageSummary(
        specifications=len(specifications),
        declared_requirements=declared_requirements,
        undetermined_specifications=undetermined,
        known_pairs=known_pairs,
        evaluated_pairs=sum(1 for r in with_element if r.state in ("compliant", "non_compliant")),
        refused_pairs=sum(1 for r in with_element if r.state == "not_verified"),
        error_pairs=sum(1 for r in with_element if r.state == "error"),
        not_applicable_pairs=sum(1 for r in with_element if r.state == "not_applicable"),
        scope_rows=len(rows) - len(with_element),
    )
