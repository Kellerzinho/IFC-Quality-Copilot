"""Entidades do catálogo de domínio (M1-03).

Separam fonte, significado, uso IFC, aplicabilidade e evidência admissível
(plano M1 §3). O catálogo descreve conceitos; valores de elementos pertencem às
observações de uma análise e não moram aqui. Toda entidade é imutável e recusa
campos desconhecidos. Tipo, dimensão, portador e estado são sempre declarados:
nada é inferido de nomes como ``Pset_``, ``Qto_`` ou ``Is*``.
"""

from typing import Annotated, Any, Literal, NamedTuple, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    StringConstraints,
    field_validator,
    model_validator,
)

from src.domain_catalog.canonical import canonical_json_text, parse_json_strict


def _json_integer_only(value: object) -> object:
    """Recusa booleano e número real onde o formato exige inteiro: ``true`` e ``1.0`` não são 1."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"esperado inteiro, recebido {type(value).__name__} {value!r}")
    return value


FormatVersionOne = Annotated[Literal[1], BeforeValidator(_json_integer_only)]
"""Versão 1 de um formato de arquivo: somente o inteiro 1 (o ``Literal`` aceitaria ``true``)."""

LocalId = Annotated[
    str,
    StringConstraints(
        pattern=r"^urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    ),
]
"""ID estável de entidade local: UUID em URN, separado de código legível e versão."""

SourceRef = Annotated[
    str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]*:[A-Za-z0-9][A-Za-z0-9._-]*$")
]
"""ID de fonte ou de linha de fonte, com espaço de nomes (ex.: ``dai2025:A7-010``)."""

IfcClassName = Annotated[str, StringConstraints(pattern=r"^Ifc[A-Z][A-Za-z0-9]*$")]
PredefinedTypeName = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]*$")]
LangTag = Annotated[str, StringConstraints(pattern=r"^[a-z]{2,3}(-[A-Z]{2})?$")]
NonEmptyText = Annotated[str, StringConstraints(min_length=1)]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
ConceptCode = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_.-]*$")]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]*$")]
PageNumber = Annotated[StrictInt, Field(ge=1)]

LifecycleState = Literal["draft", "reviewed", "approved", "deprecated"]
"""Prontidão do registro cadastral; só ``approved``/``deprecated`` entram em release."""

PUBLISHABLE_LIFECYCLES: frozenset[str] = frozenset({"approved", "deprecated"})

LogicalType = Literal["boolean", "integer", "decimal", "string", "code", "datetime", "reference"]
Dimension = Literal[
    "length", "area", "volume", "mass", "mass_per_area", "pressure", "dimensionless", "count"
]
IfcSchemaId = Literal["IFC2X3", "IFC4", "IFC4X3_ADD2"]
CarrierKind = Literal[
    "attribute",
    "property",
    "quantity",
    "property_or_quantity",
    "material",
    "classification",
    "document",
]
"""Portador IFC do campo. ``quantity`` é portador (``IfcElementQuantity``), não faceta IDS.

``property_or_quantity`` declara portador ainda **não determinado** entre propriedade
(``IfcPropertySet``) e quantidade (``IfcElementQuantity``), ambos alcançados pela faceta
``property`` do IDS. Só existe com ``carrier_status = pending_reconciliation`` e
``ifc_type`` nulo, nunca habilita escrita e não significa que os dois sejam aceitos.
"""

SET_CARRIERS: frozenset[str] = frozenset({"property", "quantity", "property_or_quantity"})
"""Portadores que vivem num conjunto nomeado (``set_name`` e ``set_kind`` obrigatórios)."""

CarrierStatus = Literal["approved", "pending_reconciliation"]
"""Com ``pending_reconciliation`` o portador não está reconciliado e a escrita fica bloqueada;
se nem o tipo de portador é conhecido, ``carrier_kind`` é ``property_or_quantity``."""

BindingScope = Literal["occurrence", "type", "occurrence_or_type", "unspecified"]
"""Onde o campo vive. ``unspecified`` preserva o silêncio da fonte e nunca habilita escrita;
mesmo com escopo declarado, a escrita futura exige destino explícito e avaliação do alcance
em tipos compartilhados (M4/M5)."""
ValueType = Literal["code", "string", "integer", "boolean"]
AliasPurpose = Literal[
    "search",
    "label_translation",
    "historical_spelling",
    "representation_match",
    "approved_equivalence",
]
RESOLUTION_ALIAS_PURPOSES: frozenset[str] = frozenset(
    {"historical_spelling", "representation_match", "approved_equivalence"}
)
"""Finalidades de alias que a resolução pode usar; busca e tradução só localizam."""

ChannelCode = Literal["P", "T", "Q", "M", "C", "D", "H", "S", "X", "J", "G", "A", "K"]
"""Canais de leitura do M3 (docs/pesquisa/modulo-03-contexto/README.md)."""

ArtifactType = Literal[
    "dissertation",
    "ids_report",
    "ids_xml",
    "spreadsheet",
    "research_matrix",
    "article_supplement",
    "dictionary_snapshot",
    "synthetic_fixture",
]
SourceCategory = Literal[
    "entity",
    "attribute",
    "material",
    "classification",
    "custom_property",
    "standard_property",
    "quantity",
    "metadata",
    "geometry_requirement",
    "document_requirement",
]
TranscriptionStatus = Literal["registered", "checked_by_research", "checked_by_curator"]
DecisionStatus = Literal["pending", "decided", "rejected"]

IfcValueType = Literal[
    "IfcLabel",
    "IfcText",
    "IfcIdentifier",
    "IfcBoolean",
    "IfcInteger",
    "IfcReal",
    "IfcCountMeasure",
    "IfcLengthMeasure",
    "IfcPositiveLengthMeasure",
    "IfcAreaMeasure",
    "IfcVolumeMeasure",
    "IfcMassMeasure",
    "IfcPressureMeasure",
    "IfcQuantityLength",
    "IfcQuantityArea",
    "IfcQuantityVolume",
    "IfcQuantityWeight",
    "IfcQuantityCount",
]


class IfcTypeSpec(NamedTuple):
    """Tipos lógicos e dimensão compatíveis com um tipo IFC, e se é entidade de quantidade."""

    logical_types: frozenset[str]
    dimension: str | None
    is_quantity: bool


IFC_VALUE_TYPES: dict[str, IfcTypeSpec] = {
    "IfcLabel": IfcTypeSpec(frozenset({"string", "code"}), None, False),
    "IfcText": IfcTypeSpec(frozenset({"string"}), None, False),
    "IfcIdentifier": IfcTypeSpec(frozenset({"string", "code"}), None, False),
    "IfcBoolean": IfcTypeSpec(frozenset({"boolean"}), None, False),
    "IfcInteger": IfcTypeSpec(frozenset({"integer"}), None, False),
    "IfcReal": IfcTypeSpec(frozenset({"decimal"}), None, False),
    "IfcCountMeasure": IfcTypeSpec(frozenset({"integer", "decimal"}), "count", False),
    "IfcLengthMeasure": IfcTypeSpec(frozenset({"decimal"}), "length", False),
    "IfcPositiveLengthMeasure": IfcTypeSpec(frozenset({"decimal"}), "length", False),
    "IfcAreaMeasure": IfcTypeSpec(frozenset({"decimal"}), "area", False),
    "IfcVolumeMeasure": IfcTypeSpec(frozenset({"decimal"}), "volume", False),
    "IfcMassMeasure": IfcTypeSpec(frozenset({"decimal"}), "mass", False),
    "IfcPressureMeasure": IfcTypeSpec(frozenset({"decimal"}), "pressure", False),
    "IfcQuantityLength": IfcTypeSpec(frozenset({"decimal"}), "length", True),
    "IfcQuantityArea": IfcTypeSpec(frozenset({"decimal"}), "area", True),
    "IfcQuantityVolume": IfcTypeSpec(frozenset({"decimal"}), "volume", True),
    "IfcQuantityWeight": IfcTypeSpec(frozenset({"decimal"}), "mass", True),
    "IfcQuantityCount": IfcTypeSpec(frozenset({"integer", "decimal"}), "count", True),
}
"""Compatibilidade do formato v1. IfcLogical fica fora: UNKNOWN não cabe em booleano."""

_CODE_PYTHON_TYPE: dict[str, type] = {"code": str, "string": str, "integer": int, "boolean": bool}
_PHYSICAL_LOGICAL_TYPES: frozenset[str] = frozenset({"integer", "decimal"})


class CatalogModel(BaseModel):
    """Base imutável que recusa campos desconhecidos."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class LocalizedText(CatalogModel):
    """Texto em um idioma."""

    lang: LangTag
    text: NonEmptyText


def _unique_langs(texts: tuple[LocalizedText, ...]) -> tuple[LocalizedText, ...]:
    """Recusa dois textos no mesmo idioma, que deixariam o rótulo ambíguo."""
    langs = [text.lang for text in texts]
    if len(langs) != len(set(langs)):
        raise ValueError(f"idioma repetido em textos localizados: {langs}")
    return texts


LocalizedTexts = Annotated[tuple[LocalizedText, ...], AfterValidator(_unique_langs)]
"""Textos localizados com no máximo um texto por idioma."""


class Qualifier(CatalogModel):
    """Qualificador que faz parte do significado (método, critério, condição de medição)."""

    name: NonEmptyText
    value: NonEmptyText


class SourceArtifact(CatalogModel):
    """Artefato de fonte. URL identifica a origem; hash só existe para arquivo adquirido."""

    id: SourceRef
    title: NonEmptyText
    authors: tuple[NonEmptyText, ...] = ()
    issued: str | None = None
    artifact_type: ArtifactType
    location: str | None = None
    sha256: Sha256Hex | None = None
    size_bytes: Annotated[StrictInt, Field(ge=0)] | None = None
    terms: NonEmptyText
    notes: str | None = None

    @model_validator(mode="after")
    def _size_requires_hash(self) -> Self:
        """Tamanho sem hash sugeriria arquivo adquirido sem identidade verificável."""
        if self.size_bytes is not None and self.sha256 is None:
            raise ValueError("size_bytes só se registra junto com sha256 do arquivo adquirido")
        return self


class SourceLocator(CatalogModel):
    """Localização da linha na fonte; página impressa e página do PDF são distintas."""

    printed_page: PageNumber | None = None
    pdf_page: PageNumber | None = None
    table: str | None = None
    row_ref: str | None = None
    xml_path: str | None = None


class SourceAssertion(CatalogModel):
    """Assertiva transcrita fielmente; a reconciliação nunca a sobrescreve."""

    id: SourceRef
    source_artifact_id: SourceRef
    transcription_artifact_id: SourceRef | None = None
    locator: SourceLocator
    category: SourceCategory
    target_literal: NonEmptyText
    target_identifier_literal: str | None = None
    set_literal: str | None = None
    datatype_literal: str | None = None
    unit_literal: str | None = None
    domain_literal_json: str | None = None
    notes: tuple[str, ...] = ()
    transcription_status: TranscriptionStatus

    @field_validator("domain_literal_json")
    @classmethod
    def _domain_is_canonical_json(cls, value: str | None) -> str | None:
        """O domínio literal guarda JSON canônico, preservando listas, objetos e textos."""
        if value is not None and canonical_json_text(parse_json_strict(value)) != value:
            raise ValueError("domain_literal_json precisa estar em JSON canônico")
        return value

    @property
    def domain_literal(self) -> Any:
        """Cópia nova do domínio literal da fonte (``None`` quando a célula não existe)."""
        if self.domain_literal_json is None:
            return None
        return parse_json_strict(self.domain_literal_json)


class ConceptDefinition(CatalogModel):
    """Significado reutilizável; classe, portador e schema pertencem ao binding."""

    id: LocalId
    code: ConceptCode
    labels: LocalizedTexts = Field(min_length=1)
    definition: LocalizedTexts = ()
    qualifiers: tuple[Qualifier, ...] = ()
    logical_type: LogicalType
    dimension: Dimension | None = None
    unit_id: LocalId | None = None
    value_set_id: LocalId | None = None
    source_assertion_ids: tuple[SourceRef, ...] = ()
    lifecycle: LifecycleState
    notes: str | None = None

    @model_validator(mode="after")
    def _type_dimension_and_definition(self) -> Self:
        """Unidade exige dimensão; texto não tem dimensão; revisado exige definição."""
        if self.unit_id is not None and self.dimension is None:
            raise ValueError("unit_id exige dimensão física declarada no conceito")
        if self.dimension is not None and self.logical_type not in _PHYSICAL_LOGICAL_TYPES:
            raise ValueError(f"logical_type={self.logical_type} não admite dimensão física")
        if self.lifecycle in ("reviewed", "approved") and not self.definition:
            raise ValueError("conceito revisado ou aprovado exige definição")
        return self


class UnitDefinition(CatalogModel):
    """Unidade com dimensão explícita; ausência de unidade não é adimensional."""

    id: LocalId
    symbol: NonEmptyText
    dimension: Dimension
    labels: LocalizedTexts = ()
    reference: str | None = None
    lifecycle: LifecycleState


class AllowedValue(CatalogModel):
    """Valor permitido: código estável, distinto do rótulo."""

    code: StrictStr | StrictInt | StrictBool
    labels: LocalizedTexts = ()


class AllowedValueSet(CatalogModel):
    """Conjunto de valores; uma restrição local nunca estende o conjunto global."""

    id: LocalId
    value_type: ValueType
    values: tuple[AllowedValue, ...] = Field(min_length=1)
    ordered: StrictBool = False
    restricts_value_set_id: LocalId | None = None
    source_assertion_ids: tuple[SourceRef, ...] = ()
    lifecycle: LifecycleState

    @model_validator(mode="after")
    def _codes_match_value_type(self) -> Self:
        """Sem conversão entre texto, número e booleano; sem código repetido."""
        expected = _CODE_PYTHON_TYPE[self.value_type]
        seen: set[tuple[type, object]] = set()
        for value in self.values:
            if type(value.code) is not expected:
                raise ValueError(
                    f"código {value.code!r} incompatível com value_type={self.value_type}"
                )
            key = (type(value.code), value.code)
            if key in seen:
                raise ValueError(f"código duplicado no conjunto: {value.code!r}")
            seen.add(key)
        return self


class Condition(CatalogModel):
    """Condição declarativa sobre um fato do contexto; fato ausente é indeterminado."""

    fact: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
    operator: Literal["in", "not_in"]
    values: tuple[NonEmptyText, ...] = Field(min_length=1)


class ApplicabilityRule(CatalogModel):
    """Aplicabilidade cadastral; não substitui a aplicabilidade formal do IDS."""

    id: LocalId
    entity_classes: tuple[IfcClassName, ...] = Field(min_length=1)
    include_subtypes: StrictBool
    predefined_types: tuple[PredefinedTypeName, ...] | None = Field(default=None, min_length=1)
    conditions: tuple[Condition, ...] = ()
    source_assertion_ids: tuple[SourceRef, ...] = ()
    lifecycle: LifecycleState
    notes: str | None = None


class EvidencePolicy(CatalogModel):
    """Evidência admissível e operação; capacidade vem do registro de código, não do cadastro.

    Uma política estreita (leitura exata, na E1) não limita as receitas futuras do M3:
    mapeamentos aprovados, relações, conversões e cálculos implementados e interpretação
    fundamentada pela LLM entram como operações versionadas e testadas. ``on_missing`` vale
    só para evidência ausente após busca completa nos canais admitidos; não consultado,
    parcial, não suportado e erro são estados distintos e nunca contam como ausência.
    ``request_human`` pede valor tipado com fundamento e justificativa; ``request_review``
    apresenta todas as fontes em conflito, sem desempate. Valor permitido ou alternativa do
    IDS não comprova valor do projeto.
    """

    id: LocalId
    operation_id: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_.]*$")]
    operation_version: NonEmptyText | None = None
    admissible_channels: tuple[ChannelCode, ...] = Field(min_length=1)
    preconditions: tuple[NonEmptyText, ...] = ()
    on_missing: Literal["abstain", "request_human"]
    on_conflict: Literal["abstain", "request_review"]
    source_assertion_ids: tuple[SourceRef, ...] = ()
    lifecycle: LifecycleState
    notes: str | None = None


class IFCBinding(CatalogModel):
    """Uso de um conceito em portador IFC, com nome exato preservado (caixa e acentos)."""

    id: LocalId
    concept_id: LocalId
    applicability_rule_id: LocalId
    declared_schemas: tuple[IfcSchemaId, ...] = Field(min_length=1)
    carrier_kind: CarrierKind
    set_name: NonEmptyText | None = None
    field_name: NonEmptyText
    set_kind: Literal["standard", "custom"] | None = None
    ifc_type: IfcValueType | None = None
    source_original_type: str | None = None
    scope: BindingScope
    carrier_status: CarrierStatus
    value_set_id: LocalId | None = None
    evidence_policy_id: LocalId | None = None
    write_enabled: StrictBool = False
    source_assertion_ids: tuple[SourceRef, ...] = ()
    lifecycle: LifecycleState
    notes: str | None = None

    @model_validator(mode="after")
    def _carrier_is_coherent(self) -> Self:
        """Conjunto e tipo coerentes com o portador; escrita só com tudo aprovado."""
        if self.carrier_kind in SET_CARRIERS:
            if self.set_name is None:
                raise ValueError(f"set_name obrigatório para portador {self.carrier_kind}")
            if self.set_kind is None:
                raise ValueError("set_kind deve ser declarado; prefixo Pset_/Qto_ não decide")
        elif self.set_name is not None or self.set_kind is not None:
            raise ValueError(f"set_name/set_kind não se aplicam a carrier_kind={self.carrier_kind}")
        if self.carrier_kind == "property_or_quantity":
            if self.carrier_status != "pending_reconciliation":
                raise ValueError(
                    "property_or_quantity só existe com carrier_status pending_reconciliation: "
                    "portador aprovado precisa ser determinado"
                )
            if self.ifc_type is not None:
                raise ValueError(
                    "property_or_quantity exige ifc_type nulo: tipo de valor ou entidade de "
                    "quantidade elegeria o portador"
                )
        if self.ifc_type is not None:
            spec = IFC_VALUE_TYPES[self.ifc_type]
            if self.carrier_kind == "quantity" and not spec.is_quantity:
                raise ValueError("ifc_type de portador quantity precisa ser entidade IfcQuantity*")
            if self.carrier_kind != "quantity" and spec.is_quantity:
                raise ValueError("ifc_type IfcQuantity* só cabe em portador quantity")
        if self.write_enabled and (
            self.carrier_status != "approved"
            or self.lifecycle != "approved"
            or self.ifc_type is None
        ):
            raise ValueError(
                "write_enabled exige binding aprovado, portador aprovado e ifc_type reconciliado"
            )
        if self.write_enabled and self.scope == "unspecified":
            raise ValueError(
                "write_enabled exige escopo declarado: unspecified não autoriza escrever na "
                "ocorrência, no tipo nem nos dois"
            )
        return self


class AliasScope(CatalogModel):
    """Escopo do alias; vazio significa global."""

    set_names: tuple[NonEmptyText, ...] | None = None
    entity_classes: tuple[IfcClassName, ...] | None = None
    schemas: tuple[IfcSchemaId, ...] | None = None

    @property
    def is_global(self) -> bool:
        """Se o alias vale em qualquer conjunto, classe e schema."""
        return self.set_names is None and self.entity_classes is None and self.schemas is None


class AliasMapping(CatalogModel):
    """Alias com finalidade explícita; nunca torna fontes equivalentes por si só."""

    id: LocalId
    term: NonEmptyText
    lang: LangTag | None = None
    purpose: AliasPurpose
    scope: AliasScope
    target_concept_id: LocalId | None = None
    target_binding_id: LocalId | None = None
    source_assertion_ids: tuple[SourceRef, ...] = ()
    lifecycle: LifecycleState
    notes: str | None = None

    @model_validator(mode="after")
    def _target_and_scope(self) -> Self:
        """Um único alvo; alias de resolução aponta binding e tem escopo."""
        if (self.target_concept_id is None) == (self.target_binding_id is None):
            raise ValueError("alias precisa de exatamente um alvo: conceito ou binding")
        if self.purpose in RESOLUTION_ALIAS_PURPOSES:
            if self.scope.is_global:
                raise ValueError(
                    "alias usado na resolução exige escopo (conjunto, classe ou schema)"
                )
            if self.target_binding_id is None:
                raise ValueError("alias usado na resolução precisa ter um binding como alvo")
        return self


class ProfileMembership(CatalogModel):
    """Participação de um binding em perfil; não cria requisito obrigatório no IDS."""

    id: LocalId
    profile_id: Slug
    binding_id: LocalId
    source_assertion_ids: tuple[SourceRef, ...] = Field(min_length=1)
    lifecycle: LifecycleState


class ReconciliationDecision(CatalogModel):
    """Divergência entre assertivas; pendente não vira dado aprovado."""

    id: LocalId
    code: Slug
    status: DecisionStatus
    source_assertion_ids: tuple[SourceRef, ...] = Field(min_length=1)
    summary: NonEmptyText
    proposal: str | None = None
    justification: str | None = None
    affected_binding_ids: tuple[LocalId, ...] = ()
    notes: str | None = None

    @model_validator(mode="after")
    def _decided_requires_justification(self) -> Self:
        """Decisão tomada precisa de justificativa rastreável."""
        if self.status != "pending" and not self.justification:
            raise ValueError("decisão tomada ou rejeitada exige justificativa")
        return self
