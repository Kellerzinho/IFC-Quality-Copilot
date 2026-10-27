"""Fronteira IDS/catálogo: anexo semântico depois da avaliação formal (plano §5.4).

``attach_catalog_annotations`` acrescenta ``SemanticAnnotation`` às linhas de
requisito ``property`` suportado com elemento conhecido: ``BindingRequest`` literal
(schema e classe reais, PredefinedType lido pelo M2, ``requirement_ref`` canônico) e a
``ResolutionResult`` do release aberto, ou a indisponibilidade do catálogo. Estado
formal, esperado e observado nunca mudam; resolução desconhecida, ambígua ou
indeterminada não cria falha IDS; catálogo inválido/indisponível vira problema
lateral, e o diagnóstico IDS suportado continua válido.
"""

from typing import Literal

from src.domain_catalog.contracts import (
    RESOLVED_STATUSES,
    BindingRequest,
    CatalogReleaseRef,
    ContractModel,
)
from src.domain_catalog.reader import CatalogReader
from src.ifc_analyzer.element_context import predefined_type_context
from src.validation.analysis_identity import CatalogState
from src.validation.diagnostic_models import (
    DiagnosticSnapshot,
    RequirementResult,
    SemanticAnnotation,
    TechnicalProblem,
)

__all__ = ["CatalogUnavailable", "attach_catalog_annotations", "predefined_type_context"]


class CatalogUnavailable(ContractModel):
    """Catálogo sem reader na execução: não anexado, inválido ou indisponível."""

    state: Literal["not_attached", "invalid", "unavailable"]
    reason: str | None = None
    catalog: CatalogReleaseRef | None = None


def _eligible(row: RequirementResult) -> bool:
    return row.element is not None and row.capability_cell.startswith("requirement:property:")


def attach_catalog_annotations(
    snapshot: DiagnosticSnapshot, reader_or_problem: CatalogReader | CatalogUnavailable
) -> DiagnosticSnapshot:
    """Snapshot com anexos semânticos; resultado formal intacto (conferido na cópia)."""
    expected_ref = snapshot.identity.catalog_ref
    problems = list(snapshot.problems)
    state: CatalogState
    if isinstance(reader_or_problem, CatalogUnavailable):
        state = reader_or_problem.state
        reader = None
        if state != "not_attached":
            problems.append(
                TechnicalProblem(
                    code=f"catalog_{state}",
                    message=reader_or_problem.reason or f"catálogo {state} na execução",
                )
            )
    else:
        reader = reader_or_problem
        if expected_ref is not None and reader.ref != expected_ref:
            raise ValueError("reader difere do release congelado na identidade da análise")
        state = "available"
    rows = []
    for row in snapshot.requirements:
        if not _eligible(row):
            rows.append(row)
            continue
        assert row.element is not None
        expected = snapshot.expected_for(row)
        assert expected.set_name is not None
        assert expected.field_name is not None
        context = snapshot.context_for(row.element)
        request = BindingRequest(
            ifc_schema=snapshot.ifc_schema,  # type: ignore[arg-type]
            facet="property",
            set_name=expected.set_name.text,
            field_name=expected.field_name.text or "",
            entity=row.element.ifc_class,
            predefined_type=context,
            requirement_ref=row.requirement.key(),
        )
        if reader is None:
            annotation = SemanticAnnotation(
                state="unavailable",
                request=request,
                predefined_type=context,
                catalog=expected_ref,
                error_reason=state,
                limitations=("catálogo sem reader nesta execução; diagnóstico IDS independente",),
            )
        else:
            resolution = reader.resolve_binding(request)
            annotation = SemanticAnnotation(
                state="resolved" if resolution.status in RESOLVED_STATUSES else "unresolved",
                request=request,
                predefined_type=context,
                resolution=resolution,
                catalog=reader.ref,
                limitations=(
                    *resolution.limitations,
                    "anexo semântico: não altera conformidade IDS nem autoriza escrita",
                ),
            )
        rows.append(
            RequirementResult.model_validate({**row.model_dump(), "annotation": annotation})
        )
    return snapshot.with_annotations(tuple(rows), state, tuple(problems))
