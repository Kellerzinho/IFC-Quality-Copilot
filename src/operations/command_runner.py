"""Executor dos comandos operacionais de transação única (M6 mínimo).

Ordem fixa: (1) o envelope precisa representar exatamente operação, projeto e
argumentos; (2) a chave é consultada **antes** de ator e de qualquer CAS, para que a
repetição idêntica devolva o recibo original mesmo depois de mudanças posteriores;
(3) o ator é resolvido na autoridade comum e conferido; (4) numa única transação:
nova consulta da chave, reserva no índice global, efeito, eventos, recibo e conclusão
do comando. Qualquer falha desfaz tudo. Mesma chave com qualquer diferença, ou de
outro namespace, é ``idempotency_conflict``.
"""

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from src.domain_catalog.actor import ActorSnapshot
from src.domain_catalog.curation import utc_now
from src.domain_catalog.curation_errors import IdempotencyConflictError
from src.operations.actor_context import ActorContextService
from src.operations.contracts import (
    ActorKindRequirement,
    OperationalCommand,
    OperationalError,
    OperationalReceipt,
    OperationName,
    ResultingRef,
    command_payload_sha256,
    new_uuid,
)
from src.operations.database import OperationalStore, OperationalUnitOfWork, StoreBusyError


@dataclass
class Effect:
    """Efeito de domínio de um comando: estado, refs, eventos e resultado opcional."""

    status: Literal["applied", "noop"]
    refs: tuple[ResultingRef, ...]
    events: tuple[Mapping[str, Any], ...]
    finalize: Callable[[OperationalReceipt], BaseModel] | None = None
    result: dict[str, Any] | None = field(default=None, init=False)


@dataclass(frozen=True)
class RunOutcome:
    """Recibo operacional, resultado específico gravado (se houver) e se foi replay."""

    receipt: OperationalReceipt
    result: dict[str, Any] | None
    replayed: bool


def record_ref(operation: str, command_id: uuid.UUID) -> str:
    """Referência de registro de um comando de operações no índice global."""
    return f"operations/{operation}/{command_id}"


class OperationalRunner:
    """Executa comandos com envelope verificado, replay, ator e efeito atômicos."""

    def __init__(
        self,
        store: OperationalStore,
        *,
        clock: Callable[[], str] = utc_now,
        new_id: Callable[[], uuid.UUID] = new_uuid,
    ) -> None:
        """Autoridade comum, resolver de atores, relógio UTC e gerador de IDs."""
        self.store = store
        self.actors = ActorContextService(store, clock=clock)
        self.clock = clock
        self.new_id = new_id

    @staticmethod
    def verify_envelope(
        command: OperationalCommand,
        *,
        operation: OperationName,
        project_id: uuid.UUID | None,
        arguments: Mapping[str, Any],
    ) -> None:
        """O envelope representa exatamente o pedido; senão ``invalid_command``."""
        if command.operation != operation:
            raise OperationalError(
                "invalid_command", f"envelope de {command.operation}, chamada de {operation}"
            )
        if command.project_id != project_id:
            raise OperationalError("invalid_command", "projeto do envelope difere do pedido")
        digest = command_payload_sha256(
            operation=operation,
            actor_context_id=str(command.actor_context_id),
            project_id=project_id,
            arguments=arguments,
        )
        if digest != command.payload_sha256:
            raise OperationalError(
                "invalid_command",
                "payload_sha256 não representa os argumentos recebidos",
                expected=command.payload_sha256,
                actual=digest,
            )

    @staticmethod
    def replay(uow: OperationalUnitOfWork, command: OperationalCommand) -> RunOutcome | None:
        """Recibo original da mesma chave e conteúdo; diferença é conflito."""
        row = uow.commands.get(str(command.command_id))
        if row is None:
            return None
        if row.namespace != "operations" or (
            row.operation,
            row.payload_sha256,
            row.actor_context_id,
        ) != (command.operation, command.payload_sha256, str(command.actor_context_id)):
            raise OperationalError(
                "idempotency_conflict",
                f"chave {command.command_id} já usada por {row.namespace}/{row.operation}",
            )
        if row.state == "in_progress":
            raise OperationalError(
                "analysis_in_progress", f"comando {command.command_id} ainda em execução"
            )
        if row.state == "abandoned" or row.receipt is None:
            raise OperationalError(
                "analysis_interrupted",
                f"comando {command.command_id} foi interrompido; use uma operação nova",
            )
        try:
            receipt = OperationalReceipt.model_validate(row.receipt["receipt"])
        except (KeyError, ValidationError) as exc:
            raise OperationalError("integrity_error", "recibo gravado inválido") from exc
        if receipt.command_id != command.command_id:
            raise OperationalError("integrity_error", "recibo gravado de outro comando")
        return RunOutcome(receipt=receipt, result=row.receipt.get("result"), replayed=True)

    def lookup(self, command: OperationalCommand) -> RunOutcome | None:
        """Consulta prévia da chave, antes de ator e de pré-condições mutáveis."""
        with self.store.transaction() as uow:
            return self.replay(uow, command)

    def run(
        self,
        command: OperationalCommand,
        *,
        operation: OperationName,
        project_id: uuid.UUID | None,
        arguments: Mapping[str, Any],
        requirement: ActorKindRequirement,
        body: Callable[[OperationalUnitOfWork, ActorSnapshot, str], Effect],
    ) -> RunOutcome:
        """Executa o comando numa transação; replay devolve o recibo original."""
        self.verify_envelope(
            command, operation=operation, project_id=project_id, arguments=arguments
        )
        try:
            found = self.lookup(command)
            if found is not None:
                return found
            actor = self.actors.require(str(command.actor_context_id), requirement=requirement)
            with self.store.transaction() as uow:
                found = self.replay(uow, command)
                if found is not None:
                    return found
                uow.commands.reserve(
                    command_id=str(command.command_id),
                    namespace="operations",
                    operation=operation,
                    payload_sha256=command.payload_sha256,
                    actor_context_id=str(command.actor_context_id),
                    record_ref=record_ref(operation, command.command_id),
                )
                now = self.clock()
                effect = body(uow, actor, now)
                if not effect.events:
                    raise OperationalError("invalid_command", "comando sem evento registrado")
                seqs = tuple(
                    uow.events.append(
                        "operations",
                        {
                            **event,
                            "operation": operation,
                            "command_id": str(command.command_id),
                            "project_id": None if project_id is None else str(project_id),
                            "actor_context_id": actor.actor_context_id,
                            "at_utc": now,
                        },
                    )
                    for event in effect.events
                )
                receipt = OperationalReceipt(
                    receipt_id=self.new_id(),
                    command_id=command.command_id,
                    operation=operation,
                    status=effect.status,
                    actor_snapshot=actor,
                    project_id=project_id,
                    resulting_refs=effect.refs,
                    event_sequence=seqs,
                    committed_at_utc=now,
                    payload_sha256=command.payload_sha256,
                )
                result = None if effect.finalize is None else effect.finalize(receipt)
                result_doc = None if result is None else result.model_dump(mode="json")
                uow.commands.complete(
                    str(command.command_id),
                    {"receipt": receipt.model_dump(mode="json"), "result": result_doc},
                )
            return RunOutcome(receipt=receipt, result=result_doc, replayed=False)
        except IdempotencyConflictError as exc:
            raise OperationalError("idempotency_conflict", str(exc)) from exc
        except StoreBusyError as exc:
            raise OperationalError("store_busy", str(exc)) from exc
