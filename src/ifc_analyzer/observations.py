"""Observações literais de propriedades IFC (M2, plano §6).

``EvidenceObservation`` é o único nome de observação. Seu ID é o SHA-256 do payload
canônico; não há como aceitar objeto arbitrário com ID copiado. A leitura segue um
``SearchPlan`` fechado (conjunto e campo literais, escopos ocorrência/tipo), na
mesma sessão e análise: elemento de outra fonte ou plano de outra análise é recusado.
Ausência é conclusão de busca completa sem portador correspondente; nenhum valor é
inventado para campo ausente. Duplicatas, portadores fora do suporte e múltiplos
tipos são observados com estado/limite, nunca descartados para parecer ausência.
O limite de observações vale por seletor/escopo e também para o total do plano (um
campo): excedido, a cobertura vira ``unsupported/context_limit_exceeded`` sem truncar.
``False``, ``0``, ``''`` e nulo são distintos; o valor bruto é o valor decodificado
pelo IfcOpenShell (não o token STEP original).
"""

import uuid
from collections.abc import Iterable
from typing import Annotated, Any, Final, Literal, Protocol, Self

from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator

from src.domain_catalog.contracts import ContractModel
from src.domain_catalog.models import NonEmptyText, Sha256Hex
from src.ifc_analyzer.identity import ElementRef
from src.ifc_analyzer.read_only import IfcSourceError, ReadOnlyIfcSession
from src.operations.contracts import CanonicalUUID, SchemaVersionOne, canonical_sha256

METHOD: Final = "ifcopenshell-literal-read"
METHOD_VERSION: Final = "1.0.0"
TEXT_TYPES: Final = frozenset({"IfcLabel", "IfcText", "IfcIdentifier"})

ScopeName = Literal["occurrence", "type"]
SCOPES: Final[tuple[ScopeName, ...]] = ("occurrence", "type")
ObservationState = Literal["present", "null", "empty", "invalid", "unsupported", "error"]
UnitState = Literal["not_applicable", "known", "unknown", "conflicting"]
CoverageStatus = Literal["complete", "partial", "not_searched", "unsupported", "error"]


class TextValue(ContractModel):
    """Texto exato (inclusive vazio)."""

    tag: Literal["string"] = "string"
    value: StrictStr


class BooleanValue(ContractModel):
    """Booleano estrito; ``False`` é valor."""

    tag: Literal["boolean"] = "boolean"
    value: StrictBool


class IntegerValue(ContractModel):
    """Inteiro estrito; ``0`` é valor."""

    tag: Literal["integer"] = "integer"
    value: StrictInt


TypedValue = Annotated[TextValue | BooleanValue | IntegerValue, Field(discriminator="tag")]
"""União estrita texto/booleano/inteiro, sem coerção; demais tipos são ``unsupported``."""


class ObservationRefused(Exception):
    """Plano ou leitura recusados: referência estrangeira ou limite de contexto."""

    code = "observation_refused"

    def __init__(
        self, reason: Literal["foreign_reference", "context_limit_exceeded"], message: str
    ):
        """Guarda o motivo estável."""
        self.reason = reason
        super().__init__(f"[{reason}] {message}")


class LiteralFieldSelector(ContractModel):
    """Portador propriedade, conjunto e campo literais, com todas as razões de busca."""

    carrier: Literal["property"] = "property"
    set_name: NonEmptyText
    field_name: NonEmptyText
    reasons: tuple[NonEmptyText, ...] = Field(min_length=1)


class SearchPlan(ContractModel):
    """Busca fechada para um elemento de uma análise; sem código, caminho livre ou fuzzy."""

    analysis_id: CanonicalUUID
    element: ElementRef
    selectors: tuple[LiteralFieldSelector, ...] = Field(min_length=1)
    admitted_scopes: tuple[ScopeName, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _ordered_unique(self) -> Self:
        """Seletores únicos e ordenados por chave literal; escopos na ordem fixa."""
        keys = [(s.set_name, s.field_name) for s in self.selectors]
        if keys != sorted(set(keys)):
            raise ValueError("seletores precisam ser únicos e ordenados")
        if list(self.admitted_scopes) != [s for s in SCOPES if s in self.admitted_scopes]:
            raise ValueError("escopos precisam ser únicos e na ordem ocorrência, tipo")
        return self


def build_search_plan(
    analysis_id: uuid.UUID,
    element: ElementRef,
    selectors: Iterable[tuple[str, str, str]],
    admitted_scopes: Iterable[ScopeName],
    *,
    max_selectors: int = 64,
) -> SearchPlan:
    """Ordena e deduplica seletores por chave literal, unindo as razões; limite recusa."""
    merged: dict[tuple[str, str], set[str]] = {}
    for set_name, field_name, reason in selectors:
        merged.setdefault((set_name, field_name), set()).add(reason)
    if len(merged) > max_selectors:
        raise ObservationRefused(
            "context_limit_exceeded", f"{len(merged)} seletores excedem o limite {max_selectors}"
        )
    scopes = set(admitted_scopes)
    return SearchPlan(
        analysis_id=analysis_id,
        element=element,
        selectors=tuple(
            LiteralFieldSelector(set_name=key[0], field_name=key[1], reasons=tuple(sorted(reasons)))
            for key, reasons in sorted(merged.items())
        ),
        admitted_scopes=tuple(s for s in SCOPES if s in scopes),
    )


JsonValue = Any


class EvidenceObservation(ContractModel):
    """Leitura literal de um membro de conjunto, com dono real, origem e estado."""

    schema_version: SchemaVersionOne = 1
    observation_id: Sha256Hex
    analysis_id: CanonicalUUID
    source_sha256: Sha256Hex
    element: ElementRef
    owner: ElementRef
    origin: ScopeName
    type_relation_express_id: StrictInt | None
    set_express_id: StrictInt
    set_class: NonEmptyText
    set_name: NonEmptyText
    member_express_id: StrictInt
    field_name: NonEmptyText
    carrier_kind: NonEmptyText
    state: ObservationState
    raw_value: JsonValue
    raw_representation: Literal["decoded_ifc_value"] = "decoded_ifc_value"
    typed_value: TypedValue | None
    ifc_type: str | None
    unit_state: UnitState
    unit: str | None
    method: Literal["ifcopenshell-literal-read"] = METHOD
    method_version: Literal["1.0.0"] = METHOD_VERSION
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _content_addressed(self) -> Self:
        """O ID é o hash do conteúdo; elemento e fonte coerentes."""
        if self.observation_id != observation_digest(self.model_dump(mode="json")):
            raise ValueError("observation_id não corresponde ao conteúdo")
        if self.element.sha256 != self.source_sha256 or self.owner.sha256 != self.source_sha256:
            raise ValueError("observação de outra fonte")
        if self.state == "present" and self.typed_value is None:
            raise ValueError("estado present exige valor tipado")
        return self


def observation_digest(document: dict[str, Any]) -> str:
    """Hash canônico do payload sem o próprio ID."""
    return canonical_sha256({k: v for k, v in document.items() if k != "observation_id"})


class SelectorCoverage(ContractModel):
    """Cobertura de um seletor num escopo."""

    set_name: NonEmptyText
    field_name: NonEmptyText
    scope: ScopeName
    status: CoverageStatus
    reason: str | None = None


class MatchedSet(ContractModel):
    """Conjunto com o nome do seletor encontrado num escopo, com ou sem o campo."""

    set_name: NonEmptyText
    field_name: NonEmptyText
    scope: ScopeName
    owner_express_id: StrictInt
    set_express_id: StrictInt
    set_class: NonEmptyText


class SearchReport(ContractModel):
    """Plano, observações ordenadas, conjuntos encontrados, cobertura e hash do relatório."""

    schema_version: SchemaVersionOne = 1
    plan: SearchPlan
    plan_sha256: Sha256Hex
    observations: tuple[EvidenceObservation, ...]
    matched_sets: tuple[MatchedSet, ...] = ()
    coverage: tuple[SelectorCoverage, ...]
    problems: tuple[str, ...] = ()
    report_sha256: Sha256Hex

    @model_validator(mode="after")
    def _hashes(self) -> Self:
        """Hashes do plano e do relatório conferem com o conteúdo."""
        if self.plan_sha256 != canonical_sha256(self.plan.model_dump(mode="json")):
            raise ValueError("plan_sha256 não corresponde ao plano")
        body = self.model_dump(mode="json", exclude={"report_sha256"})
        if self.report_sha256 != canonical_sha256(body):
            raise ValueError("report_sha256 não corresponde ao relatório")
        return self

    def status(self, set_name: str, field_name: str, scope: ScopeName) -> CoverageStatus:
        """Estado de cobertura de um seletor/escopo."""
        return next(
            c.status
            for c in self.coverage
            if (c.set_name, c.field_name, c.scope) == (set_name, field_name, scope)
        )


class ObservationReader(Protocol):
    """Leitor de observações de uma sessão e análise."""

    def read(self, plan: SearchPlan) -> SearchReport:
        """Executa o plano e devolve o relatório."""
        ...


def _decimal_text(value: float) -> str:
    return repr(float(value))


def _members(definition: Any) -> tuple[str, tuple[Any, ...]]:
    if definition.is_a("IfcPropertySet"):
        return "IfcPropertySet", tuple(definition.HasProperties or ())
    if definition.is_a("IfcElementQuantity"):
        return "IfcElementQuantity", tuple(definition.Quantities or ())
    return definition.is_a(), ()


class IfcObservationReader:
    """Leitura literal na sessão retida, presa a uma análise."""

    def __init__(
        self, session: ReadOnlyIfcSession, analysis_id: uuid.UUID, *, max_observations: int = 512
    ) -> None:
        """Sessão e análise donas das observações."""
        self._session = session
        self._analysis_id = analysis_id
        self._max_observations = max_observations

    def _definitions(self, owner: Any, origin: ScopeName) -> list[Any]:
        if origin == "type":
            return list(owner.HasPropertySets or ())
        found: list[Any] = []
        for rel in owner.IsDefinedBy or ():
            if rel.is_a("IfcRelDefinesByProperties"):
                definition = rel.RelatingPropertyDefinition
                found.extend(definition if isinstance(definition, tuple) else (definition,))
        return found

    def _observe(
        self,
        plan: SearchPlan,
        owner: Any,
        origin: ScopeName,
        relation: Any,
        definition: Any,
        member: Any,
    ) -> EvidenceObservation:
        set_class, _ = _members(definition)
        carrier = member.is_a()
        state: ObservationState = "unsupported"
        typed: TextValue | BooleanValue | IntegerValue | None = None
        raw: Any = {"carrier": carrier}
        ifc_type: str | None = None
        unit_state: UnitState = "unknown"
        unit: str | None = None
        limitations: list[str] = []
        if carrier == "IfcPropertySingleValue":
            nominal = member.NominalValue
            explicit_unit = member.Unit
            if explicit_unit is not None:
                unit_state = "known"
                unit = str(getattr(explicit_unit, "Name", None) or explicit_unit.is_a())
            if nominal is None:
                state, raw = "null", None
                unit_state = "not_applicable" if explicit_unit is None else unit_state
            else:
                ifc_type = nominal.is_a()
                value = nominal.wrappedValue
                if ifc_type in TEXT_TYPES and isinstance(value, str):
                    typed, raw = TextValue(value=value), value
                    state = "empty" if value == "" else "present"
                elif ifc_type == "IfcBoolean" and isinstance(value, bool):
                    typed, raw, state = BooleanValue(value=value), value, "present"
                elif (
                    ifc_type == "IfcInteger"
                    and isinstance(value, int)
                    and not isinstance(value, bool)
                ):
                    typed, raw, state = IntegerValue(value=value), value, "present"
                elif isinstance(value, float):
                    raw = {"ifc_type": ifc_type, "decimal": _decimal_text(value)}
                    limitations.append("valor decimal/medida fora do suporte desta condição")
                else:
                    raw = {"ifc_type": ifc_type, "text": str(value)}
                    limitations.append(f"tipo {ifc_type} fora do suporte desta condição")
                if typed is not None and explicit_unit is None:
                    unit_state = "not_applicable"
        else:
            limitations.append(f"portador {carrier} fora do suporte desta condição")
        document = {
            "schema_version": 1,
            "analysis_id": str(self._analysis_id),
            "source_sha256": self._session.source.sha256,
            "element": plan.element.model_dump(mode="json"),
            "owner": self._session.element_ref(owner).model_dump(mode="json"),
            "origin": origin,
            "type_relation_express_id": None if relation is None else relation.id(),
            "set_express_id": definition.id(),
            "set_class": set_class,
            "set_name": definition.Name,
            "member_express_id": member.id(),
            "field_name": member.Name,
            "carrier_kind": carrier,
            "state": state,
            "raw_value": raw,
            "raw_representation": "decoded_ifc_value",
            "typed_value": None if typed is None else typed.model_dump(mode="json"),
            "ifc_type": ifc_type,
            "unit_state": unit_state,
            "unit": unit,
            "method": METHOD,
            "method_version": METHOD_VERSION,
            "limitations": limitations,
        }
        return EvidenceObservation.model_validate(
            {**document, "observation_id": observation_digest(document)}
        )

    def read(self, plan: SearchPlan) -> SearchReport:
        """Executa a busca literal; plano estrangeiro é ``ObservationRefused``."""
        if plan.analysis_id != self._analysis_id:
            raise ObservationRefused("foreign_reference", "plano de outra análise")
        if not self._session.owns(plan.element):
            raise ObservationRefused("foreign_reference", "elemento de outra fonte ou revisão")
        try:
            instance = self._session.by_express_id(plan.element.express_id)
        except IfcSourceError as exc:
            raise ObservationRefused("foreign_reference", str(exc)) from exc
        if self._session.element_ref(instance) != plan.element:
            raise ObservationRefused("foreign_reference", "elemento não corresponde à fonte")
        type_rels = list(getattr(instance, "IsTypedBy", None) or ())
        observations: list[EvidenceObservation] = []
        matched: list[MatchedSet] = []
        coverage: list[SelectorCoverage] = []
        for selector in plan.selectors:
            for scope in SCOPES:
                status: CoverageStatus = "complete"
                reason: str | None = None
                found: list[EvidenceObservation] = []
                if scope not in plan.admitted_scopes:
                    status = "not_searched"
                else:
                    owners: list[tuple[Any, Any]] = (
                        [(instance, None)]
                        if scope == "occurrence"
                        else [(rel.RelatingType, rel) for rel in type_rels]
                    )
                    if scope == "type" and len(type_rels) > 1:
                        status, reason = "partial", "multiple_types"
                    for owner, relation in owners:
                        for definition in self._definitions(owner, scope):
                            if definition.Name != selector.set_name:
                                continue
                            matched.append(
                                MatchedSet(
                                    set_name=selector.set_name,
                                    field_name=selector.field_name,
                                    scope=scope,
                                    owner_express_id=owner.id(),
                                    set_express_id=definition.id(),
                                    set_class=_members(definition)[0],
                                )
                            )
                            for member in _members(definition)[1]:
                                if member.Name == selector.field_name:
                                    found.append(
                                        self._observe(
                                            plan, owner, scope, relation, definition, member
                                        )
                                    )
                    if len(found) > self._max_observations:
                        found = []
                        status, reason = "unsupported", "context_limit_exceeded"
                observations.extend(found)
                coverage.append(
                    SelectorCoverage(
                        set_name=selector.set_name,
                        field_name=selector.field_name,
                        scope=scope,
                        status=status,
                        reason=reason,
                    )
                )
        if len(observations) > self._max_observations:
            # Limite total por campo (plano §6): excesso agregado nunca é truncado nem
            # certificado como busca completa; nenhum seletor/escopo buscado fica completo.
            # Cobertura já incompleta conserva o próprio estado e motivo (M-06).
            observations = []
            coverage = [
                c
                if c.status != "complete"
                else SelectorCoverage(
                    set_name=c.set_name,
                    field_name=c.field_name,
                    scope=c.scope,
                    status="unsupported",
                    reason="context_limit_exceeded",
                )
                for c in coverage
            ]
        observations.sort(
            key=lambda o: (
                o.owner.express_id,
                o.set_express_id,
                o.member_express_id,
                SCOPES.index(o.origin),
            )
        )
        body = {
            "schema_version": 1,
            "plan": plan.model_dump(mode="json"),
            "plan_sha256": canonical_sha256(plan.model_dump(mode="json")),
            "observations": [o.model_dump(mode="json") for o in observations],
            "matched_sets": [m.model_dump(mode="json") for m in matched],
            "coverage": [c.model_dump(mode="json") for c in coverage],
            "problems": [],
        }
        return SearchReport.model_validate({**body, "report_sha256": canonical_sha256(body)})
