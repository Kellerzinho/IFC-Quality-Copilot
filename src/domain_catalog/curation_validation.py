"""Regras de conteúdo da curadoria (E2): validação, patch, materialização e diff.

Funções puras sobre ``CatalogContent``, usadas pelos serviços de curadoria e de
publicação e pela tela de curadoria (achados por entidade e campo).

- **Validação** (plano M1 §4.1, passo 4) reúne os problemas da E1 (``content.py``) e
  os portões desta etapa: proposta nova só em ``draft``; entidade herdada do
  release-base não muda sem virar proposta nem desaparece (só é depreciada); fonte
  publicada é imutável; decisão de reconciliação pendente trava o portador dos usos
  que afeta; duplicata idêntica exige revisão de identidade; uso com portador
  pendente segue a política de publicação vigente. Capacidade indisponível, escopo
  ``unspecified`` e conteúdo sintético são avisos visíveis.
- **Materialização**: só a aprovação humana transforma propostas (``draft`` ou
  ``reviewed``) em ``approved``; nada mais muda. Editar nunca escreve ``approved``.
- **Patch**: operações atômicas (incluir, retirar proposta, depreciar, duplicar); um
  erro em qualquer operação recusa o patch inteiro, com o campo de cada problema.
  Retirar proposta sobre entidade herdada restaura a versão publicada, byte a byte.
"""

from collections.abc import Callable
from typing import Final, Literal

from pydantic import ValidationError

from src.domain_catalog.canonical import canonical_json_text
from src.domain_catalog.content import ENTITY_KINDS, CatalogContent, content_issues
from src.domain_catalog.contracts import CatalogReleaseRef
from src.domain_catalog.curation_errors import DraftPatchError
from src.domain_catalog.curation_models import (
    LIFECYCLE_KINDS,
    DeprecateEntity,
    DiffSummary,
    DraftPatch,
    DuplicateEntity,
    PendingItem,
    RemoveProposal,
    Severity,
    UpsertEntity,
    ValidationFinding,
    ValidationReport,
    content_sha256,
)
from src.domain_catalog.errors import CatalogValidationError, ContentIssue
from src.domain_catalog.models import CatalogModel
from src.domain_catalog.operations import OperationRegistry
from src.domain_catalog.package import ENTITY_MODELS

VALIDATOR_VERSION: Final = "m1-e2-validacao-1"
"""Versão das regras; muda quando um portão muda, e fica gravada em cada resumo."""

PendingCarrierPolicy = Literal["block", "acknowledge", "allow"]
"""Uso com portador pendente: bloquear (B), publicar com reconhecimento (C) ou publicar (A)."""

PENDING_CARRIER_POLICY: Final[PendingCarrierPolicy] = "block"
"""Política vigente: bloquear até decisão do curador responsável (B; registro E2)."""

_PROPOSAL_LIFECYCLES: frozenset[str] = frozenset({"draft", "reviewed"})
_SOURCE_KINDS: tuple[str, ...] = ("source_artifacts", "source_assertions")
_SEVERITY_RANK: dict[str, int] = {"error": 0, "pending": 1, "warning": 2}

Index = dict[str, dict[str, CatalogModel]]


def _index(content: CatalogContent | None) -> Index:
    """Entidades de cada tipo por ID (vazio sem conteúdo)."""
    if content is None:
        return {kind: {} for kind in ENTITY_KINDS}
    return {
        kind: {getattr(entity, "id"): entity for entity in getattr(content, kind)}  # noqa: B009
        for kind in ENTITY_KINDS
    }


def index_content(content: CatalogContent | None) -> Index:
    """Entidades de cada tipo por ID; sem conteúdo, todos os tipos vazios."""
    return _index(content)


def _lifecycle(entity: CatalogModel) -> str | None:
    return getattr(entity, "lifecycle", None)


def _with_lifecycle(entity: CatalogModel, lifecycle: str) -> CatalogModel:
    """Mesma entidade com outro estado cadastral, revalidada pelo modelo."""
    return type(entity).model_validate({**entity.model_dump(), "lifecycle": lifecycle})


def _id(entity: CatalogModel) -> str:
    return str(getattr(entity, "id"))  # noqa: B009 - toda entidade do conteúdo tem ``id``


def _rebuild(entities: Index) -> CatalogContent:
    """Conteúdo com as entidades de cada tipo em ordem de ID."""
    return CatalogContent.model_validate(
        {kind: tuple(sorted(entities[kind].values(), key=_id)) for kind in ENTITY_KINDS}
    )


def entity_key(entity: CatalogModel) -> str:
    """ID de uma entidade do conteúdo (toda entidade tem ``id``)."""
    return _id(entity)


def rebuild_content(entities: Index) -> CatalogContent:
    """Conteúdo a partir de um índice por tipo, com as entidades em ordem de ID."""
    return _rebuild(entities)


# --- materialização ------------------------------------------------------------------------


def _materialize(content: CatalogContent) -> tuple[CatalogContent | None, list[ValidationFinding]]:
    """Promove propostas a ``approved``; entidade que não sobrevive à promoção vira achado."""
    entities = _index(content)
    findings: list[ValidationFinding] = []
    for kind in LIFECYCLE_KINDS:
        for entity_id, entity in list(entities[kind].items()):
            if _lifecycle(entity) not in _PROPOSAL_LIFECYCLES:
                continue
            try:
                entities[kind][entity_id] = _with_lifecycle(entity, "approved")
            except ValidationError as exc:
                for error in exc.errors():
                    findings.append(
                        ValidationFinding(
                            severity="error",
                            code="release.invalid_after_approval",
                            entity_kind=kind,
                            entity_id=entity_id,
                            field=".".join(str(part) for part in error["loc"]) or None,
                            message=f"a proposta não é válida como aprovada: {error['msg']}",
                        )
                    )
    if findings:
        return None, findings
    return _rebuild(entities), findings


def materialize_release_content(content: CatalogContent) -> CatalogContent:
    """Conteúdo do release que a aprovação de ``content`` produz.

    Propostas (``draft``/``reviewed``) passam a ``approved``; herdadas e depreciadas
    ficam como estão. É o único caminho de proposta a aprovado, e só a aprovação
    humana de uma revisão exata o aciona.
    """
    released, findings = _materialize(content)
    if released is None:
        raise CatalogValidationError(
            [
                ContentIssue(
                    code=finding.code,
                    entity_kind=finding.entity_kind or "",
                    entity_id=finding.entity_id or "",
                    field=finding.field,
                    message=finding.message,
                )
                for finding in findings
            ]
        )
    return released


# --- pendências ----------------------------------------------------------------------------


def pending_items(content: CatalogContent) -> tuple[PendingItem, ...]:
    """Pendências que acompanham aprovação, candidato e recibo, em ordem estável."""
    items = [
        PendingItem(
            kind="carrier_pending",
            entity_id=binding.id,
            detail=(
                f"{binding.set_name or '-'}.{binding.field_name} ({binding.carrier_kind}): "
                "portador pendente de reconciliação; escrita bloqueada"
            ),
        )
        for binding in content.bindings
        if binding.carrier_status == "pending_reconciliation"
    ]
    items += [
        PendingItem(
            kind="reconciliation_decision",
            entity_id=decision.id,
            detail=f"{decision.code}: {decision.summary}",
        )
        for decision in content.reconciliation_decisions
        if decision.status == "pending"
    ]
    return tuple(sorted(items, key=lambda item: (item.kind, item.entity_id)))


# --- validação -----------------------------------------------------------------------------

Add = Callable[..., None]


def _check_lifecycles(content: CatalogContent, published: Index, add: Add) -> None:
    current = _index(content)
    for kind in LIFECYCLE_KINDS:
        for entity_id, entity in current[kind].items():
            state = _lifecycle(entity)
            if state in _PROPOSAL_LIFECYCLES:
                continue
            original = published[kind].get(entity_id)
            if original is None:
                add(
                    "error",
                    "lifecycle.not_from_release",
                    kind,
                    entity_id,
                    "lifecycle",
                    f"estado {state} só existe em entidade herdada de release publicado; "
                    "proposta nova fica em draft até a aprovação",
                )
                continue
            expected = original if state == "approved" else _with_lifecycle(original, "deprecated")
            if entity != expected:
                add(
                    "error",
                    "lifecycle.published_entity_modified",
                    kind,
                    entity_id,
                    None,
                    "entidade publicada alterada sem virar proposta: edite-a como proposta "
                    "em draft, sujeita à aprovação",
                )
        for entity_id in sorted(published[kind].keys() - current[kind].keys()):
            add(
                "error",
                "lifecycle.published_entity_removed",
                kind,
                entity_id,
                None,
                "entidade publicada não pode sair do próximo release; use depreciação",
            )


def _check_sources(content: CatalogContent, published: Index, add: Add) -> None:
    current = _index(content)
    for kind in _SOURCE_KINDS:
        for entity_id, original in published[kind].items():
            now = current[kind].get(entity_id)
            if now is None:
                add(
                    "error",
                    "source.published_source_removed",
                    kind,
                    entity_id,
                    None,
                    "fonte publicada não pode sair do próximo release",
                )
            elif now != original:
                add(
                    "error",
                    "source.published_source_modified",
                    kind,
                    entity_id,
                    None,
                    "fonte publicada é imutável; correção de transcrição cria assertiva nova "
                    "com outro ID e vínculo",
                )
    decisions = current["reconciliation_decisions"]
    for entity_id in sorted(published["reconciliation_decisions"].keys() - decisions.keys()):
        add(
            "error",
            "decision.published_decision_removed",
            "reconciliation_decisions",
            entity_id,
            None,
            "decisão publicada não pode sair do próximo release",
        )


def _check_decision_locks(content: CatalogContent, add: Add) -> None:
    bindings = {binding.id: binding for binding in content.bindings}
    for decision in content.reconciliation_decisions:
        if decision.status != "pending":
            continue
        for binding_id in decision.affected_binding_ids:
            binding = bindings.get(binding_id)
            if binding is None:
                continue
            if binding.carrier_status != "pending_reconciliation" or binding.write_enabled:
                add(
                    "error",
                    "decision.pending_locks_carrier",
                    "bindings",
                    binding_id,
                    "carrier_status",
                    f"a decisão pendente {decision.code} trava o portador deste uso: "
                    "reconciliar exige decidir a divergência, com justificativa, na mesma revisão",
                )


def _check_duplicates(content: CatalogContent, add: Add) -> None:
    for kind in LIFECYCLE_KINDS:
        seen: dict[str, str] = {}
        for entity in sorted(getattr(content, kind), key=_id):
            signature = canonical_json_text(
                entity.model_dump(mode="json", exclude={"id", "lifecycle"})
            )
            if signature in seen:
                add(
                    "error",
                    "identity.unreviewed_duplicate",
                    kind,
                    _id(entity),
                    "id",
                    f"igual a {seen[signature]} exceto pelo ID: revise a identidade (conceito, "
                    "fonte, aplicabilidade e operações) antes de submeter",
                )
            else:
                seen[signature] = _id(entity)


_CARRIER_MESSAGES: dict[str, str] = {
    "block": (
        "uso com portador pendente de reconciliação não pode ser aprovado nem publicado até "
        "haver evidência (política vigente: bloquear)"
    ),
    "acknowledge": (
        "uso com portador pendente entra no release com escrita bloqueada; a publicação exige "
        "reconhecimento explícito desta pendência"
    ),
    "allow": "uso com portador pendente entra no release com escrita bloqueada",
}


def _check_pending_carriers(
    content: CatalogContent, policy: PendingCarrierPolicy, add: Add
) -> None:
    for binding in content.bindings:
        if binding.carrier_status != "pending_reconciliation":
            continue
        if binding.lifecycle in _PROPOSAL_LIFECYCLES:
            severity = "error" if policy == "block" else "pending"
            add(
                severity,
                "carrier.pending_proposal",
                "bindings",
                binding.id,
                "carrier_status",
                _CARRIER_MESSAGES[policy],
            )
        else:
            add(
                "pending",
                "carrier.pending_published",
                "bindings",
                binding.id,
                "carrier_status",
                "uso já publicado com portador pendente; escrita bloqueada",
            )


def _warnings(
    content: CatalogContent, base: CatalogContent | None, registry: OperationRegistry, add: Add
) -> None:
    for policy in content.evidence_policies:
        capability = registry.capability(policy.operation_id, policy.operation_version)
        if capability.status != "available":
            add(
                "warning",
                "capability.operation_unavailable",
                "evidence_policies",
                policy.id,
                "operation_id",
                f"operação {policy.operation_id} {capability.status}: sem enriquecimento por "
                "esta política até existir implementação versionada e testada",
            )
    for binding in content.bindings:
        if binding.scope == "unspecified":
            add(
                "warning",
                "binding.scope_unspecified",
                "bindings",
                binding.id,
                "scope",
                "escopo ocorrência/tipo não esclarecido: não autoriza escrita em nenhum dos dois",
            )
    for artifact in content.source_artifacts:
        if artifact.artifact_type == "synthetic_fixture":
            add(
                "warning",
                "source.synthetic_content",
                "source_artifacts",
                artifact.id,
                "artifact_type",
                "conteúdo sintético: o release será rotulado synthetic_fixture, nunca curado",
            )
    concepts = {concept.id: concept for concept in content.concepts}
    for binding in content.bindings:
        concept = concepts.get(binding.concept_id)
        active_binding = binding.lifecycle != "deprecated"
        if concept is not None and concept.lifecycle == "deprecated" and active_binding:
            add(
                "warning",
                "lifecycle.deprecated_reference",
                "bindings",
                binding.id,
                "concept_id",
                "uso ativo aponta conceito depreciado",
            )
    for decision in content.reconciliation_decisions:
        if decision.status == "pending":
            add(
                "pending",
                "decision.pending",
                "reconciliation_decisions",
                decision.id,
                "status",
                f"decisão {decision.code} pendente: {decision.summary}",
            )
    if base is not None and content_sha256(content) == content_sha256(base):
        add(
            "warning",
            "draft.no_changes",
            None,
            None,
            None,
            "a revisão é igual ao release-base: publicar geraria versão sem mudança",
        )


def validate_revision(
    *,
    draft_id: str,
    revision: int,
    content: CatalogContent,
    base: CatalogContent | None,
    base_release: CatalogReleaseRef | None,
    registry: OperationRegistry,
    pending_carrier_policy: PendingCarrierPolicy,
) -> ValidationReport:
    """Validação automática de uma revisão exata; não substitui revisão humana.

    Os achados saem em ordem estável (severidade, código, entidade, campo), de modo
    que o mesmo conteúdo produz o mesmo relatório e o mesmo hash de relatório.
    """
    findings: list[ValidationFinding] = []
    seen: set[tuple[str, str | None, str | None, str | None]] = set()

    def add(
        severity: Severity,
        code: str,
        kind: str | None,
        entity_id: str | None,
        field: str | None,
        message: str,
    ) -> None:
        findings.append(
            ValidationFinding(
                severity=severity,
                code=code,
                entity_kind=kind,
                entity_id=entity_id,
                field=field,
                message=message,
            )
        )

    for issue in content_issues(content, for_release=False):
        seen.add((issue.code, issue.entity_kind, issue.entity_id, issue.field))
        add(
            "error",
            f"content.{issue.code}",
            issue.entity_kind,
            issue.entity_id,
            issue.field,
            issue.message,
        )
    published = _index(base)
    _check_lifecycles(content, published, add)
    _check_sources(content, published, add)
    _check_decision_locks(content, add)
    _check_duplicates(content, add)
    _check_pending_carriers(content, pending_carrier_policy, add)
    released, problems = _materialize(content)
    findings.extend(problems)
    if released is not None:
        for issue in content_issues(released, for_release=True):
            key = (issue.code, issue.entity_kind, issue.entity_id, issue.field)
            if key not in seen:
                add(
                    "error",
                    f"release.{issue.code}",
                    issue.entity_kind,
                    issue.entity_id,
                    issue.field,
                    issue.message,
                )
    _warnings(content, base, registry, add)
    ordered = sorted(
        findings,
        key=lambda x: (
            _SEVERITY_RANK[x.severity],
            x.code,
            x.entity_kind or "",
            x.entity_id or "",
            x.field or "",
            x.message,
        ),
    )
    return ValidationReport.model_validate(
        {
            "draft_id": draft_id,
            "revision": revision,
            "content_sha256": content_sha256(content),
            "base_release": base_release,
            "validator_version": VALIDATOR_VERSION,
            "findings": ordered,
        }
    )


# --- patch -------------------------------------------------------------------------------


def apply_patch(
    content: CatalogContent, patch: DraftPatch, *, base: CatalogContent | None
) -> tuple[CatalogContent, tuple[str, ...]]:
    """Aplica todas as operações ou nenhuma; devolve o conteúdo novo e o registro das operações.

    Incluir só aceita proposta em ``draft`` (aprovar é ato da revisão humana, não de
    edição). Retirar a proposta tira do rascunho a entidade nova; sobre entidade
    herdada do release-base, descarta a alteração ou a depreciação proposta e restaura
    exatamente a versão publicada (registro ``restore``); entidade publicada sem
    proposta nunca sai. Depreciar só vale para entidade publicada sem alteração;
    duplicar gera proposta com novo ID e nunca herda escrita habilitada. Patch que não
    muda nada é recusado.
    """
    entities = _index(content)
    published = _index(base)
    issues: list[ContentIssue] = []
    log: list[str] = []

    def problem(code: str, kind: str, entity_id: str, field: str | None, message: str) -> None:
        issues.append(
            ContentIssue(
                code=code, entity_kind=kind, entity_id=entity_id, field=field, message=message
            )
        )

    def used_elsewhere(kind: str, entity_id: str) -> str | None:
        return next(
            (other for other in ENTITY_KINDS if other != kind and entity_id in entities[other]),
            None,
        )

    for position, operation in enumerate(patch.operations, start=1):
        where = f"operação {position}"
        if isinstance(operation, UpsertEntity):
            kind = operation.kind
            raw_id = str(operation.entity.get("id", "?"))
            try:
                entity = ENTITY_MODELS[kind].model_validate(operation.entity)
            except ValidationError as exc:
                for error in exc.errors():
                    problem(
                        "invalid_entity",
                        kind,
                        raw_id,
                        ".".join(str(part) for part in error["loc"]) or None,
                        f"{where}: {error['msg']}",
                    )
                continue
            entity_id = _id(entity)
            state = _lifecycle(entity)
            if kind in LIFECYCLE_KINDS and state != "draft":
                problem(
                    "proposal_must_be_draft",
                    kind,
                    entity_id,
                    "lifecycle",
                    f"{where}: proposta entra em draft; {state} só resulta da aprovação humana "
                    "ou da operação de depreciação",
                )
                continue
            if other := used_elsewhere(kind, entity_id):
                problem(
                    "id_used_by_other_kind",
                    kind,
                    entity_id,
                    "id",
                    f"{where}: ID já usado em {other}",
                )
                continue
            original = published[kind].get(entity_id)
            if kind in _SOURCE_KINDS and original is not None and entity != original:
                problem(
                    "published_source_immutable",
                    kind,
                    entity_id,
                    None,
                    f"{where}: fonte publicada é imutável; registre assertiva nova com outro ID",
                )
                continue
            entities[kind][entity_id] = entity
            log.append(f"upsert {kind} {entity_id}")
        elif isinstance(operation, RemoveProposal):
            kind, entity_id = operation.kind, operation.entity_id
            original = published[kind].get(entity_id)
            if entity_id not in entities[kind]:
                problem("unknown_entity", kind, entity_id, None, f"{where}: entidade inexistente")
            elif original is None:
                del entities[kind][entity_id]
                log.append(f"remove {kind} {entity_id}")
            elif entities[kind][entity_id] == original:
                problem(
                    "published_entity_not_removable",
                    kind,
                    entity_id,
                    None,
                    f"{where}: entidade publicada sem proposta neste rascunho não sai do release; "
                    "para tirá-la de uso, use a operação deprecate",
                )
            else:
                entities[kind][entity_id] = original
                log.append(f"restore {kind} {entity_id}")
        elif isinstance(operation, DeprecateEntity):
            kind, entity_id = operation.kind, operation.entity_id
            original = published[kind].get(entity_id)
            if original is None:
                problem(
                    "deprecate_requires_published_entity",
                    kind,
                    entity_id,
                    None,
                    f"{where}: só entidade publicada é depreciada; proposta nova é retirada",
                )
            elif _lifecycle(original) == "deprecated":
                problem(
                    "already_deprecated", kind, entity_id, "lifecycle", f"{where}: já depreciada"
                )
            elif entities[kind].get(entity_id) != original:
                problem(
                    "deprecate_requires_unchanged_entity",
                    kind,
                    entity_id,
                    None,
                    f"{where}: há proposta sobre esta entidade neste rascunho; retire-a com a "
                    "operação remove (volta a valer a versão publicada) e então deprecie",
                )
            else:
                entities[kind][entity_id] = _with_lifecycle(original, "deprecated")
                log.append(f"deprecate {kind} {entity_id}")
        elif isinstance(operation, DuplicateEntity):
            kind = operation.kind
            source = entities[kind].get(operation.source_id)
            if source is None:
                problem(
                    "unknown_entity",
                    kind,
                    operation.source_id,
                    None,
                    f"{where}: origem inexistente",
                )
                continue
            if any(operation.new_id in entities[other] for other in ENTITY_KINDS):
                problem("id_in_use", kind, operation.new_id, "id", f"{where}: novo ID já usado")
                continue
            data = {**source.model_dump(), "id": operation.new_id, "lifecycle": "draft"}
            if kind == "bindings":
                data["write_enabled"] = False
            entities[kind][operation.new_id] = ENTITY_MODELS[kind].model_validate(data)
            log.append(f"duplicate {kind} {operation.source_id} -> {operation.new_id}")
    if issues:
        raise DraftPatchError(issues)
    result = _rebuild(entities)
    if content_sha256(result) == content_sha256(content):
        raise DraftPatchError(
            [
                ContentIssue(
                    code="no_change",
                    entity_kind="draft",
                    entity_id="-",
                    field=None,
                    message="o patch não altera o conteúdo da revisão",
                )
            ]
        )
    return result, tuple(log)


# --- diff ---------------------------------------------------------------------------------


def content_diff(base: CatalogContent | None, content: CatalogContent) -> DiffSummary:
    """Entidades acrescentadas, alteradas e depreciadas em relação ao release-base."""
    published = _index(base)
    added: list[str] = []
    changed: list[str] = []
    deprecated: list[str] = []
    for kind in ENTITY_KINDS:
        for entity in sorted(getattr(content, kind), key=_id):
            entity_id = _id(entity)
            original = published[kind].get(entity_id)
            ref = f"{kind}:{entity_id}"
            if original is None:
                added.append(ref)
            elif entity == original:
                continue
            elif (
                _lifecycle(entity) == "deprecated"
                and _lifecycle(original) != "deprecated"
                and entity == _with_lifecycle(original, "deprecated")
            ):
                deprecated.append(ref)
            else:
                changed.append(ref)
    return DiffSummary(added=tuple(added), changed=tuple(changed), deprecated=tuple(deprecated))
