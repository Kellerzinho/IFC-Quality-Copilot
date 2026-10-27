"""Contexto de ator local declarado (E2, fronteira M1/M6).

Os contextos aqui são SINTÉTICOS e criados pelo diretório de teste, que faz o papel
do backend (M6, ainda não implementado). Nome declarado não é identidade autenticada:
os testes verificam que o catálogo nunca promove a garantia nem aceita papel ou
identidade enviados como texto livre.
"""

from dataclasses import dataclass

import pytest

from src.domain_catalog.actor import (
    ActorSnapshot,
    authorize,
    snapshot_actor,
)
from src.domain_catalog.curation_errors import ActorContextError, ActorNotAllowedError


@dataclass(frozen=True)
class _Context:
    """Contexto mínimo com a forma estrutural proposta ao M6 (atributos somente leitura)."""

    actor_context_id: str = "ctx-001"
    installation_id: str = "inst-teste"
    session_id: str = "sessao-1"
    actor_kind: str = "human"
    declared_name: str | None = "Pessoa Sintética"
    identity_assurance: str = "unverified_local"
    registered_at_utc: str = "2026-10-14T12:00:00Z"


def test_snapshot_keeps_declared_name_as_unverified_local_identity() -> None:
    snapshot = snapshot_actor(_Context())

    assert snapshot.identity_assurance == "unverified_local"
    assert snapshot.declared_name == "Pessoa Sintética"
    assert snapshot.responsible_label == (
        "identificação informada: Pessoa Sintética (não autenticada)"
    )


def test_snapshot_without_name_is_an_unidentified_local_operator() -> None:
    snapshot = snapshot_actor(_Context(declared_name=None))

    assert snapshot.declared_name is None
    assert snapshot.responsible_label == "operador local não identificado (não autenticado)"


@pytest.mark.parametrize("assurance", ["authenticated", "verified", "", "UNVERIFIED_LOCAL"])
def test_identity_assurance_other_than_unverified_local_is_refused(assurance: str) -> None:
    with pytest.raises(ActorContextError, match="identity_assurance"):
        snapshot_actor(_Context(identity_assurance=assurance))


@pytest.mark.parametrize("kind", ["admin", "curator", "llm", "Human"])
def test_actor_kind_outside_the_contract_is_refused(kind: str) -> None:
    with pytest.raises(ActorContextError, match="actor_kind"):
        snapshot_actor(_Context(actor_kind=kind))


@pytest.mark.parametrize("registered", ["2026-10-14 12:00:00", "2026-10-14T12:00:00+00:00", ""])
def test_registration_instant_must_be_utc(registered: str) -> None:
    with pytest.raises(ActorContextError, match="registered_at_utc"):
        snapshot_actor(_Context(registered_at_utc=registered))


@pytest.mark.parametrize("name", ["", "   ", "\t"])
def test_blank_declared_name_is_not_a_declaration(name: str) -> None:
    with pytest.raises(ActorContextError, match="declared_name"):
        snapshot_actor(_Context(declared_name=name))


def test_object_without_the_contract_shape_is_refused() -> None:
    class _Partial:
        actor_context_id = "ctx-x"

    with pytest.raises(ActorContextError):
        snapshot_actor(_Partial())  # type: ignore[arg-type]


def _snap(**changes: object) -> ActorSnapshot:
    return snapshot_actor(_Context(**changes))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "operation",
    ["review_draft", "prepare_release", "publish", "resume_publication", "abandon_publication"],
)
@pytest.mark.parametrize("kind", ["assistant", "service"])
def test_assistant_and_service_never_approve_or_publish(operation: str, kind: str) -> None:
    with pytest.raises(ActorNotAllowedError, match=kind):
        authorize(operation, _snap(actor_kind=kind, declared_name="Pessoa sintética"))


@pytest.mark.parametrize("operation", ["review_draft", "prepare_release", "publish"])
def test_human_without_declared_name_cannot_decide_or_publish(operation: str) -> None:
    with pytest.raises(ActorNotAllowedError, match="responsável declarado"):
        authorize(operation, _snap(declared_name=None))


@pytest.mark.parametrize("operation", ["review_draft", "prepare_release", "publish"])
def test_human_with_declared_name_may_decide_and_publish(operation: str) -> None:
    authorize(operation, _snap())


def test_assistant_may_propose_but_not_submit_for_review() -> None:
    assistant = _snap(actor_kind="assistant", declared_name=None)

    authorize("request_change", assistant)
    authorize("edit_draft", assistant)
    with pytest.raises(ActorNotAllowedError):
        authorize("submit_for_review", assistant)


def test_service_may_import_a_draft_but_not_edit_it() -> None:
    importer = _snap(actor_kind="service", declared_name=None)

    authorize("import_draft", importer)
    with pytest.raises(ActorNotAllowedError):
        authorize("edit_draft", importer)


def test_unknown_operation_is_never_authorized() -> None:
    with pytest.raises(ActorNotAllowedError, match="operação desconhecida"):
        authorize("approve_everything", _snap())
