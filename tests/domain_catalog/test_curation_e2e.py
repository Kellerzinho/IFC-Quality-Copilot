"""Demonstração vertical da E2 (plano M1 §11): solicitação → rascunho → curador →
pacote publicado → reabertura sem rede.

Conteúdo e atores SINTÉTICOS (``SYN_*``) sobre os adaptadores de teste não
operacionais. O release publicado aqui é fixture de teste, rotulado
``synthetic_fixture``, numa pasta temporária: não é catálogo real nem integração com o
M6. Todo socket e toda resolução de nome falham o teste durante o percurso inteiro.
"""

import socket
import subprocess
import sys
from pathlib import Path

import pytest

from src.config import BASE_DIR
from src.domain_catalog.contracts import BindingRequest
from src.domain_catalog.curation_models import (
    CommandMeta,
    DraftPatch,
    OriginRef,
    RequestedField,
    UpsertEntity,
)
from src.domain_catalog.package import ComponentTerms
from tests.domain_catalog import factories as f
from tests.domain_catalog.curation_adapters import make_env

_FORBIDDEN_MODULES = (
    "httpx",
    "ollama",
    "src.bsdd",
    "src.semantic_registry",
    "src.suggestion_engine",
    "src.pipeline",
)


def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("a curadoria tentou acessar a rede")

    monkeypatch.setattr(socket.socket, "connect", _no_network)
    monkeypatch.setattr(socket, "create_connection", _no_network)
    monkeypatch.setattr(socket, "getaddrinfo", _no_network)


def _meta(command_id: str, actor: str) -> CommandMeta:
    return CommandMeta(command_id=command_id, actor_context_id=actor)


def _upsert(kind: str, entity: object) -> UpsertEntity:
    return UpsertEntity(op="upsert", kind=kind, entity=entity.model_dump(mode="json"))  # type: ignore[arg-type, attr-defined]


def test_request_to_published_release_reopened_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _block_network(monkeypatch)
    env = make_env(tmp_path)

    # 1. Operador pede mapeamento para campo de um IDS (referência, sem copiar o IDS).
    request = env.curation.request_change(
        _meta("cmd-e2e-01", env.operator),
        catalog_id=f.SYN_CATALOG_ID,
        motivation="IDS exige SYN_Metodo em lajes; o catálogo não tem o campo.",
        field=RequestedField(
            ifc_schema="IFC4",
            facet="property",
            entity="IfcSlab",
            set_name="SYN_Conjunto",
            field_name="SYN_Metodo",
        ),
        origin_refs=(OriginRef(kind="ids_requirement", ref="sha256:sintetico/especificacao[1]"),),
    ).value
    env.curation.triage_request(
        _meta("cmd-e2e-02", env.curator), request_id=request.request_id, reason="assumida"
    )

    # 2. Curador abre o rascunho e o assistente propõe o cadastro (proposta identificada).
    head = env.curation.create_draft(
        _meta("cmd-e2e-03", env.curator),
        title="Primeiro release sintético",
        catalog=f.catalog_identity(),
        request_ids=(request.request_id,),
        reason="atender a solicitação",
    ).value
    proposal = DraftPatch(
        operations=(
            _upsert("source_artifacts", f.source_artifact()),
            _upsert("source_assertions", f.source_assertion()),
            _upsert("value_sets", f.value_set("draft")),
            _upsert("concepts", f.concept("draft")),
            _upsert("applicability_rules", f.rule("draft")),
            _upsert("bindings", f.binding("draft")),
        ),
        reason="cadastro proposto a partir da linha sintética",
    )
    head = env.curation.edit_draft(
        _meta("cmd-e2e-04", env.assistant),
        draft_id=head.draft.draft_id,
        expected_revision=1,
        patch=proposal,
    ).value
    assert env.curation.get_revision(head.draft.draft_id, 2).origin == "assistant_proposal"

    # 3. Validação, revisão e aprovação humanas da revisão exata.
    assert env.curation.validate_draft(head.draft.draft_id).passed
    env.curation.submit_for_review(
        _meta("cmd-e2e-05", env.curator),
        draft_id=head.draft.draft_id,
        revision=head.revision,
        content_sha256=head.content_sha256,
        reason="pronto para revisão",
    )
    approval = env.curation.review_draft(
        _meta("cmd-e2e-06", env.curator),
        draft_id=head.draft.draft_id,
        revision=head.revision,
        content_sha256=head.content_sha256,
        verdict="approve",
        justification="Definição e uso sintéticos conferidos para o teste.",
    ).value

    # 4. Candidato exato e publicação explícita.
    candidate = env.publication.prepare_release(
        _meta("cmd-e2e-07", env.curator),
        draft_id=head.draft.draft_id,
        revision=head.revision,
        content_sha256=head.content_sha256,
        version="1.0.0",
        terms=(ComponentTerms(component="conteúdo", terms="sintético, sem terceiros"),),
        reason="preparar release",
    ).value
    receipt = env.publication.publish(
        _meta("cmd-e2e-08", env.curator),
        candidate_id=candidate.candidate_id,
        version=candidate.release.version,
        manifest_sha256=candidate.release.manifest_sha256,
        justification="Publicação sintética de teste.",
    ).value

    # 5. Reabertura pelo release exato, sem rede, e consulta resolvida.
    reader = env.publication.open_published(receipt.release)
    result = reader.resolve_binding(
        BindingRequest(
            ifc_schema="IFC4",
            facet="property",
            set_name="SYN_Conjunto",
            field_name="SYN_Metodo",
            entity="IfcSlab",
        )
    )

    assert result.status == "exact"
    assert result.catalog == receipt.release
    assert receipt.approval_id == approval.review_id
    assert receipt.content_origin == "synthetic_fixture"
    assert (receipt.store_operational, receipt.artifact_store_operational) == (False, False)
    closed = env.curation.get_request(request.request_id)
    assert (closed.state, closed.published_release) == ("approved", receipt.release)
    trail = [(e.subject_kind, e.to_state) for e in env.curation.events()]
    for step in [
        ("request", "open"),
        ("request", "in_triage"),
        ("draft", "editing"),
        ("draft", "in_review"),
        ("review", "approve"),
        ("draft", "approved"),
        ("candidate", "prepared"),
        ("intent", "recorded"),
        ("publication", "published"),
        ("draft", "published"),
    ]:
        assert step in trail


def test_curation_modules_do_not_import_network_or_legacy_semantics() -> None:
    code = (
        "import sys\n"
        "import src.domain_catalog.curation, src.domain_catalog.publication\n"
        "import src.domain_catalog.curation_validation, src.domain_catalog.actor\n"
        "import src.domain_catalog.draft_store\n"
        f"print(','.join(m for m in {_FORBIDDEN_MODULES!r} if m in sys.modules))\n"
    )

    loaded = subprocess.run(
        [sys.executable, "-c", code], cwd=BASE_DIR, capture_output=True, text=True, check=True
    ).stdout.strip()

    assert loaded == ""
