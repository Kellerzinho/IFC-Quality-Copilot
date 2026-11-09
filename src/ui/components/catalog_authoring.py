"""Formulários locais de autoria semântica; todas as gravações passam pela E2."""

from typing import Any, get_args

import streamlit as st

from src.domain_catalog.models import AliasPurpose, Dimension, LogicalType
from src.domain_catalog.workspace import CatalogWorkspace
from src.domain_catalog.workspace_models import (
    ActionReceipt,
    CatalogView,
    DraftSummary,
    WorkspaceSession,
)
from src.ui.components.catalog_workspace import run_action, safe_text


def render_first_catalog(ws: CatalogWorkspace, session: WorkspaceSession) -> None:
    """Abre o primeiro rascunho sem semear ou aprovar conteúdo real."""
    st.subheader("Iniciar catálogo local")
    st.caption(
        "Namespace provisório. Importação aceita candidates.json exportado pelo staging "
        "bSDD ou conteúdo de catálogo em rascunho, até 8 MiB. Não aprova nem publica."
    )
    with st.form("catalog_first_form"):
        name = st.text_input("Nome do catálogo", key="catalog_first_name")
        namespace = st.text_input("Namespace local", key="catalog_first_namespace")
        maintainer = st.text_input("Mantenedor declarado", key="catalog_first_maintainer")
        title = st.text_input("Título do primeiro rascunho", key="catalog_first_title")
        upload = st.file_uploader(
            "Candidatos locais (opcional)", type=["json"], key="catalog_first_upload"
        )
        source = st.text_input("Identificação da fonte importada", key="catalog_first_source")
        reason = st.text_input("Motivo da criação/importação", key="catalog_first_reason")
        if st.form_submit_button("Criar primeiro rascunho"):
            run_action(
                "first_catalog",
                lambda key: ws.start_catalog(
                    session,
                    command_id=key,
                    name=name,
                    namespace=namespace,
                    maintainer=maintainer,
                    title=title,
                    reason=reason,
                    candidates=upload.getvalue() if upload else None,
                    source_label=source,
                ),
            )


def _text(entity: Any, field: str) -> str:
    texts = getattr(entity, field, ())
    return next((t.text for t in texts if t.lang == "pt-BR"), "")


def _localized(entity: Any, field: str, value: str) -> list[dict[str, str]]:
    """Preserva outros idiomas quando a pessoa edita o texto português."""
    result = [t.model_dump() for t in getattr(entity, field, ()) if t.lang != "pt-BR"]
    if value:
        result.append({"lang": "pt-BR", "text": value})
    return result


def _pick(label: str, options: list[str], current: str | None, key: str) -> str:
    return st.selectbox(
        label, options, index=options.index(current) if current in options else 0, key=key
    )


def render_semantic_authoring(
    ws: CatalogWorkspace,
    session: WorkspaceSession,
    draft: DraftSummary,
) -> None:
    """Cria/edita conceitos, unidades, domínios, aliases e decisões A/B pela plataforma."""
    content = ws.view_content(
        CatalogView(kind="draft", draft_id=draft.draft_id, revision=draft.revision)
    )
    st.subheader("Autoria e reconciliação semântica")
    st.caption(
        "Significado/método distinto exige conceito distinto. Decisão A/B fica na revisão "
        "do rascunho: não muda fontes, projeções históricas ou IFC. Nome declarado não autentica."
    )
    kinds = {
        "Conceito": "concepts",
        "Unidade": "units",
        "Domínio de valores": "value_sets",
        "Alias": "aliases",
        "Decisão A/B": "reconciliation_decisions",
    }
    label = st.selectbox("Entidade semântica", list(kinds), key="catalog_sem_kind")
    kind = kinds[label]
    entities = {e.id: e for e in getattr(content, kind)}
    chosen = st.selectbox(
        "Registro semântico",
        ["(novo)", *entities],
        key=f"catalog_sem_pick_{kind}",
        format_func=lambda value: (
            "(novo)"
            if value == "(novo)"
            else str(getattr(entities[value], "code", getattr(entities[value], "term", value)))
            + f" — {value}"
        ),
    )
    entity = entities.get(chosen)
    # Identity-specific keys retain edits across conflict reruns; no revision-dependent resets.
    prefix = f"catalog_sem_{draft.draft_id}_{kind}_{chosen}"

    def key(field: str) -> str:
        return f"{prefix}_{field}"

    def value(field: str, default: Any = "") -> Any:
        return getattr(entity, field, default) if entity is not None else default

    baseline_key = f"{prefix}_baseline"
    if entity is not None and baseline_key not in st.session_state:
        st.session_state[baseline_key] = entity.model_dump(mode="json")
    fields: dict[str, Any] = {}
    with st.form(f"{prefix}_form"):
        if kind == "concepts":
            fields["code"] = st.text_input(
                "Código do conceito", value=value("code"), key=key("code")
            )
            title = st.text_input("Rótulo (pt-BR)", value=_text(entity, "labels"), key=key("label"))
            definition = st.text_area(
                "Definição (pt-BR)", value=_text(entity, "definition"), key=key("definition")
            )
            fields["labels"] = _localized(entity, "labels", title)
            fields["definition"] = _localized(entity, "definition", definition)
            fields["logical_type"] = _pick(
                "Tipo lógico", list(get_args(LogicalType)), value("logical_type"), key("type")
            )
            fields["dimension"] = (
                _pick(
                    "Dimensão declarada",
                    ["", *get_args(Dimension)],
                    value("dimension"),
                    key("dimension"),
                )
                or None
            )
            fields["unit_id"] = (
                _pick(
                    "Unidade do conceito",
                    ["", *[u.id for u in content.units]],
                    value("unit_id"),
                    key("unit"),
                )
                or None
            )
            fields["value_set_id"] = (
                _pick(
                    "Domínio do conceito",
                    ["", *[v.id for v in content.value_sets]],
                    value("value_set_id"),
                    key("values"),
                )
                or None
            )
        elif kind == "units":
            fields["symbol"] = st.text_input("Símbolo", value=value("symbol"), key=key("symbol"))
            fields["dimension"] = _pick(
                "Dimensão da unidade",
                list(get_args(Dimension)),
                value("dimension"),
                key("dimension"),
            )
            fields["reference"] = (
                st.text_input(
                    "Referência da unidade", value=value("reference") or "", key=key("reference")
                )
                or None
            )
        elif kind == "value_sets":
            fields["value_type"] = _pick(
                "Tipo dos valores",
                ["code", "string", "integer", "boolean"],
                value("value_type"),
                key("type"),
            )
            raw = st.text_area(
                "Valores permitidos (um por linha; booleanos: true/false)",
                value="\n".join(
                    str(v.code).lower() if isinstance(v.code, bool) else str(v.code)
                    for v in value("values", ())
                ),
                key=key("values"),
            )
            fields["ordered"] = st.checkbox(
                "Ordem significativa", value=value("ordered", False), key=key("ordered")
            )
            fields["restricts_value_set_id"] = (
                _pick(
                    "Restringe domínio",
                    ["", *[v.id for v in content.value_sets if v.id != chosen]],
                    value("restricts_value_set_id"),
                    key("restricts"),
                )
                or None
            )
        elif kind == "aliases":
            fields["term"] = st.text_input("Termo do alias", value=value("term"), key=key("term"))
            fields["lang"] = (
                st.text_input(
                    "Idioma do alias (opcional)", value=value("lang") or "", key=key("lang")
                )
                or None
            )
            fields["purpose"] = _pick(
                "Finalidade do alias",
                list(get_args(AliasPurpose)),
                value("purpose"),
                key("purpose"),
            )
            targets = {e.id: "binding" for e in content.bindings}
            targets.update({e.id: "conceito" for e in content.concepts})
            target = _pick(
                "Alvo do alias",
                ["", *targets],
                value("target_binding_id") or value("target_concept_id"),
                key("target"),
            )
            fields["target_binding_id"] = target if targets.get(target) == "binding" else None
            fields["target_concept_id"] = target if targets.get(target) == "conceito" else None
            scope = value("scope", None)
            fields["scope"] = {}
            for field, title in [
                ("set_names", "Conjuntos do alias"),
                ("entity_classes", "Classes do alias"),
                ("schemas", "Schemas do alias"),
            ]:
                selected = st.text_input(
                    f"{title} (vírgulas)",
                    value=", ".join(getattr(scope, field, None) or ()),
                    key=key(field),
                )
                fields["scope"][field] = [
                    s.strip() for s in selected.split(",") if s.strip()
                ] or None
        else:
            fields["code"] = st.text_input(
                "Código da decisão", value=value("code"), key=key("code")
            )
            fields["status"] = _pick(
                "Estado da decisão",
                ["pending", "decided", "rejected"],
                value("status"),
                key("status"),
            )
            fields["summary"] = st.text_area(
                "Divergência A/B", value=value("summary"), key=key("summary")
            )
            fields["proposal"] = (
                st.text_area(
                    "Proposta de reconciliação", value=value("proposal") or "", key=key("proposal")
                )
                or None
            )
            fields["justification"] = (
                st.text_area(
                    "Fundamento da decisão",
                    value=value("justification") or "",
                    key=key("justification"),
                )
                or None
            )
            fields["affected_binding_ids"] = st.multiselect(
                "Usos afetados",
                [b.id for b in content.bindings],
                default=list(value("affected_binding_ids", ())),
                key=key("bindings"),
            )
        if kind != "units":
            fields["source_assertion_ids"] = st.multiselect(
                "Assertivas de origem",
                [a.id for a in content.source_assertions],
                default=list(value("source_assertion_ids", ())),
                key=key("sources"),
            )
        reason = st.text_input("Motivo da alteração semântica", key=key("reason"))
        submitted = st.form_submit_button("Salvar proposta semântica")
        if submitted:
            if kind == "value_sets":
                try:
                    codes: list[Any] = [line for line in raw.splitlines() if line]
                    if fields["value_type"] == "integer":
                        codes = [int(c) for c in codes]
                    elif fields["value_type"] == "boolean":
                        if any(c not in ("true", "false") for c in codes):
                            raise ValueError("Use apenas true ou false para booleanos.")
                        codes = [c == "true" for c in codes]
                    old_values = {(type(v.code), v.code): v for v in value("values", ())}
                    fields["values"] = [
                        old_values[(type(c), c)].model_dump(mode="json")
                        if (type(c), c) in old_values
                        else {"code": c}
                        for c in codes
                    ]
                except ValueError:
                    st.error("Valores incompatíveis com o tipo declarado; confira as linhas.")
                    return
            if entity is None:
                run_action(
                    "semantic_add",
                    lambda command: ws.add_entity(
                        session,
                        command_id=command,
                        fields=fields,
                        draft_id=draft.draft_id,
                        expected_revision=draft.revision,
                        kind=kind,
                        reason=reason,
                    ),
                )
            else:
                baseline = st.session_state[baseline_key]
                fields = {name: data for name, data in fields.items() if data != baseline[name]}
                if not fields:
                    st.info("Nenhuma alteração semântica informada.")
                    return

                def save_edit(command: str) -> ActionReceipt:
                    receipt = ws.edit_entity(
                        session,
                        command_id=command,
                        entity_id=chosen,
                        changes=fields,
                        draft_id=draft.draft_id,
                        expected_revision=draft.revision,
                        kind=kind,
                        reason=reason,
                    )
                    st.session_state[baseline_key] = {**baseline, **fields}
                    return receipt

                run_action("semantic_edit", save_edit)
    if kind == "reconciliation_decisions":
        for decision in content.reconciliation_decisions:
            safe_text(
                "Decisão registrada", f"{decision.code}: {decision.status} — {decision.summary}"
            )
