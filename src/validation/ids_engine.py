"""Motor IDS formal: inventário completo, gates, backend real e snapshot (plano §5.2–§5.4).

Ordem por especificação: schema IFC → cardinalidade → aplicabilidade → nome de classe
declarado no schema carregado (``unknown_entity_name``, sem ``Entity.filter``) →
consulta direta da classe sob captura (``entity_query_error``) → backend real só com
requisitos suportados. Gates por elemento (observações literais da mesma sessão):
fonte ambígua, portador não suportado, overlay herdado não verificável e unidade
explícita invalidam a célula mesmo que o backend a aprove. Requisitos fora da matriz
ficam ``not_verified`` sem afetar os demais. Aplicabilidade com PredefinedType
consulta o contexto M2 de todos os candidatos antes do backend: algum indeterminado
torna a população indeterminada. O modelo é conferido antes/depois:
mutação levanta ``source_mutated`` e não produz snapshot.
"""

import uuid
from collections.abc import Callable
from typing import Any

from src.domain_catalog.curation import utc_now
from src.ifc_analyzer.element_context import predefined_type_context
from src.ifc_analyzer.identity import ElementRef
from src.ifc_analyzer.observations import IfcObservationReader, SearchReport, build_search_plan
from src.ifc_analyzer.read_only import ReadOnlyIfcSession
from src.operations.contracts import new_uuid
from src.translator.ids_document import IDSDocument, IDSFacet, IDSSpecification
from src.validation.aggregation import coverage_summary, evaluate_cardinality, specification_status
from src.validation.analysis_identity import AnalysisIdentity
from src.validation.diagnostic_models import (
    DiagnosticSnapshot,
    ElementContext,
    ExpectedField,
    FormalState,
    RequirementRef,
    RequirementResult,
    SourceCheck,
    SpecificationResult,
    TechnicalProblem,
    snapshot_digest,
)
from src.validation.ids_constraints import (
    Support,
    classify_applicability,
    classify_cardinality,
    classify_requirement,
    classify_schema,
    entity_name,
    property_selector,
    requirement_cardinality,
)
from src.validation.ifctester_adapter import BackendError, SpecificationRun, run_specification
from src.validation.schema_bundle import SchemaBundle


class EngineError(Exception):
    """Execução recusada inteira: identidade divergente ou limite de resultado excedido."""

    code = "ids_engine_refused"

    def __init__(self, reason: str, message: str) -> None:
        """Guarda o motivo estável."""
        self.reason = reason
        super().__init__(f"[{reason}] {message}")


def expected_field(facet: IDSFacet) -> ExpectedField:
    """Exigência literal de uma faceta de requisito (independente de suporte)."""
    cardinality, origin = requirement_cardinality(facet)
    return ExpectedField(
        requirement=RequirementRef.model_validate(facet.location.model_dump()),
        facet_tag=facet.tag,
        set_name=facet.parameter("propertySet"),
        field_name=facet.parameter("baseName") or facet.parameter("name"),
        data_type=facet.attribute("dataType"),
        cardinality=cardinality,
        cardinality_origin=origin,  # type: ignore[arg-type]
        value=facet.parameter("value"),
        fragment=facet.fragment,
        fragment_sha256=facet.fragment_sha256,
    )


def _element_gate(report: SearchReport) -> str | None:
    """Motivo para recusar a célula do elemento, ou ``None`` se o backend pode decidir."""
    occurrence_sets = [s for s in report.matched_sets if s.scope == "occurrence"]
    type_sets = [s for s in report.matched_sets if s.scope == "type"]
    # Ausência só é inferida de busca completa: limite excedido ou erro de leitura
    # recusam a célula antes de qualquer aceite do backend (E3-01).
    for coverage in report.coverage:
        if coverage.status in ("unsupported", "error", "not_searched"):
            return coverage.reason or f"search_{coverage.status}"
    if any(c.status == "partial" for c in report.coverage):
        return "ambiguous_source"
    if len(occurrence_sets) > 1 or len(type_sets) > 1:
        return "ambiguous_source"
    if any(s.set_class != "IfcPropertySet" for s in report.matched_sets):
        return "unsupported_carrier"
    occurrence = [o for o in report.observations if o.origin == "occurrence"]
    typed = [o for o in report.observations if o.origin == "type"]
    if len(occurrence) > 1 or len(typed) > 1:
        return "ambiguous_source"
    if occurrence_sets and not occurrence and typed:
        return "unsupported_inherited_property_overlay"
    effective = occurrence[0] if occurrence else (typed[0] if typed else None)
    if effective is None:
        return None
    if effective.carrier_kind != "IfcPropertySingleValue":
        return "unsupported_carrier"
    if effective.unit is not None:
        return "unsupported_unit"
    return None


def _text_dependent(instance: Any) -> bool:
    """O backend leria ``ElementType``/``ObjectType`` (texto) para este elemento.

    Precedência do ``get_predefined_type`` do IfcOpenShell 0.8.5: o tipo associado vem
    primeiro; PredefinedType vazio ou ``USERDEFINED`` cai no ``ElementType``; um valor
    ordinário diferente de ``NOTDEFINED`` no tipo encerra a busca, e o ``ObjectType`` da
    ocorrência é ignorado (R-01). Só então a ocorrência é lida, com a mesma regra para
    ``ObjectType``. Vários tipos associados ficam indeterminados pelo contexto M2;
    aqui qualquer texto possível conta como dependência (conservador).
    """
    relations = list(getattr(instance, "IsTypedBy", None) or ())
    occurrence_text = getattr(instance, "PredefinedType", None) in (
        None,
        "",
        "USERDEFINED",
    ) and bool(getattr(instance, "ObjectType", None))
    if len(relations) > 1:
        return occurrence_text or any(_type_text(r.RelatingType) for r in relations)
    if relations:
        type_object = relations[0].RelatingType
        if _type_text(type_object):
            return True
        if getattr(type_object, "PredefinedType", None) not in (
            None,
            "",
            "USERDEFINED",
            "NOTDEFINED",
        ):
            return False
    return occurrence_text


def _type_text(type_object: Any) -> bool:
    """O tipo cairia no texto (PredefinedType vazio/USERDEFINED).

    Como no backend: ``ElementType`` quando o tipo o declara; senão ``ProcessType``
    (tipos de processo, ex.: ``IfcTaskType``).
    """
    if getattr(type_object, "PredefinedType", None) not in (None, "", "USERDEFINED"):
        return False
    text = (
        getattr(type_object, "ElementType", None)
        if hasattr(type_object, "ElementType")
        else getattr(type_object, "ProcessType", None)
    )
    return bool(text)


def _literal_predefined(spec: IDSSpecification) -> str | None:
    """PredefinedType literal da aplicabilidade (já classificada como suportada)."""
    value = spec.applicability[0].parameter("predefinedType")
    return None if value is None else value.text


class IdsEngine:
    """Avaliação formal sobre sessão IFC retida e IDS validado, para uma identidade exata."""

    def __init__(self, bundle: SchemaBundle | None = None) -> None:
        """Bundle oficial (carregado se omitido)."""
        self._bundle = bundle or SchemaBundle.load()

    def evaluate(
        self,
        session: ReadOnlyIfcSession,
        document: IDSDocument,
        identity: AnalysisIdentity,
        *,
        clock: Callable[[], str] = utc_now,
        snapshot_id: uuid.UUID | None = None,
    ) -> DiagnosticSnapshot:
        """Snapshot formal completo; mutação da fonte ou limite excedido não produz snapshot."""
        if session.source != identity.ifc or document.ids_sha256 != identity.ids.sha256:
            raise EngineError("identity_mismatch", "sessão ou IDS não são as fontes da identidade")
        state = _Evaluation(session, document, identity)
        for spec in document.specifications:
            state.specification(spec)
        session.verify_unchanged()
        data: dict[str, Any] = {
            "schema_version": 1,
            "snapshot_id": str(snapshot_id or new_uuid()),
            "created_at_utc": clock(),
            "identity": identity.model_dump(mode="json"),
            "ids_document": document.model_dump(mode="json"),
            "ifc_schema": session.schema,
            "expected_fields": [e.model_dump(mode="json") for e in state.expected],
            "specifications": [s.model_dump(mode="json") for s in state.specs],
            "requirements": [
                r.model_dump(mode="json")
                for r in sorted(state.rows, key=RequirementResult.sort_key)
            ],
            "search_reports": [r.model_dump(mode="json") for r in state.reports.values()],
            "element_contexts": [
                c.model_dump(mode="json")
                for c in sorted(state.contexts.values(), key=lambda c: c.element.express_id)
            ],
            "coverage": coverage_summary(
                state.specs,
                state.rows,
                sum(len(s.requirements) for s in document.specifications),
                [len(s.requirements) for s in document.specifications],
            ).model_dump(mode="json"),
            "problems": [p.model_dump(mode="json") for p in state.problems],
            "catalog_runtime_state": identity.catalog_state,
            "source_check": SourceCheck(
                ifc_sha256=session.source.sha256,
                ids_sha256=document.ids_sha256,
                signature_before=state.signature_before,
                signature_after=session.signature,
                entity_count=session.entity_count,
            ).model_dump(mode="json"),
        }
        return DiagnosticSnapshot.model_validate({**data, "content_sha256": snapshot_digest(data)})


class _Evaluation:
    """Acumulador de uma avaliação (linhas, especificações, relatórios e problemas)."""

    def __init__(
        self, session: ReadOnlyIfcSession, document: IDSDocument, identity: AnalysisIdentity
    ) -> None:
        self.session = session
        self.document = document
        self.identity = identity
        self.limits = identity.limits
        self.signature_before = session.signature
        self.reader = IfcObservationReader(
            session,
            identity.analysis_id,
            max_observations=identity.limits.max_observations_per_field,
        )
        self.expected: list[ExpectedField] = []
        self.rows: list[RequirementResult] = []
        self.specs: list[SpecificationResult] = []
        self.reports: dict[str, SearchReport] = {}
        self.contexts: dict[int, ElementContext] = {}
        self.problems: list[TechnicalProblem] = []

    def _row(self, row: RequirementResult) -> None:
        self.rows.append(row)
        if len(self.rows) > self.limits.max_result_rows:
            raise EngineError(
                "resource_limit_exceeded", f"resultado excede {self.limits.max_result_rows} linhas"
            )

    def _scope_rows(self, spec: IDSSpecification, state: str, reason: str, cell: str) -> None:
        for facet in spec.requirements:
            expected = expected_field(facet)
            self._row(
                RequirementResult(
                    analysis_id=self.identity.analysis_id,
                    requirement=expected.requirement,
                    expected_sha256=expected.digest(),
                    element=None,
                    state=state,  # type: ignore[arg-type]
                    reason=reason,
                    capability_cell=cell,
                )
            )

    def _problem(self, code: str, message: str, spec: IDSSpecification) -> None:
        self.problems.append(
            TechnicalProblem(code=code, message=message, specification_index=spec.index)
        )

    def _undetermined(
        self, spec: IDSSpecification, state: str, reason: str, cell: str, status: str
    ) -> None:
        self._scope_rows(spec, state, reason, cell)
        self.specs.append(
            SpecificationResult(
                analysis_id=self.identity.analysis_id,
                specification_index=spec.index,
                name=spec.name,
                identifier=spec.identifier,
                cardinality=spec.cardinality,
                population_state="undetermined",
                members=(),
                member_count=None,
                cardinality_evaluation="not_evaluated",
                status=status,  # type: ignore[arg-type]
                reasons=(reason,),
            )
        )

    def specification(self, spec: IDSSpecification) -> None:
        self.expected.extend(expected_field(facet) for facet in spec.requirements)
        for support in (
            classify_schema(self.session.schema, spec),
            classify_cardinality(spec.cardinality),
            classify_applicability(spec),
        ):
            if not support.supported:
                assert support.reason is not None
                if support.reason == "invalid_cardinality":
                    self._problem(
                        "invalid_cardinality", "maxOccurs finito menor que minOccurs", spec
                    )
                self._undetermined(
                    spec, "not_verified", support.reason, support.cell_id, "not_verified"
                )
                return
        name = entity_name(spec)
        declared = self._declared(name)
        if declared is None:
            self._problem("unknown_entity_name", f"{name} não existe no schema IFC4", spec)
            self._undetermined(
                spec, "not_verified", "unknown_entity_name", "applicability", "not_verified"
            )
            return
        if not self._is_occurrence(declared):
            # Tipos e demais não-IfcObject guardam propriedades por outro caminho
            # (HasPropertySets); fora da matriz inicial, nunca avaliados como ocorrência.
            self._undetermined(
                spec,
                "not_verified",
                "unsupported_applicability",
                "applicability",
                "not_verified",
            )
            return
        model = self.session.backend_model()
        try:
            candidates = {inst.id() for inst in model.by_type(declared, include_subtypes=False)}
        except Exception as exc:  # erro real da consulta de classe
            self._problem("entity_query_error", f"consulta de {declared} falhou: {exc}", spec)
            self._undetermined(spec, "error", "entity_query_error", "applicability", "error")
            return
        predefined = _literal_predefined(spec)
        expected_members: set[int] | None = None
        undetermined: set[int] = set()
        if predefined is not None:
            contexts = dict(self.contexts)
            try:
                expected_members, undetermined = self._predefined_population(candidates, predefined)
            except Exception as exc:  # falha local do pré-filtro M2: só esta especificação
                self.contexts = contexts
                self._problem("evaluation_error", f"contexto PredefinedType falhou: {exc}", spec)
                self._undetermined(spec, "error", "evaluation_error", "applicability", "error")
                return
            if undetermined and not expected_members:
                # Pertinência depende de USERDEFINED, ObjectType/ElementType ou tipos
                # múltiplos e nenhum membro é determinado: população indeterminada (E3-02).
                self._undetermined(
                    spec,
                    "not_verified",
                    "undetermined_predefined_type",
                    "applicability",
                    "not_verified",
                )
                return
        supports = [classify_requirement(facet) for facet in spec.requirements]
        supported = [f for f, s in zip(spec.requirements, supports, strict=True) if s.supported]
        try:
            run = run_specification(model, self.document, spec, supported)
            population = {inst.id() for inst in run.population}
            if not population <= candidates:
                raise BackendError("backend_inconsistency", "população fora da classe consultada")
            if expected_members is not None and population - undetermined != expected_members:
                raise BackendError(
                    "backend_inconsistency", "população diverge do PredefinedType efetivo do M2"
                )
        except BackendError as exc:
            self._problem(exc.reason, str(exc), spec)
            self._undetermined(spec, "error", exc.reason, "backend", "error")
            return
        except Exception as exc:  # exceção real da avaliação: erro correlacionado
            self._problem("evaluation_error", f"backend falhou: {exc}", spec)
            self._undetermined(spec, "error", "evaluation_error", "backend", "error")
            return
        rows, specs = len(self.rows), len(self.specs)
        reports, contexts = dict(self.reports), dict(self.contexts)
        try:
            self._known(spec, run, supports, undetermined)
        except EngineError:
            raise
        except Exception as exc:  # falha local (leitura M2): só esta especificação vira erro
            del self.rows[rows:], self.specs[specs:]
            self.reports, self.contexts = reports, contexts
            self._problem("evaluation_error", f"avaliação local falhou: {exc}", spec)
            self._undetermined(spec, "error", "evaluation_error", "evaluation", "error")

    def _predefined_population(
        self, candidates: set[int], literal: str
    ) -> tuple[set[int], set[int]]:
        """Membros determinados cujo PredefinedType efetivo é ``literal`` e indeterminados.

        Todos os candidatos da classe são consultados antes do filtro do backend. É
        indeterminado o candidato que o M2 não determina ou cuja pertinência no backend
        dependeria de texto ``ObjectType``/``ElementType`` (M-01); seus contextos ficam
        no snapshot para auditoria.
        """
        members: set[int] = set()
        undetermined: set[int] = set()
        for express_id in sorted(candidates):
            instance = self.session.by_express_id(express_id)
            element = self.session.element_ref(instance)
            context = predefined_type_context(self.session, element)
            if context.status == "undetermined" or _text_dependent(instance):
                undetermined.add(express_id)
                self.contexts.setdefault(
                    express_id, ElementContext(element=element, predefined_type=context)
                )
            elif context.status == "determined":
                effective = next(
                    r.value for r in context.readings if r.origin == context.effective_origin
                )
                if effective == literal:
                    members.add(express_id)
        return members, undetermined

    @staticmethod
    def _is_occurrence(name: str) -> bool:
        """A classe declarada é subtipo de ``IfcObject`` (ocorrência com IsDefinedBy)."""
        import ifcopenshell.ifcopenshell_wrapper as wrapper

        entity = wrapper.schema_by_name("IFC4").declaration_by_name(name).as_entity()
        while entity is not None:
            if entity.name() == "IfcObject":
                return True
            entity = entity.supertype()
        return False

    @staticmethod
    def _declared(name: str) -> str | None:
        import ifcopenshell.ifcopenshell_wrapper as wrapper

        try:
            declaration = wrapper.schema_by_name("IFC4").declaration_by_name(name)
        except RuntimeError:
            return None
        entity = declaration.as_entity()
        return None if entity is None else str(entity.name())

    def _known(
        self,
        spec: IDSSpecification,
        run: SpecificationRun,
        supports: list[Support],
        undetermined: set[int] = frozenset(),  # type: ignore[assignment]
    ) -> None:
        members = sorted(
            (
                self.session.element_ref(inst)
                for inst in run.population
                if inst.id() not in undetermined
            ),
            key=lambda e: e.express_id,
        )
        for member in members:
            if member.express_id not in self.contexts:
                self.contexts[member.express_id] = ElementContext(
                    element=member, predefined_type=predefined_type_context(self.session, member)
                )
        before = len(self.rows)
        if undetermined:
            # Parte da população é indeterminada (M-02): linha de escopo não verificada e
            # resultados seguros dos membros determinados; cardinalidade não avaliada.
            self._scope_rows(spec, "not_verified", "undetermined_predefined_type", "applicability")
        if not members:
            if not undetermined:
                self._scope_rows(spec, "not_applicable", "no_applicable_elements", "population")
        elif not run.requirements_evaluated:
            for facet in spec.requirements:
                for member in members:
                    self._element_row(
                        facet, member, "not_applicable", "prohibited_specification", "population"
                    )
        else:
            for facet, support in zip(spec.requirements, supports, strict=True):
                for member in members:
                    if not support.supported:
                        assert support.reason is not None
                        self._element_row(
                            facet, member, "not_verified", support.reason, support.cell_id
                        )
                    else:
                        self._evaluated_row(facet, member, run, support)
        if undetermined:
            self.specs.append(
                SpecificationResult(
                    analysis_id=self.identity.analysis_id,
                    specification_index=spec.index,
                    name=spec.name,
                    identifier=spec.identifier,
                    cardinality=spec.cardinality,
                    population_state="undetermined",
                    members=(),
                    member_count=None,
                    cardinality_evaluation="not_evaluated",
                    status=specification_status(
                        "not_evaluated", self.rows[before:], undetermined=True
                    ),
                    reasons=("undetermined_predefined_type",),
                )
            )
            return
        cardinality = evaluate_cardinality(spec.cardinality, len(members))
        self.specs.append(
            SpecificationResult(
                analysis_id=self.identity.analysis_id,
                specification_index=spec.index,
                name=spec.name,
                identifier=spec.identifier,
                cardinality=spec.cardinality,
                population_state="known",
                members=tuple(members),
                member_count=len(members),
                cardinality_evaluation=cardinality,
                status=specification_status(cardinality, self.rows[before:], undetermined=False),
            )
        )

    def _element_row(
        self, facet: IDSFacet, member: ElementRef, state: str, reason: str, cell: str, **extra: Any
    ) -> None:
        expected = expected_field(facet)
        self._row(
            RequirementResult(
                analysis_id=self.identity.analysis_id,
                requirement=expected.requirement,
                expected_sha256=expected.digest(),
                element=member,
                state=state,  # type: ignore[arg-type]
                reason=reason,
                capability_cell=cell,
                **extra,
            )
        )

    def _evaluated_row(
        self, facet: IDSFacet, member: ElementRef, run: SpecificationRun, support: Support
    ) -> None:
        pset, name = property_selector(facet)
        plan = build_search_plan(
            self.identity.analysis_id,
            member,
            [(pset, name, f"ids:{facet.location.key()}")],
            ("occurrence", "type"),
            max_selectors=self.limits.max_selectors_per_field,
        )
        report = self.reader.read(plan)
        self.reports.setdefault(report.report_sha256, report)
        outcome = run.outcomes[facet.location.index][member.express_id]
        gate = _element_gate(report)
        state: FormalState
        if outcome.error is not None:
            # Erro localizado desta faceta/elemento; as demais células seguem (E3-10).
            self.problems.append(
                TechnicalProblem(
                    code="evaluation_error",
                    message=f"faceta falhou: {outcome.error}",
                    specification_index=facet.location.specification_index,
                    location_key=facet.location.key(),
                    element=member,
                )
            )
            expected = expected_field(facet)
            self._row(
                RequirementResult(
                    analysis_id=self.identity.analysis_id,
                    requirement=expected.requirement,
                    expected_sha256=expected.digest(),
                    element=member,
                    state="error",
                    reason="evaluation_error",
                    capability_cell=support.cell_id,
                    search_report_sha256=report.report_sha256,
                    observation_ids=tuple(o.observation_id for o in report.observations),
                )
            )
            return
        if gate is not None:
            state, reason = "not_verified", gate
        elif outcome.passed:
            state, reason = "compliant", None
        else:
            state, reason = "non_compliant", "requirement_violated"
        expected = expected_field(facet)
        self._row(
            RequirementResult(
                analysis_id=self.identity.analysis_id,
                requirement=expected.requirement,
                expected_sha256=expected.digest(),
                element=member,
                state=state,
                reason=reason,
                capability_cell=support.cell_id,
                backend_passed=outcome.passed,
                backend_detail=outcome.detail,
                search_report_sha256=report.report_sha256,
                observation_ids=tuple(o.observation_id for o in report.observations),
            )
        )
