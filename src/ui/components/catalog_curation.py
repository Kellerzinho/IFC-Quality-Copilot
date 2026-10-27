"""Curadoria e publicação pela interface (M1-14, E5).

Solicitação de operador, rascunho (criar sobre release, adicionar uso com operação
existente, duplicar, editar campo, retirar, depreciar), validação por entidade/campo,
diff, submissão e revisão da revisão/hash exatos, preparo de candidato e publicação
por pessoa. Cada ação é um comando do serviço com chave idempotente; a autorização é
do serviço. Salvar, aprovar conteúdo e publicar são ações distintas.
"""

import streamlit as st

from src.domain_catalog.curation_models import OriginRef, RequestedField
from src.domain_catalog.package import ComponentTerms
from src.domain_catalog.workspace import CatalogWorkspace
from src.domain_catalog.workspace_models import (
    CatalogView,
    DraftSummary,
    WorkspaceError,
    WorkspaceSession,
)
from src.ui.components.catalog_authoring import render_first_catalog, render_semantic_authoring
from src.ui.components.catalog_workspace import (
    run_action,
    safe_text,
    show_error,
    show_issues,
)

EDITABLE_FIELDS = ("field_name", "set_name", "ifc_type", "scope", "notes")
CARRIERS = ("property", "quantity", "attribute")
SCOPES = ("occurrence", "type", "occurrence_or_type")
SCHEMAS = ("IFC2X3", "IFC4", "IFC4X3_ADD2")
NEW_POLICY = "nova política sobre operação registrada"


def _need_identity(session: WorkspaceSession | None) -> bool:
    if session is None:
        st.info("Identifique-se no topo da página para registrar ações.")
        return True
    return False


def _draft(ws: CatalogWorkspace, view: CatalogView) -> DraftSummary | None:
    """Estado atual do rascunho com a revisão/hash **vistos** pela pessoa."""
    if view.kind != "draft" or view.draft_id is None:
        return None
    current = next((d for d in ws.list_drafts() if d.draft_id == view.draft_id), None)
    if current is None or view.revision is None or view.revision == current.revision:
        return current
    digest = next(h for n, _, _, h in ws.revisions(view.draft_id) if n == view.revision)
    return current.model_copy(update={"revision": view.revision, "content_sha256": digest})


def _render_request(ws: CatalogWorkspace, session: WorkspaceSession, view: CatalogView) -> None:
    st.subheader("Solicitação de operador (campo desconhecido ou nova operação)")
    with st.form("catalog_request_form"):
        field = st.text_input("Campo solicitado", key="catalog_req_field")
        set_name = st.text_input("Conjunto (opcional)", key="catalog_req_set")
        entity = st.text_input("Classe IFC (opcional)", key="catalog_req_entity")
        origin = st.text_input("Requisito IDS de origem (opcional)", key="catalog_req_origin")
        motivation = st.text_area("Motivação", key="catalog_req_motivation")
        if st.form_submit_button("Registrar solicitação"):
            try:
                catalog_id = ws.catalog_id_of(view)
                requested = RequestedField(
                    field_name=field, set_name=set_name or None, entity=entity or None
                )
                origins = (OriginRef(kind="ids_requirement", ref=origin),) if origin else ()
            except (WorkspaceError, ValueError) as error:
                st.error("Solicitação incompleta.")
                st.text(str(getattr(error, "message", error)))
                return
            run_action(
                "request",
                lambda key: ws.request_change(
                    session,
                    command_id=key,
                    catalog_id=catalog_id,
                    motivation=motivation,
                    field=requested,
                    origin_refs=origins,
                ),
            )
    requests = ws.list_requests()
    if requests:
        st.dataframe(
            [
                {
                    "Solicitação": r.request_id,
                    "Estado": r.state,
                    "Campo": r.field.field_name,
                    "Motivação": r.motivation,
                    "Por (declarado)": r.requested_by.responsible_label,
                }
                for r in requests
            ],
            hide_index=True,
            width="stretch",
        )
        open_ids = [r.request_id for r in requests if r.state in ("open", "in_triage")]
        if open_ids:
            with st.form("catalog_request_action_form"):
                chosen = st.selectbox("Solicitação", open_ids, key="catalog_req_pick")
                action = st.radio("Ação", ("triage", "reject", "cancel"), key="catalog_req_action")
                reason = st.text_input("Motivo/justificativa", key="catalog_req_reason")
                if st.form_submit_button("Registrar ação na solicitação"):
                    run_action(
                        f"request_{action}",
                        lambda key: ws.act_on_request(
                            session, command_id=key, request_id=chosen, action=action, reason=reason
                        ),
                    )


def _render_add_usage(ws: CatalogWorkspace, session: WorkspaceSession, draft: DraftSummary) -> None:
    content = ws.view_content(
        CatalogView(kind="draft", draft_id=draft.draft_id, revision=draft.revision)
    )
    concepts = {f"{c.code} · {c.id}": c.id for c in content.concepts}
    available = {
        c.operation_id for c in ws.operations() if c.state == "available" and c.operation_id
    }
    policies = {
        f"{p.operation_id} {p.operation_version or ''} · {p.id}": p.id
        for p in content.evidence_policies
        if p.operation_id in available
    }
    st.subheader("Adicionar uso de conceito existente (operação já implementada)")
    if not concepts:
        st.info("Não há conceito neste rascunho para reutilizar.")
        return
    with st.form("catalog_add_usage_form"):
        concept = st.selectbox("Conceito (mesmo significado)", list(concepts), key="catalog_au_c")
        classes = st.text_input("Classes IFC (separadas por vírgula)", key="catalog_au_classes")
        subtypes = st.checkbox("Incluir subtipos", key="catalog_au_sub")
        schemas = st.multiselect("Schemas", SCHEMAS, default=["IFC4"], key="catalog_au_sch")
        carrier = st.selectbox("Portador", CARRIERS, key="catalog_au_carrier")
        set_name = st.text_input("Conjunto", key="catalog_au_set")
        set_kind = st.selectbox("Tipo de conjunto", ("custom", "standard"), key="catalog_au_sk")
        field = st.text_input("Campo", key="catalog_au_field")
        ifc_type = st.text_input("Tipo IFC (ex.: IfcLabel)", key="catalog_au_type")
        scope = st.selectbox("Escopo", SCOPES, key="catalog_au_scope")
        policy = st.selectbox(
            "Evidência admissível",
            ["(sem enriquecimento)", *policies, NEW_POLICY],
            key="catalog_au_policy",
        )
        operation = st.selectbox(
            "Operação registrada (para nova política)",
            sorted(available) or ["(nenhuma operação implementada)"],
            key="catalog_au_op",
        )
        reason = st.text_input("Motivo", key="catalog_au_reason")
        if st.form_submit_button("Salvar uso no rascunho"):
            run_action(
                "add_usage",
                lambda key: ws.add_usage(
                    session,
                    command_id=key,
                    draft_id=draft.draft_id,
                    expected_revision=draft.revision,
                    concept_id=concepts[concept],
                    entity_classes=[c.strip() for c in classes.split(",") if c.strip()],
                    include_subtypes=subtypes,
                    schemas=schemas,
                    carrier_kind=carrier,
                    set_name=set_name or None,
                    set_kind=set_kind if set_name else None,
                    field_name=field,
                    ifc_type=ifc_type or None,
                    scope=scope,
                    reason=reason,
                    evidence_policy_id=policies.get(policy),
                    operation_id=operation if policy == NEW_POLICY else None,
                ),
            )


def _render_row_actions(
    ws: CatalogWorkspace, session: WorkspaceSession, draft: DraftSummary
) -> None:
    rows = ws.rows(CatalogView(kind="draft", draft_id=draft.draft_id, revision=draft.revision))
    if not rows:
        return
    st.subheader("Ações sobre uma linha do rascunho")
    labels = {f"{r.field_name} · {', '.join(r.entity_classes)} · {r.binding_id}": r for r in rows}
    with st.form("catalog_row_action_form"):
        chosen = st.selectbox("Linha", list(labels), key="catalog_ra_row")
        action = st.radio(
            "Ação",
            ("editar campo", "duplicar linha", "retirar proposta", "depreciar"),
            key="catalog_ra_action",
        )
        field = st.selectbox("Campo a editar", EDITABLE_FIELDS, key="catalog_ra_field")
        value = st.text_input("Novo valor (vazio = remover)", key="catalog_ra_value")
        reason = st.text_input("Motivo", key="catalog_ra_reason")
        if st.form_submit_button("Aplicar ao rascunho"):
            binding_id = labels[chosen].binding_id
            common = {
                "draft_id": draft.draft_id,
                "expected_revision": draft.revision,
                "reason": reason,
            }
            if action == "editar campo":
                run_action(
                    "edit",
                    lambda key: ws.edit_entity(
                        session,
                        command_id=key,
                        kind="bindings",
                        entity_id=binding_id,
                        changes={field: value or None},
                        **common,  # type: ignore[arg-type]
                    ),
                )
            elif action == "duplicar linha":
                run_action(
                    "duplicate",
                    lambda key: ws.duplicate_usage(
                        session,
                        command_id=key,
                        binding_id=binding_id,
                        **common,  # type: ignore[arg-type]
                    ),
                )
            elif action == "retirar proposta":
                run_action(
                    "withdraw",
                    lambda key: ws.withdraw_proposal(
                        session,
                        command_id=key,
                        kind="bindings",
                        entity_id=binding_id,
                        **common,  # type: ignore[arg-type]
                    ),
                )
            else:
                run_action(
                    "deprecate",
                    lambda key: ws.deprecate(
                        session,
                        command_id=key,
                        kind="bindings",
                        entity_id=binding_id,
                        **common,  # type: ignore[arg-type]
                    ),
                )


def _render_review(ws: CatalogWorkspace, session: WorkspaceSession, draft: DraftSummary) -> None:
    st.subheader("Validação, diff e revisão da revisão exata")
    safe_text("Rascunho", f"{draft.title} · estado {draft.state}")
    safe_text("Revisão e hash exibidos", f"r{draft.revision} · {draft.content_sha256}")
    try:
        report = ws.validation(draft.draft_id, draft.revision)
    except WorkspaceError as error:
        show_error(error)
        return
    st.text(
        f"Validação automática: {report.errors} erro(s), {report.warnings} aviso(s), "
        f"{report.pending} pendência(s). Validação não é revisão humana."
    )
    show_issues(report.issues)
    with st.expander("Diff sobre o release-base e revisões"):
        for line in ws.revision_diff(draft.draft_id, draft.revision):
            st.text(line)
        for number, origin, why, digest in ws.revisions(draft.draft_id):
            st.text(f"r{number} · {origin} · {digest[:12]}… · {why}")
        for line in ws.reviews(draft.draft_id):
            st.text(line)
    if draft.state == "editing":
        with st.form("catalog_submit_form"):
            reason = st.text_input("Motivo da submissão", key="catalog_sub_reason")
            confirm = st.checkbox(
                f"Submeter exatamente a r{draft.revision} ({draft.content_sha256[:12]}…)",
                key="catalog_sub_confirm",
            )
            if st.form_submit_button("Enviar para revisão humana") and confirm:
                run_action(
                    "submit",
                    lambda key: ws.submit_for_review(
                        session,
                        command_id=key,
                        draft_id=draft.draft_id,
                        revision=draft.revision,
                        content_sha256=draft.content_sha256,
                        reason=reason,
                    ),
                )
    if draft.state == "in_review":
        with st.form("catalog_review_form"):
            verdict = st.radio(
                "Decisão", ("approve", "request_changes", "reject"), key="catalog_rev_verdict"
            )
            justification = st.text_area("Justificativa", key="catalog_rev_justification")
            confirm = st.checkbox(
                f"Decido sobre a r{draft.revision} ({draft.content_sha256[:12]}…). Aprovar "
                "conteúdo não publica, não adota pin e não altera IFC.",
                key="catalog_rev_confirm",
            )
            if st.form_submit_button("Registrar revisão") and confirm:
                run_action(
                    "review",
                    lambda key: ws.review(
                        session,
                        command_id=key,
                        draft_id=draft.draft_id,
                        revision=draft.revision,
                        content_sha256=draft.content_sha256,
                        verdict=verdict,  # type: ignore[arg-type]
                        justification=justification,
                    ),
                )


def render_curation_tab(
    ws: CatalogWorkspace, session: WorkspaceSession | None, view: CatalogView | None
) -> None:
    """Solicitações, edição do rascunho e revisão humana."""
    if _need_identity(session):
        return
    assert session is not None
    try:
        if view is None:
            render_first_catalog(ws, session)
            return
        _render_request(ws, session, view)
        if view.kind == "release" and view.release is not None:
            release = view.release
            with st.form("catalog_new_draft_form"):
                title = st.text_input("Título do novo rascunho", key="catalog_nd_title")
                reason = st.text_input("Motivo", key="catalog_nd_reason")
                if st.form_submit_button("Abrir rascunho sobre este release"):
                    run_action(
                        "new_draft",
                        lambda key: ws.create_draft(
                            session,
                            command_id=key,
                            title=title,
                            reason=reason,
                            base_release=release,
                        ),
                    )
            return
        draft = _draft(ws, view)
        if draft is None:
            return
        if draft.state in ("editing", "in_review", "approved"):
            if draft.state != "editing":
                st.info("Salvar uma edição retorna a 'editing' e invalida a aprovação/candidato.")
            render_semantic_authoring(ws, session, draft)
            _render_add_usage(ws, session, draft)
            _render_row_actions(ws, session, draft)
        else:
            st.info(f"Rascunho em {draft.state}: edição indisponível durante esta etapa.")
        _render_review(ws, session, draft)
    except WorkspaceError as error:
        show_error(error)


def render_publication_tab(ws: CatalogWorkspace, session: WorkspaceSession | None) -> None:
    """Preparo do candidato e publicação humana do hash exato; retomada/abandono."""
    if _need_identity(session):
        return
    assert session is not None
    if ws.mode == "operational":
        st.warning(
            "Publicação real: só um curador humano, sobre revisão aprovada e hash exato. "
            "Publicar não adota pin em projeto algum."
        )
    try:
        for draft in ws.list_drafts():
            if draft.state == "approved":
                _render_prepare(ws, session, draft)
            if draft.candidate_id and draft.state in ("approved", "publishing"):
                _render_publish(ws, session, draft.candidate_id)
        _render_inspection(ws, session)
    except WorkspaceError as error:
        show_error(error)


def _render_prepare(ws: CatalogWorkspace, session: WorkspaceSession, draft: DraftSummary) -> None:
    if draft.candidate_id:
        return
    st.subheader("Preparar candidato")
    safe_text("Rascunho aprovado", f"{draft.title} (r{draft.revision})")
    with st.form(f"catalog_prepare_form_{draft.draft_id}"):
        version = st.text_input("Versão (semver)", key=f"catalog_prep_v_{draft.draft_id}")
        component = st.text_input(
            "Componente", value="conteúdo", key=f"catalog_prep_c_{draft.draft_id}"
        )
        terms = st.text_input("Termos de distribuição", key=f"catalog_prep_t_{draft.draft_id}")
        reason = st.text_input("Motivo", key=f"catalog_prep_r_{draft.draft_id}")
        if st.form_submit_button("Preparar candidato (não publica)"):
            try:
                declared = (ComponentTerms(component=component, terms=terms),)
            except ValueError:
                st.error("Informe componente e termos.")
                return
            run_action(
                f"prepare_{draft.draft_id}",
                lambda key: ws.prepare_release(
                    session,
                    command_id=key,
                    draft_id=draft.draft_id,
                    revision=draft.revision,
                    content_sha256=draft.content_sha256,
                    version=version,
                    terms=declared,
                    reason=reason,
                ),
            )


def _render_publish(ws: CatalogWorkspace, session: WorkspaceSession, candidate_id: str) -> None:
    candidate = ws.candidate(candidate_id)
    if candidate.state not in ("prepared", "publishing"):
        return
    st.subheader(f"Candidato {candidate.version}")
    safe_text("Hash do manifesto", candidate.manifest_sha256)
    safe_text("Revisão aprovada", f"r{candidate.revision}")
    for line in (*candidate.added, *candidate.changed, *candidate.deprecated):
        st.text(f"diff: {line}")
    for item in candidate.pending_items:
        st.text(f"pendência declarada: {item}")
    with st.form(f"catalog_publish_form_{candidate_id}"):
        typed = st.text_input(
            "Digite a versão exata para confirmar", key=f"catalog_pub_v_{candidate_id}"
        )
        justification = st.text_area("Justificativa", key=f"catalog_pub_j_{candidate_id}")
        acknowledge = st.checkbox(
            "Reconheço as pendências listadas", key=f"catalog_pub_ack_{candidate_id}"
        )
        if st.form_submit_button("Publicar este candidato"):
            if typed != candidate.version:
                st.error("A versão digitada não confere; nada foi publicado.")
                return
            pending = candidate.pending_ids if acknowledge else ()
            run_action(
                f"publish_{candidate_id}",
                lambda key: ws.publish(
                    session,
                    command_id=key,
                    candidate_id=candidate.candidate_id,
                    version=candidate.version,
                    manifest_sha256=candidate.manifest_sha256,
                    justification=justification,
                    acknowledged_pending=pending,
                ),
            )


def _render_inspection(ws: CatalogWorkspace, session: WorkspaceSession) -> None:
    lines = ws.publication_inspection()
    st.subheader("Inspeção de publicações interrompidas")
    if not lines:
        st.text("Nenhuma intenção pendente ou resíduo.")
        return
    for line in lines:
        st.text(line)
    intents = [intent_id for intent_id, _ in ws.pending_intents()]
    if not intents:
        return
    with st.form("catalog_intent_form"):
        intent = st.selectbox("Intenção", intents, key="catalog_intent_pick")
        action = st.radio("Ação", ("retomar", "abandonar"), key="catalog_intent_action")
        reason = st.text_input("Motivo", key="catalog_intent_reason")
        if st.form_submit_button("Registrar"):
            if action == "retomar":
                run_action(
                    f"resume_{intent}",
                    lambda key: ws.resume_publication(
                        session, command_id=key, intent_id=intent, reason=reason
                    ),
                )
            else:
                run_action(
                    f"abandon_{intent}",
                    lambda key: ws.abandon_publication(
                        session, command_id=key, intent_id=intent, reason=reason
                    ),
                )
