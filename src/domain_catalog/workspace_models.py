"""Modelos de leitura e de erro da área de trabalho do catálogo (M1-14, E5).

São projeções somente leitura, montadas pela fachada ``workspace.py`` a partir dos
serviços E2/E3. Não carregam autoridade: estado cadastral, estado do rascunho, estado
IDS, estado de mapeamento e estado de evidência ficam em campos separados, sem um
``status`` genérico. Nenhum destes modelos é gravado; a verdade continua nos serviços.
"""

from typing import Literal

from pydantic import Field

from src.domain_catalog.contracts import CatalogReleaseRef, ContractModel
from src.domain_catalog.curation_models import CommandId

WorkspaceMode = Literal["operational", "simulation"]
"""``simulation``: armazenamento temporário isolado e sintético; nada ali é aprovação real."""

ViewKind = Literal["release", "draft"]
GroupBy = Literal["element", "requirement"]

SIMULATION_NOTICE = (
    "SIMULAÇÃO — armazenamento temporário isolado com dados e atores sintéticos. "
    "Nada feito aqui aprova conteúdo real, publica catálogo real ou altera um IFC."
)
IDENTITY_NOTICE = (
    "Identidade declarada localmente (unverified_local): o nome informado identifica, "
    "mas não autentica. A autorização de cada ação é conferida no serviço."
)


class WorkspaceSession(ContractModel):
    """Sessão emitida pelo backend; a interface guarda só esta referência opaca."""

    session_id: str
    actor_context_id: str
    declared_name: str | None
    identity_assurance: Literal["unverified_local"] = "unverified_local"
    mode: WorkspaceMode


class CatalogView(ContractModel):
    """Conteúdo exibido: um release publicado exato ou uma revisão exata de rascunho."""

    kind: ViewKind
    release: CatalogReleaseRef | None = None
    draft_id: str | None = None
    revision: int | None = None


class RowFilters(ContractModel):
    """Filtros da tabela; ``None`` não filtra."""

    source: str | None = None
    entity_class: str | None = None
    profile: str | None = None
    state: str | None = None


class FilterOptions(ContractModel):
    """Valores disponíveis para cada filtro, em ordem estável."""

    sources: tuple[str, ...] = ()
    entity_classes: tuple[str, ...] = ()
    profiles: tuple[str, ...] = ()
    states: tuple[str, ...] = ()


class CapabilityView(ContractModel):
    """Disponibilidade da operação da política de evidência no código instalado."""

    state: Literal["available", "unsupported", "version_mismatch", "no_policy"]
    operation_id: str | None = None
    requested_version: str | None = None
    available_version: str | None = None
    reason: str


class CatalogRow(ContractModel):
    """Uma linha da tabela: um uso (binding) com seu conceito, nunca fundidos."""

    binding_id: str
    concept_id: str
    concept_code: str
    concept_label: str
    set_name: str | None
    field_name: str
    carrier_kind: str
    carrier_status: str
    scope: str
    ifc_type: str | None
    entity_classes: tuple[str, ...]
    schemas: tuple[str, ...]
    profiles: tuple[str, ...]
    sources: tuple[str, ...]
    lifecycle: str
    write_enabled: bool
    capability: CapabilityView
    concept_shared_by: int = Field(ge=1)


class LiteralPair(ContractModel):
    """Campo lado a lado: literal da fonte (original) e valor reconciliado do catálogo."""

    aspect: str
    original: tuple[str, ...]
    reconciled: str | None


class AssertionView(ContractModel):
    """Assertiva de fonte citada, com literais fiéis e situação da transcrição."""

    assertion_id: str
    source_artifact_id: str
    locator: str
    target_literal: str
    set_literal: str | None
    datatype_literal: str | None
    unit_literal: str | None
    domain_literal_json: str | None
    transcription_status: str


class AliasView(ContractModel):
    """Alias com finalidade e escopo explícitos."""

    alias_id: str
    term: str
    purpose: str
    scope: str
    target: str
    lifecycle: str


class DecisionView(ContractModel):
    """Decisão de reconciliação que afeta o uso."""

    decision_id: str
    code: str
    status: str
    summary: str
    justification: str | None


class HistoryEntry(ContractModel):
    """Evento confirmado de curadoria ou publicação ligado ao que está exibido."""

    at_utc: str
    operation: str
    actor: str
    subject: str
    transition: str
    reason: str | None


class RowDetail(ContractModel):
    """Detalhe de um uso: conceito × binding, original × reconciliado, proveniência."""

    row: CatalogRow
    concept_definition: tuple[str, ...]
    concept_logical_type: str
    concept_dimension: str | None
    unit: str | None
    value_set: tuple[str, ...]
    applicability: str
    applicability_conditions: tuple[str, ...]
    predefined_types: tuple[str, ...]
    aliases: tuple[AliasView, ...]
    policy_id: str | None
    policy_channels: tuple[str, ...]
    policy_on_missing: str | None
    policy_on_conflict: str | None
    original_vs_reconciled: tuple[LiteralPair, ...]
    assertions: tuple[AssertionView, ...]
    decisions: tuple[DecisionView, ...]
    sibling_bindings: tuple[str, ...]
    history: tuple[HistoryEntry, ...]
    notes: tuple[str, ...]


class FieldIssue(ContractModel):
    """Problema de validação localizado por entidade e campo, para o formulário."""

    severity: Literal["error", "warning", "pending"]
    code: str
    entity_kind: str | None
    entity_id: str | None
    field: str | None
    message: str


class ValidationView(ContractModel):
    """Validação automática de uma revisão exata, agrupável por entidade/campo."""

    draft_id: str
    revision: int
    content_sha256: str
    errors: int
    warnings: int
    pending: int
    issues: tuple[FieldIssue, ...]


class DraftSummary(ContractModel):
    """Rascunho em lista, com o hash da revisão atual para confirmações exatas."""

    draft_id: str
    title: str
    state: str
    revision: int
    content_sha256: str
    base_release: CatalogReleaseRef | None
    candidate_id: str | None
    published_release: CatalogReleaseRef | None


class CandidateSummary(ContractModel):
    """Candidato preparado: versão, hash do manifesto e pendências declaradas."""

    candidate_id: str
    draft_id: str
    revision: int
    version: str
    manifest_sha256: str
    state: str
    pending_items: tuple[str, ...]
    pending_ids: tuple[str, ...]
    added: tuple[str, ...]
    changed: tuple[str, ...]
    deprecated: tuple[str, ...]


class ActionReceipt(ContractModel):
    """Resultado de um comando confirmado; ``replayed`` indica repetição idempotente."""

    command_id: CommandId
    operation: str
    subject: str
    revision: int | None
    replayed: bool
    message: str


class PinView(ContractModel):
    """Pin vigente do projeto e seu histórico; nunca "latest"."""

    project_id: str
    project_name: str
    pin_revision: int
    pair_set_revision: int
    catalog: CatalogReleaseRef | None
    adopted_by: str | None
    reason: str | None
    pairs: tuple[str, ...]
    history: tuple[str, ...]


class AdoptionPreview(ContractModel):
    """Plano de adoção pronto para confirmação explícita do hash exato."""

    plan_id: str
    plan_sha256: str
    intent: str
    old_catalog: CatalogReleaseRef | None
    target_catalog: CatalogReleaseRef
    diff_lines: tuple[str, ...]
    diff_absent_reason: str | None
    impact_lines: tuple[str, ...]
    reanalysis_scope: str
    pairs: int
    statement: str


class AnalysisRow(ContractModel):
    """Requisito × elemento com três estados separados: IDS, mapeamento e evidência."""

    element: str
    requirement: str
    expected: str
    found: str
    origin: str
    ids_state: str
    ids_reason: str | None
    mapping_state: str
    evidence_state: str
    evidence_detail: str | None


class AnalysisView(ContractModel):
    """Análise exata reaberta por hash, agrupada por elemento ou por requisito."""

    analysis_id: str
    state: str
    catalog: CatalogReleaseRef | None
    pin_revision: int
    group_by: GroupBy
    rows: tuple[AnalysisRow, ...]
    limitations: tuple[str, ...]


class WorkspaceError(Exception):
    """Falha apresentável: código estável, mensagem sem caminhos e orientação.

    ``keep_input`` pede à interface que preserve o que o usuário digitou;
    ``retry_same_key`` indica que repetir com a mesma chave idempotente é seguro.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        keep_input: bool = True,
        retry_same_key: bool = False,
        issues: tuple[FieldIssue, ...] = (),
        current_revision: int | None = None,
    ) -> None:
        """Guarda os dados apresentáveis da falha."""
        self.code = code
        self.message = message
        self.keep_input = keep_input
        self.retry_same_key = retry_same_key
        self.issues = issues
        self.current_revision = current_revision
        super().__init__(f"[{code}] {message}")
