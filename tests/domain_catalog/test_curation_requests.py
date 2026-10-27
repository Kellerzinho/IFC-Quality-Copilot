"""Solicitações de cadastro/mapeamento e o executor de comandos (E2, M1-08).

Atores, catálogo e solicitações são SINTÉTICOS, gravados pelo adaptador de teste não
operacional. Verifica estado explícito da solicitação, ator declarado em cada evento,
idempotência por chave de comando e ausência de efeito parcial quando algo falha.
"""

from pathlib import Path

import pytest

from src.domain_catalog.curation import CurationService
from src.domain_catalog.curation_errors import (
    ActorContextError,
    ActorNotAllowedError,
    CommandValidationError,
    CurationNotFoundError,
    IdempotencyConflictError,
    InvalidTransitionError,
)
from src.domain_catalog.curation_models import (
    ChangeRequest,
    CommandMeta,
    CommandOutcome,
    OriginRef,
    RequestedField,
)
from src.domain_catalog.draft_store import StoreUnavailableError
from tests.domain_catalog.curation_adapters import CurationEnv, make_env

CATALOG = "urn:uuid:00000000-0000-4000-8000-0000000000e2"
FIELD = RequestedField(
    ifc_schema="IFC4",
    facet="property",
    entity="IfcSlab",
    set_name="SYN_Conjunto",
    field_name="SYN_Novo",
)
IDS_REF = OriginRef(kind="ids_requirement", ref="sha256:abc/especificacao[2]/propriedade[1]")


@pytest.fixture
def env(tmp_path: Path) -> CurationEnv:
    return make_env(tmp_path)


def _request(
    env: CurationEnv, command_id: str = "cmd-req-0001", actor: str | None = None
) -> CommandOutcome[ChangeRequest]:
    return env.curation.request_change(
        CommandMeta(command_id=command_id, actor_context_id=actor or env.operator),
        catalog_id=CATALOG,
        motivation="IDS fornecido exige campo sem cadastro no catálogo.",
        field=FIELD,
        origin_refs=(IDS_REF,),
    )


def test_operator_request_is_open_and_linked_to_its_ids_requirement(env: CurationEnv) -> None:
    outcome = _request(env)
    request = outcome.value

    assert request.state == "open"
    assert request.field == FIELD
    assert request.origin_refs == (IDS_REF,)
    assert request.requested_by.declared_name == "Pessoa Operadora Sintética"
    assert request.requested_by.identity_assurance == "unverified_local"
    assert outcome.receipt.store_operational is False
    assert outcome.replayed is False
    assert env.curation.get_request(request.request_id) == request


def test_every_request_command_records_one_event_with_the_declared_actor(env: CurationEnv) -> None:
    outcome = _request(env)

    events = env.curation.events()

    assert len(events) == 1
    event = events[0]
    assert (event.subject_kind, event.subject_id) == ("request", outcome.value.request_id)
    assert (event.from_state, event.to_state) == (None, "open")
    assert event.command_id == "cmd-req-0001"
    assert event.actor.actor_context_id == env.operator
    assert outcome.receipt.event_seqs == (event.seq,)


def test_assistant_may_suggest_a_request_and_its_origin_stays_visible(env: CurationEnv) -> None:
    request = _request(env, actor=env.assistant).value

    assert request.requested_by.actor_kind == "assistant"
    assert request.state == "open"


def test_service_actor_cannot_open_a_request_and_nothing_is_recorded(env: CurationEnv) -> None:
    with pytest.raises(ActorNotAllowedError):
        _request(env, actor=env.importer)

    assert env.curation.list_requests() == ()
    assert env.curation.events() == ()


def test_unknown_actor_context_is_refused_without_effect(env: CurationEnv) -> None:
    with pytest.raises(ActorContextError, match="ctx-inexistente"):
        _request(env, actor="ctx-inexistente")

    assert env.curation.events() == ()


def test_context_claiming_authentication_is_refused(env: CurationEnv) -> None:
    forged = env.actors.register(
        "human",
        "Pessoa sintética",
        identity_assurance="authenticated",
        actor_context_id="ctx-forjado",
    )

    with pytest.raises(ActorContextError, match="identity_assurance"):
        _request(env, actor=forged)


def test_repeating_a_command_returns_the_same_receipt_without_new_effects(env: CurationEnv) -> None:
    first = _request(env)
    again = _request(env)

    assert again.replayed is True
    assert again.receipt == first.receipt
    assert again.value == first.value
    assert len(env.curation.list_requests()) == 1
    assert len(env.curation.events()) == 1


def test_same_command_id_with_different_payload_is_a_conflict(env: CurationEnv) -> None:
    _request(env)

    with pytest.raises(IdempotencyConflictError):
        env.curation.request_change(
            CommandMeta(command_id="cmd-req-0001", actor_context_id=env.operator),
            catalog_id=CATALOG,
            motivation="Outro motivo, mesma chave.",
            field=FIELD,
        )

    assert len(env.curation.list_requests()) == 1


def test_same_command_id_from_another_actor_is_a_conflict(env: CurationEnv) -> None:
    _request(env)

    with pytest.raises(IdempotencyConflictError):
        _request(env, actor=env.curator)


def test_command_lookup_resolves_a_lost_response(env: CurationEnv) -> None:
    outcome = _request(env)

    record = env.curation.get_command("cmd-req-0001")

    assert record is not None
    assert record.state == "completed"
    assert record.receipt == outcome.receipt
    assert env.curation.get_command("cmd-nunca-enviado") is None


def test_blank_motivation_is_an_invalid_command(env: CurationEnv) -> None:
    with pytest.raises(CommandValidationError, match="motivation"):
        env.curation.request_change(
            CommandMeta(command_id="cmd-req-0002", actor_context_id=env.operator),
            catalog_id=CATALOG,
            motivation="",
            field=FIELD,
        )

    assert env.curation.events() == ()


def test_triage_moves_open_request_to_in_triage(env: CurationEnv) -> None:
    request = _request(env).value

    triaged = env.curation.triage_request(
        CommandMeta(command_id="cmd-tri-0001", actor_context_id=env.curator),
        request_id=request.request_id,
        reason="Campo pertence ao perfil de orçamento.",
    ).value

    assert triaged.state == "in_triage"
    assert [e.to_state for e in env.curation.events()] == ["open", "in_triage"]


def test_rejection_requires_a_declared_responsible(env: CurationEnv) -> None:
    request = _request(env).value
    anonymous = env.actors.register("human", None)

    with pytest.raises(ActorNotAllowedError, match="responsável declarado"):
        env.curation.reject_request(
            CommandMeta(command_id="cmd-rej-0001", actor_context_id=anonymous),
            request_id=request.request_id,
            justification="Fora do escopo do perfil.",
        )

    assert env.curation.get_request(request.request_id).state == "open"


def test_rejected_request_keeps_justification_and_is_terminal(env: CurationEnv) -> None:
    request = _request(env).value
    rejected = env.curation.reject_request(
        CommandMeta(command_id="cmd-rej-0002", actor_context_id=env.curator),
        request_id=request.request_id,
        justification="Campo duplica conceito existente; usar o cadastro atual.",
    ).value

    assert rejected.state == "rejected"
    assert rejected.closing_reason == "Campo duplica conceito existente; usar o cadastro atual."
    with pytest.raises(InvalidTransitionError):
        env.curation.cancel_request(
            CommandMeta(command_id="cmd-can-0001", actor_context_id=env.operator),
            request_id=request.request_id,
            reason="Desisti.",
        )


@pytest.mark.parametrize(
    ("first", "second"),
    [("cancel", "triage"), ("cancel", "reject"), ("reject", "triage"), ("triage", "triage")],
)
def test_transitions_out_of_place_are_refused(env: CurationEnv, first: str, second: str) -> None:
    request = _request(env).value

    def run(action: str, n: int) -> None:
        meta = CommandMeta(command_id=f"cmd-{action}-{n:04d}", actor_context_id=env.curator)
        if action == "cancel":
            env.curation.cancel_request(meta, request_id=request.request_id, reason="motivo")
        elif action == "reject":
            env.curation.reject_request(
                meta, request_id=request.request_id, justification="justificativa"
            )
        else:
            env.curation.triage_request(meta, request_id=request.request_id, reason="motivo")

    run(first, 1)
    before = env.curation.get_request(request.request_id)
    with pytest.raises(InvalidTransitionError):
        run(second, 2)

    assert env.curation.get_request(request.request_id) == before


def test_unknown_request_is_not_found(env: CurationEnv) -> None:
    with pytest.raises(CurationNotFoundError):
        env.curation.triage_request(
            CommandMeta(command_id="cmd-tri-0009", actor_context_id=env.curator),
            request_id="urn:uuid:00000000-0000-4000-8000-00000000dead",
            reason="motivo",
        )


def test_list_requests_filters_by_state_for_the_curation_table(env: CurationEnv) -> None:
    first = _request(env, "cmd-req-0001").value
    second = _request(env, "cmd-req-0003").value
    env.curation.triage_request(
        CommandMeta(command_id="cmd-tri-0001", actor_context_id=env.curator),
        request_id=second.request_id,
        reason="motivo",
    )

    assert [r.request_id for r in env.curation.list_requests(state="open")] == [first.request_id]
    assert [r.request_id for r in env.curation.list_requests(state="in_triage")] == [
        second.request_id
    ]


def test_requests_and_events_survive_a_restart(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    request = _request(env).value

    restarted = make_env(tmp_path)

    assert restarted.curation.get_request(request.request_id) == request
    assert [e.to_state for e in restarted.curation.events()] == ["open"]


def test_commit_failure_leaves_no_request_event_or_command_and_retry_works(
    tmp_path: Path,
) -> None:
    env = make_env(tmp_path, fail_at={"before_commit"})

    with pytest.raises(StoreUnavailableError):
        _request(env)

    env.store.fail_at.clear()
    assert env.curation.list_requests() == ()
    assert env.curation.events() == ()
    assert env.curation.get_command("cmd-req-0001") is None
    retried = _request(env)
    assert retried.replayed is False
    assert retried.value.state == "open"


def test_service_constructor_requires_the_ports(tmp_path: Path) -> None:
    env = make_env(tmp_path)

    service = CurationService(env.store, env.actors, clock=env.clock, new_id=env.new_id)

    assert service.list_requests() == ()


def test_same_declared_name_in_two_contexts_stays_two_unverified_identifications(
    env: CurationEnv,
) -> None:
    first = env.actors.register("human", "Pessoa sintética", actor_context_id="ctx-sintetico-a")
    second = env.actors.register("human", "Pessoa sintética", actor_context_id="ctx-sintetico-b")

    a = _request(env, "cmd-req-0101", first).value.requested_by
    b = _request(env, "cmd-req-0102", second).value.requested_by

    assert (a.declared_name, b.declared_name) == ("Pessoa sintética", "Pessoa sintética")
    assert a.actor_context_id != b.actor_context_id
    assert {a.identity_assurance, b.identity_assurance} == {"unverified_local"}
    assert a.responsible_label == "identificação informada: Pessoa sintética (não autenticada)"
