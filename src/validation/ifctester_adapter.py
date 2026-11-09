"""Adaptador restrito do IfcTester 0.8.5 (backend formal fixado; plano §5.1).

Para cada especificação suportada monta um ``Ids`` **novo** com a aplicabilidade
integral e somente os requisitos suportados, a partir do documento já decodificado
pelo bundle oficial; nunca usa ``ids.open``/``from_string``/``get_schema`` padrão nem
altera globais da biblioteca. ``Ids.parse`` agrupa facetas por tag: cada faceta é
correlacionada ao original por (tag, ocorrência) e conferida (seletores e
cardinalidade) antes da avaliação. O resultado é lido por **faceta e elemento**
(``passed_entities``/``failures`` de objetos novos), nunca por
``Specification.passed_entities``, que une sucessos parciais. Exceção de uma faceta
de requisito num elemento é capturada só para essa célula (``FacetOutcome.error``);
as demais facetas e a população seguem do mesmo backend. Os caches
``get_pset``/``get_psets`` são da biblioteca: um lock de processo serializa cada
validação completa.
"""

import threading
from dataclasses import dataclass, field
from typing import Any, Final

from src.operations.contracts import canonical_sha256
from src.translator.ids_document import IDSDocument, IDSFacet, IDSSpecification
from src.validation.ids_constraints import property_selector, requirement_cardinality

BACKEND_OPTIONS: Final = {
    "backend": "ifctester",
    "should_filter_version": True,
    "strip_namespaces": True,
    "fresh_ids_per_specification": True,
    "requirements": "supported_subset_correlated_by_tag_occurrence",
    "result_source": "per_facet_per_element",
    "cache_policy": "clear_before_and_after_under_process_lock",
    "facet_exceptions": "isolated_per_requirement_facet_and_element",
}
BACKEND_OPTIONS_SHA256: Final = canonical_sha256(BACKEND_OPTIONS)

_BACKEND_LOCK: Final = threading.Lock()


class BackendError(Exception):
    """Execução do backend falhou ou divergiu do documento; nada é aproveitado."""

    code = "ids_backend_error"

    def __init__(self, reason: str, message: str) -> None:
        """Guarda o motivo estável (``evaluation_error`` ou ``backend_inconsistency``)."""
        self.reason = reason
        super().__init__(f"[{reason}] {message}")


@dataclass(frozen=True)
class FacetOutcome:
    """Resultado do backend para uma faceta e um elemento (``error``: exceção da faceta)."""

    passed: bool
    detail: str | None
    error: str | None = None


class _FacetFailure:
    """Resultado falso devolvido ao IfcTester quando a faceta levanta exceção."""

    def __bool__(self) -> bool:
        return False

    def __str__(self) -> str:
        return "evaluation_error"


def _guard(facet: Any, position: int, errors: dict[tuple[int, int], str]) -> None:
    """Troca a classe do objeto novo por subclasse que isola exceções por elemento."""
    base = type(facet)

    def call(self: Any, inst: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return base.__call__(self, inst, *args, **kwargs)
        except Exception as exc:  # erro real da faceta neste elemento
            errors[(position, inst.id())] = f"{type(exc).__name__}: {exc}"
            return _FacetFailure()

    facet.__class__ = type(f"Guarded{base.__name__}", (base,), {"__call__": call})


@dataclass
class SpecificationRun:
    """População do backend e resultados por requisito original e express ID."""

    population: list[Any]
    outcomes: dict[int, dict[int, FacetOutcome]] = field(default_factory=dict)
    requirements_evaluated: bool = True


def _decoded_specification(
    document: IDSDocument, index: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    decoded = document.decoded()
    specs = decoded["specifications"]["specification"]
    specs = specs if isinstance(specs, list) else [specs]
    return decoded["info"], specs[index]


def _literal(value: Any) -> Any:
    return value.get("simpleValue") if isinstance(value, dict) else value


def run_specification(
    model: Any,
    document: IDSDocument,
    spec: IDSSpecification,
    supported: list[IDSFacet],
) -> SpecificationRun:
    """Avalia uma especificação suportada com objetos novos e devolve resultados por faceta."""
    from ifctester.facet import (  # type: ignore[import-untyped,import-not-found,unused-ignore]
        get_pset,
        get_psets,
    )
    from ifctester.ids import Ids  # type: ignore[import-untyped,import-not-found,unused-ignore]

    info, original = _decoded_specification(document, spec.index)
    properties = (original.get("requirements") or {}).get("property", [])
    properties = properties if isinstance(properties, list) else [properties]
    try:
        selected = [properties[facet.occurrence_index] for facet in supported]
    except IndexError as exc:
        raise BackendError("backend_inconsistency", "faceta original sem correspondente") from exc
    subset = {key: value for key, value in original.items() if key != "requirements"}
    if selected:
        subset["requirements"] = {"property": selected}
    ids = Ids()
    ids.parse({"info": info, "specifications": {"specification": [subset]}})
    (parsed,) = ids.specifications
    if len(parsed.requirements) != len(supported):
        raise BackendError("backend_inconsistency", "contagem de requisitos divergente")
    for facet, source in zip(parsed.requirements, supported, strict=True):
        pset, name = property_selector(source)
        cardinality, _ = requirement_cardinality(source)
        if (facet.propertySet, facet.baseName, facet.cardinality) != (pset, name, cardinality):
            raise BackendError("backend_inconsistency", "correlação de faceta divergente")
    errors: dict[tuple[int, int], str] = {}
    for position, facet in enumerate(parsed.requirements):
        _guard(facet, position, errors)
    with _BACKEND_LOCK:
        get_pset.cache_clear()
        get_psets.cache_clear()
        try:
            ids.validate(model, should_filter_version=True)
        finally:
            get_pset.cache_clear()
            get_psets.cache_clear()
    if parsed.is_ifc_version is not True:
        raise BackendError("backend_inconsistency", "backend recusou a versão IFC conferida")
    run = SpecificationRun(population=list(parsed.applicable_entities))
    run.requirements_evaluated = parsed.maxOccurs != 0
    if not run.requirements_evaluated:
        return run
    for position, (facet, source) in enumerate(zip(parsed.requirements, supported, strict=True)):
        failed = {failure["element"].id(): failure["reason"] for failure in facet.failures}
        passed = {element.id() for element in facet.passed_entities}
        outcomes: dict[int, FacetOutcome] = {}
        for element in run.population:
            express = element.id()
            if (express in passed) == (express in failed):
                raise BackendError("backend_inconsistency", f"#{express} sem resultado único")
            error = errors.get((position, express))
            if error is not None and express in passed:
                raise BackendError("backend_inconsistency", f"#{express} com erro e aprovação")
            outcomes[express] = FacetOutcome(express in passed, failed.get(express), error)
        run.outcomes[source.location.index] = outcomes
    return run
