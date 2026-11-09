"""DTOs do contrato de leitura do catálogo (plano M1 §6.1).

Formas versionáveis trocadas com M2, M3 e M4. A resolução informa significado e uso
cadastrados com estado explícito; não decide conformidade IDS, não escolhe o
primeiro candidato e não converte erro de pacote em "nenhum resultado".
"""

from collections.abc import Iterator, Mapping
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
    model_validator,
)

from src.domain_catalog.models import (
    CarrierKind,
    CarrierStatus,
    IFCBinding,
    IfcSchemaId,
    LifecycleState,
    LocalId,
    NonEmptyText,
    Sha256Hex,
)

ApplicabilityState = Literal["applicable", "not_applicable", "indeterminate"]
ResolutionStatus = Literal[
    "exact", "approved_mapping", "ambiguous", "unmapped", "unsupported", "package_error"
]
"""Estado semântico da resolução, independente da conformidade IDS (plano M1 §4.2)."""

RequestFacet = Literal["attribute", "property", "classification", "material"]
"""Faceta IDS do requisito; ``property`` cobre conjuntos de propriedades e de quantidades."""

CapabilityStatus = Literal["available", "unsupported", "version_mismatch"]
SemVer = Annotated[str, StringConstraints(pattern=r"^\d+\.\d+\.\d+$")]


class ContractModel(BaseModel):
    """Base imutável dos DTOs de contrato."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class FrozenFacts(Mapping[str, str]):
    """Fatos do contexto num mapeamento imutável, comparável, hashable e serializável.

    Lê como ``dict`` (``facts["x"]``, ``get``, ``in``, iteração), mas não tem método de
    alteração: pedido e resultado conservam os fatos usados na resolução. A cópia na
    construção desacopla o mapeamento do chamador; ``frozen=True`` sozinho não impedia
    alterar um ``dict`` interno.
    """

    __slots__ = ("_items",)

    def __init__(self, facts: Mapping[str, str] | None = None) -> None:
        """Copia os fatos em ordem estável de nome."""
        self._items: tuple[tuple[str, str], ...] = tuple(sorted(dict(facts or {}).items()))

    def __getitem__(self, key: str) -> str:
        """Valor do fato pelo nome."""
        for name, value in self._items:
            if name == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        """Nomes dos fatos em ordem estável."""
        return (name for name, _ in self._items)

    def __len__(self) -> int:
        """Quantidade de fatos."""
        return len(self._items)

    def __hash__(self) -> int:
        """Hash dos pares, para que pedidos iguais tenham o mesmo hash."""
        return hash(self._items)

    def __eq__(self, other: object) -> bool:
        """Igual a qualquer mapeamento com os mesmos pares."""
        if isinstance(other, Mapping):
            return dict(self._items) == dict(other.items())
        return NotImplemented

    def __repr__(self) -> str:
        """Representação legível dos fatos."""
        return f"FrozenFacts({dict(self._items)!r})"


Facts = Annotated[
    Mapping[str, str],
    AfterValidator(FrozenFacts),
    PlainSerializer(dict, return_type=dict[str, str]),
]
"""Fatos ``nome → valor`` imutáveis no modelo; em JSON, um objeto de textos."""


class CatalogReleaseRef(ContractModel):
    """Identidade exata de um release: nunca "latest"."""

    catalog_id: LocalId
    version: SemVer
    manifest_sha256: Sha256Hex


PredefinedTypeOrigin = Literal["occurrence", "type"]
"""Nível em que o PredefinedType foi lido: a ocorrência ou o objeto de tipo associado."""


class PredefinedTypeReading(ContractModel):
    """Valor de PredefinedType declarado num nível do arquivo, sem interpretação."""

    origin: PredefinedTypeOrigin
    value: NonEmptyText


class PredefinedTypeContext(ContractModel):
    """PredefinedType do elemento como o M2 o determinou; o catálogo não o deduz do nome.

    O valor efetivo segue a regra do schema/IDS que o M2 aplica à ocorrência e ao tipo
    associado; o catálogo não aplica precedência própria.

    - ``determined``: há valor efetivo, lido em ``effective_origin``;
    - ``absent``: ocorrência e tipo associado foram consultados e nenhum declara valor;
    - ``undetermined``: informação insuficiente (por exemplo, ocorrência sem valor e tipo
      associado não consultado, ou conflito que o M2 não resolve), com ``reason``.

    ``readings`` conserva o que cada nível declara, inclusive valor divergente do
    efetivo. ``NOTDEFINED`` e ``USERDEFINED`` são valores declarados, não ausência; o
    texto de ``ObjectType``/``ElementType`` ainda não é avaliado pelo catálogo.
    """

    status: Literal["determined", "absent", "undetermined"]
    effective_origin: PredefinedTypeOrigin | None = None
    readings: tuple[PredefinedTypeReading, ...] = ()
    reason: NonEmptyText | None = None

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Estado, origem efetiva e leituras não se contradizem."""
        origins = [reading.origin for reading in self.readings]
        if len(origins) != len(set(origins)):
            raise ValueError("no máximo uma leitura por nível: ocorrência e tipo associado")
        if self.status == "determined":
            if self.effective_origin is None or self.effective_origin not in origins:
                raise ValueError("determined exige effective_origin com a leitura correspondente")
        elif self.effective_origin is not None:
            raise ValueError(f"status {self.status} não admite effective_origin")
        if self.status == "absent" and self.readings:
            raise ValueError("absent significa nenhum valor declarado; não admite leituras")
        if self.status == "undetermined" and self.reason is None:
            raise ValueError("undetermined exige reason com a informação que falta")
        return self

    @classmethod
    def determined(cls, value: str, origin: PredefinedTypeOrigin) -> "PredefinedTypeContext":
        """Valor efetivo lido num único nível, sem divergência registrada."""
        return cls(
            status="determined",
            effective_origin=origin,
            readings=(PredefinedTypeReading(origin=origin, value=value),),
        )

    @property
    def effective(self) -> str | None:
        """Valor efetivo, quando determinado."""
        return next((r.value for r in self.readings if r.origin == self.effective_origin), None)


class BindingRequest(ContractModel):
    """Caminho exigido por um requisito e o contexto conhecido; desconhecido fica ``None``.

    ``predefined_type`` é o PredefinedType efetivo informado pelo M2, com origem e
    leituras; ``None`` significa não informado e torna indeterminada a regra que o exige.
    """

    ifc_schema: IfcSchemaId
    facet: RequestFacet
    set_name: NonEmptyText | None = None
    field_name: NonEmptyText
    entity: NonEmptyText | None = None
    predefined_type: PredefinedTypeContext | None = None
    facts: Facts = Field(default_factory=FrozenFacts)
    requirement_ref: str | None = None


class ResolutionCandidate(ContractModel):
    """Uso cadastrado que corresponde ao caminho, com o motivo de ser ou não escolhido."""

    binding_id: LocalId
    concept_id: LocalId
    concept_code: str
    match: Literal["literal_path", "alias"]
    alias_id: LocalId | None = None
    applicability: ApplicabilityState
    schema_declared: bool
    carrier_status: CarrierStatus
    lifecycle: LifecycleState
    write_enabled: bool
    reasons: tuple[str, ...] = ()


RESOLVED_STATUSES: frozenset[str] = frozenset({"exact", "approved_mapping"})
"""Estados em que a resolução aponta um único uso."""


class ResolutionResult(ContractModel):
    """Resultado de resolução; só ``exact`` e ``approved_mapping`` apontam um uso.

    O uso escolhido (binding e conceito, sempre juntos) precisa constar entre os
    candidatos. ``alias_ids`` lista todos os aliases aprovados pelos quais o uso foi
    encontrado num ``approved_mapping``: vários aliases do mesmo uso não são vários
    usos, e nenhum deles é descartado da proveniência.
    """

    status: ResolutionStatus
    request: BindingRequest
    binding_id: LocalId | None = None
    concept_id: LocalId | None = None
    alias_ids: tuple[LocalId, ...] = ()
    candidates: tuple[ResolutionCandidate, ...] = ()
    reasons: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    decision_ids: tuple[LocalId, ...] = ()
    catalog: CatalogReleaseRef | None = None

    @model_validator(mode="after")
    def _resolved_only_when_unique(self) -> Self:
        """Binding e conceito escolhidos existem juntos, e somente em resolução única."""
        chosen = (self.binding_id, self.concept_id)
        if self.status not in RESOLVED_STATUSES:
            if chosen != (None, None):
                raise ValueError(f"status {self.status} não admite binding ou conceito escolhido")
            if self.alias_ids:
                raise ValueError(f"status {self.status} não admite alias_ids")
            return self
        if None in chosen:
            raise ValueError(f"status {self.status} exige binding e conceito escolhidos")
        backing = [c for c in self.candidates if c.binding_id == self.binding_id]
        if not backing or any(c.concept_id != self.concept_id for c in backing):
            raise ValueError(
                "o uso escolhido precisa constar entre os candidatos, com seu conceito"
            )
        if self.status == "exact" and self.alias_ids:
            raise ValueError("resolução exact não admite alias_ids")
        backing_aliases = {c.alias_id for c in backing if c.match == "alias"}
        if self.status == "approved_mapping" and (
            not self.alias_ids or not set(self.alias_ids) <= backing_aliases
        ):
            raise ValueError(
                "approved_mapping exige alias_ids aprovados que sejam candidatos do uso escolhido"
            )
        return self

    @classmethod
    def package_error(
        cls, request: BindingRequest, reason: str, catalog: CatalogReleaseRef | None = None
    ) -> "ResolutionResult":
        """Resultado para pacote indisponível ou inválido, com a causa explícita."""
        return cls(status="package_error", request=request, reasons=(reason,), catalog=catalog)


class OperationCapability(ContractModel):
    """Disponibilidade de uma operação no código instalado; cadastro não cria executor."""

    operation_id: str
    requested_version: str | None
    status: CapabilityStatus
    available_version: str | None
    reason: str


PageOffset = Annotated[int, Field(ge=0)]
PageLimit = Annotated[int, Field(ge=1, le=500)]


class CatalogQuery(ContractModel):
    """Busca de conceitos no release fixado.

    O texto ignora caixa e acentos só para localizar candidatos. ``entity`` compara a
    classe declarada nas regras de aplicabilidade, sem expandir subtipos.
    """

    text: NonEmptyText | None = None
    entity: NonEmptyText | None = None
    carrier_kind: CarrierKind | None = None
    profile_id: str | None = None
    source_artifact_id: str | None = None
    lifecycle: LifecycleState | None = None
    offset: PageOffset = 0
    limit: PageLimit = 50


class ConceptSummary(ContractModel):
    """Conceito encontrado e onde a consulta o encontrou; ordem não significa escolha."""

    concept_id: LocalId
    code: str
    label: str
    lifecycle: LifecycleState
    binding_ids: tuple[LocalId, ...]
    matched_by: tuple[str, ...]


class CandidatePage(ContractModel):
    """Página de conceitos com o total antes da paginação."""

    items: tuple[ConceptSummary, ...]
    total: int
    offset: int
    limit: int


class BindingQuery(ContractModel):
    """Listagem de usos; conjunto e nome comparados exatamente."""

    concept_id: LocalId | None = None
    entity: NonEmptyText | None = None
    set_name: NonEmptyText | None = None
    field_name: NonEmptyText | None = None
    carrier_kind: CarrierKind | None = None
    profile_id: str | None = None
    offset: PageOffset = 0
    limit: PageLimit = 50


class BindingPage(ContractModel):
    """Página de bindings com o total antes da paginação."""

    items: tuple[IFCBinding, ...]
    total: int
    offset: int
    limit: int
