"""Contratos de transporte da API de revisão M4 (fatia plataforma-base).

Nomes seguem o plano (M2/M3/M4 §5): ``SourceArtifactRef``, ``ElementRef``,
``ElementRecord``, ``ModelPairBinding``. ``Gap`` (lacuna) e ``Suggestion`` são
PROVISÓRIOS até M2/M3 fecharem seus formatos e carregam
``schema_status="provisorio_aguardando_M2_M3"``.

Regras de identidade:
- revisão de um arquivo = SHA-256 dos bytes; o nome não participa;
- elemento = modelo + revisão IFC + express_id; GlobalId é só atributo;
- zero, FALSE e string vazia são valores observados, nunca ausência.
"""

from typing import Annotated, Final, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION: Final = "m4-plataforma-base/1"
PROVISIONAL_STATUS: Final = "provisorio_aguardando_M2_M3"

Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Discipline = Literal["architecture", "structure"]
ArtifactRole = Literal["ifc", "ids"]
GlobalIdState = Literal["unique", "duplicated_in_file", "missing"]
ScalarValue = bool | int | float | str
ProvisionalSchemaStatus = Literal["provisorio_aguardando_M2_M3"]


class _Contract(BaseModel):
    """Base dos contratos: imutável e sem campos extras."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------------------
# Fontes e identidade
# ---------------------------------------------------------------------------


class SourceArtifactRef(_Contract):
    """Referência imutável aos bytes de um IFC ou IDS recebido.

    ``revision_id`` é o SHA-256 do conteúdo: o mesmo arquivo enviado com outro
    nome produz a mesma revisão. ``display_name`` é só apresentação.
    """

    role: ArtifactRole
    revision_id: Sha256Hex
    size_bytes: int = Field(ge=0)
    display_name: str
    ifc_schema: str | None = None


class ElementRef(_Contract):
    """Identidade de um elemento: modelo lógico + revisão IFC + express_id.

    O GlobalId NÃO faz parte da chave: dois arquivos (ou duas entidades do
    mesmo arquivo) podem repetir GlobalId e continuam sendo elementos distintos.
    O express_id só localiza a entidade naquela revisão; não indica
    continuidade entre revisões.
    """

    model_id: str = Field(min_length=1)
    ifc_revision_id: Sha256Hex
    express_id: int = Field(gt=0)

    @property
    def key(self) -> str:
        """Retorna a forma textual estável da chave composta."""
        return f"{self.model_id}:{self.ifc_revision_id}:{self.express_id}"


class ElementRecord(_Contract):
    """Resumo de navegação de um elemento (não é evidência de requisito)."""

    ref: ElementRef
    ifc_class: str
    name: str | None = None
    global_id: str | None = Field(
        default=None, description="Atributo IFC; não é identidade."
    )
    global_id_state: GlobalIdState
    has_geometry: bool


class ModelPairBinding(_Contract):
    """Linha disciplina–IFC–IDS de um projeto.

    A confirmação cobre as revisões efetivas: trocar o IFC ou o IDS invalida a
    confirmação anterior. Nomes de arquivo nunca decidem o vínculo.
    """

    project_id: str
    model_id: str
    discipline: Discipline
    ifc: SourceArtifactRef | None = None
    ids: SourceArtifactRef | None = None
    confirmed: bool = False
    confirmed_ifc_revision_id: Sha256Hex | None = None
    confirmed_ids_revision_id: Sha256Hex | None = None

    @model_validator(mode="after")
    def _confirmation_matches_sources(self) -> "ModelPairBinding":
        """Garante que confirmação só exista sobre as revisões atuais."""
        if not self.confirmed:
            if self.confirmed_ifc_revision_id or self.confirmed_ids_revision_id:
                raise ValueError("revisões confirmadas exigem confirmed=True")
            return self
        if self.ifc is None or self.ids is None:
            raise ValueError("confirmação exige IFC e IDS registrados")
        if (
            self.confirmed_ifc_revision_id != self.ifc.revision_id
            or self.confirmed_ids_revision_id != self.ids.revision_id
        ):
            raise ValueError("confirmação não corresponde às revisões atuais")
        return self


class Project(_Contract):
    """Projeto com as duas linhas de modelo (arquitetura e estrutura)."""

    schema_version: Literal["m4-plataforma-base/1"] = SCHEMA_VERSION
    project_id: str
    name: str
    models: list[ModelPairBinding]


class ProjectSummary(_Contract):
    """Projeto salvo no armazenamento local, com as datas (UTC) e as duas linhas."""

    project_id: str
    name: str
    created_at: AwareDatetime
    updated_at: AwareDatetime
    models: list[ModelPairBinding]


class ProjectList(_Contract):
    """Projetos do armazenamento local, do alterado mais recentemente ao mais antigo."""

    schema_version: Literal["m4-plataforma-base/1"] = SCHEMA_VERSION
    total: int
    items: list[ProjectSummary]


class CreateProjectRequest(_Contract):
    """Pedido de criação de projeto."""

    name: str = Field(min_length=1, max_length=200)


class ConfirmBindingRequest(_Contract):
    """Confirmação explícita das revisões IFC e IDS de uma linha."""

    ifc_revision_id: Sha256Hex
    ids_revision_id: Sha256Hex


class ElementList(_Contract):
    """Elementos de uma revisão IFC, em ordem estável de express_id."""

    schema_version: Literal["m4-plataforma-base/1"] = SCHEMA_VERSION
    model_id: str
    ifc_revision_id: Sha256Hex
    total: int
    items: list[ElementRecord]


# ---------------------------------------------------------------------------
# Valores observados
# ---------------------------------------------------------------------------


ValueKind = Literal["boolean", "integer", "real", "string", "other"]
ObservationState = Literal["present", "empty", "null", "property_absent", "pset_absent"]


class ObservedValue(_Contract):
    """Valor lido do IFC, sem conversão para texto.

    ``present`` com 0 ou FALSE continua presente; ``empty`` é string vazia;
    ``null`` é propriedade existente sem valor; ausências distinguem Pset e
    propriedade.
    """

    state: ObservationState
    kind: ValueKind | None = None
    value: ScalarValue | None = None

    @model_validator(mode="after")
    def _state_matches_value(self) -> "ObservedValue":
        """Impede valor em ausência e ausência disfarçada de valor."""
        if self.state == "present":
            if self.value is None or self.kind is None:
                raise ValueError("estado present exige value e kind")
        elif self.state == "empty":
            if self.value != "" or self.kind != "string":
                raise ValueError("estado empty exige string vazia")
        elif self.value is not None or self.kind is not None:
            raise ValueError(f"estado {self.state} não carrega valor")
        return self


class ProvisionalMarkerObservation(_Contract):
    """Observação do ADAPTADOR M4 (não do legado) sobre marcador provisório.

    "A definir", 0 e FALSE gravados como marcadores são classificados como
    provisórios, nunca como valor real confirmado. O valor tipado original
    permanece em ``Gap.current_value``.
    """

    observed_by: Literal["m4_adapter"] = "m4_adapter"
    marker: Literal["A definir", "0", "FALSE"]
    classification: Literal["provisorio"] = "provisorio"
    note: str = (
        "Observação do adaptador M4, não do legado. Marcador tratado como "
        "provisório; não é valor confirmado."
    )


# ---------------------------------------------------------------------------
# Lacuna (PROVISÓRIA)
# ---------------------------------------------------------------------------


class GapRequirement(_Contract):
    """Requisito que originou a lacuna, como interpretado pelo parser legado."""

    property_set: str
    property_name: str
    check: str
    expected_value: str | None = None
    unit: str | None = None
    specification: str


GapOrigin = Literal["legacy_ifc_analyzer", "m4_adapter_marker"]
GapResolution = Literal["resolved", "ambiguous", "not_found"]


class Gap(_Contract):
    """Lacuna PROVISÓRIA — aguarda o diagnóstico canônico de M2.

    ``origin`` separa o que veio do legado (``legacy_ifc_analyzer``) do que é
    observação própria do adaptador (``m4_adapter_marker``). Quando o legado
    aponta um GlobalId repetido no arquivo, ``resolution="ambiguous"`` lista
    todos os candidatos e nenhum é escolhido.
    """

    schema_status: ProvisionalSchemaStatus = PROVISIONAL_STATUS
    gap_id: str
    origin: GapOrigin
    resolution: GapResolution
    element: ElementRef | None = None
    candidates: list[ElementRef] = Field(default_factory=list)
    global_id: str | None = None
    ifc_class: str
    element_name: str | None = None
    requirement: GapRequirement
    current_value: ObservedValue | None = None
    provisional_marker: ProvisionalMarkerObservation | None = None

    @model_validator(mode="after")
    def _resolution_is_consistent(self) -> "Gap":
        """Impede escolha arbitrária entre candidatos ambíguos."""
        if self.resolution == "resolved":
            if self.element is None or self.candidates:
                raise ValueError("resolved exige um elemento e nenhum candidato")
        elif self.resolution == "ambiguous":
            if self.element is not None or len(self.candidates) < 2:
                raise ValueError("ambiguous exige 2+ candidatos e nenhum elemento")
            if self.current_value is not None:
                raise ValueError("ambiguous não pode atribuir valor a um candidato")
        elif self.element is not None or self.candidates:
            raise ValueError("not_found não carrega elemento")
        return self


class GapList(_Contract):
    """Lacunas PROVISÓRIAS de uma linha confirmada."""

    schema_status: ProvisionalSchemaStatus = PROVISIONAL_STATUS
    schema_version: Literal["m4-plataforma-base/1"] = SCHEMA_VERSION
    model_id: str
    ifc_revision_id: Sha256Hex
    ids_revision_id: Sha256Hex
    source: str
    total: int
    items: list[Gap]
    limitations: list[str]


# ---------------------------------------------------------------------------
# Sugestão (PROVISÓRIA) — formato do FieldEnrichmentResult M3
# ---------------------------------------------------------------------------


class FieldRef(_Contract):
    """Campo-alvo de enriquecimento num elemento identificado."""

    element: ElementRef
    property_set: str
    property_name: str


class ProposedValue(_Contract):
    """Valor tipado de uma alternativa.

    0 e FALSE podem ser propostas legítimas e são preservados como tipados;
    "A definir" nunca é valor e é recusado.
    """

    kind: Literal["boolean", "integer", "real", "string"]
    value: ScalarValue
    unit: str | None = None

    @model_validator(mode="after")
    def _not_a_placeholder(self) -> "ProposedValue":
        """Recusa marcador textual como se fosse valor real."""
        if isinstance(self.value, str) and self.value.strip().casefold() == "a definir":
            raise ValueError("'A definir' é marcador provisório, não valor proposto")
        return self


class FieldAlternative(_Contract):
    """Alternativa proposta: valor, método, evidências e limitações."""

    alternative_id: str
    value: ProposedValue
    method: str
    evidence: list[str] = Field(min_length=1)
    justification: str
    limitations: list[str] = Field(default_factory=list)


class ProposedSuggestion(_Contract):
    """Sugestão PROVISÓRIA com ao menos uma alternativa (não autoriza escrita)."""

    outcome: Literal["proposed"]
    schema_status: ProvisionalSchemaStatus = PROVISIONAL_STATUS
    field: FieldRef
    alternatives: list[FieldAlternative] = Field(min_length=1)


class AbstainedSuggestion(_Contract):
    """Abstenção PROVISÓRIA: motivo sem valor algum (extra=forbid recusa value)."""

    outcome: Literal["abstained"]
    schema_status: ProvisionalSchemaStatus = PROVISIONAL_STATUS
    field: FieldRef
    reason: str = Field(min_length=1)


Suggestion = Annotated[
    ProposedSuggestion | AbstainedSuggestion, Field(discriminator="outcome")
]


# ---------------------------------------------------------------------------
# Erros e saúde
# ---------------------------------------------------------------------------


class ApiError(_Contract):
    """Erro legível, sem stack trace nem caminho privado."""

    code: str
    message: str
    correlation_id: str


class Health(_Contract):
    """Estado mínimo da API local."""

    status: Literal["ok"] = "ok"
    schema_version: Literal["m4-plataforma-base/1"] = SCHEMA_VERSION
