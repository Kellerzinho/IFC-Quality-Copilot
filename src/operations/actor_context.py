"""Contexto de ator local persistido (concretiza a porta ``ActorContext`` da E2).

O contexto é criado e resgatado pelo backend local: instalação, sessão, tipo de ator
(``human``, ``assistant`` ou ``service``), nome declarado opcional e garantia
``unverified_local``. Uma string de nome nunca autentica pessoa; não há contas. O
comando referencia o contexto por ID, e o ID é resolvido nesta mesma tabela tanto
pela curadoria (E2) quanto pelas operações (E3); ``ActorSnapshot`` vindo do chamador
nunca é aceito como prova.
"""

import uuid
from collections.abc import Callable
from typing import Annotated, Literal

from pydantic import StringConstraints, ValidationError

from src.domain_catalog.actor import ActorKind, ActorSnapshot, DeclaredName, snapshot_actor
from src.domain_catalog.contracts import ContractModel
from src.domain_catalog.curation import utc_now
from src.domain_catalog.curation_errors import ActorContextError
from src.domain_catalog.package import UtcTimestamp
from src.operations.contracts import (
    ActorKindRequirement,
    OperationalError,
    OperationalErrorReason,
    SchemaVersionOne,
    new_uuid,
)
from src.operations.database import OperationalStore

UuidText = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
]

_ALLOWED: dict[str, frozenset[str]] = {
    "human": frozenset({"human"}),
    "human_or_service": frozenset({"human", "service"}),
    "any": frozenset({"human", "assistant", "service"}),
}


class LocalActorContext(ContractModel):
    """Contexto local declarado; satisfaz o protocolo ``ActorContext`` da E2."""

    schema_version: SchemaVersionOne = 1
    actor_context_id: UuidText
    installation_id: UuidText
    session_id: UuidText
    actor_kind: ActorKind
    declared_name: DeclaredName | None = None
    identity_assurance: Literal["unverified_local"] = "unverified_local"
    registered_at_utc: UtcTimestamp


class ActorContextService:
    """Registra e resgata contextos de ator na autoridade operacional comum.

    Também é o ``ActorContextResolver`` passado aos serviços de curadoria E2, para
    que E2 e E3 resolvam a mesma tabela.
    """

    def __init__(
        self,
        store: OperationalStore,
        *,
        session_id: str | None = None,
        clock: Callable[[], str] = utc_now,
    ) -> None:
        """Sessão da aplicação: um UUID novo por serviço, salvo se informado."""
        self._store = store
        self._session_id = session_id or str(new_uuid())
        self._clock = clock

    def register(self, *, actor_kind: ActorKind, declared_name: str | None) -> LocalActorContext:
        """Cria um contexto com ID gerado pelo backend; nome é só identificação informada."""
        try:
            context = LocalActorContext(
                actor_context_id=str(new_uuid()),
                installation_id=self._store.installation_id,
                session_id=self._session_id,
                actor_kind=actor_kind,
                declared_name=declared_name,
                registered_at_utc=self._clock(),
            )
        except ValidationError as exc:
            raise ValueError(f"contexto de ator inválido: {exc}") from exc
        with self._store.transaction() as uow:
            uow.actors.insert(context.model_dump(mode="json"))
            uow.events.append(
                "operations",
                {
                    "event": "actor_context_registered",
                    "actor_context_id": context.actor_context_id,
                    "actor_kind": context.actor_kind,
                    "at_utc": context.registered_at_utc,
                },
            )
        return context

    def ensure_system_context(self, *, key: str, declared_name: str) -> LocalActorContext:
        """Contexto ``service`` estável da instalação para ``key``, criado uma única vez.

        O ID deriva da instalação e da chave (UUID v5), para que execuções em processos
        diferentes usem o mesmo ator técnico; nunca representa pessoa.
        """
        actor_context_id = str(uuid.uuid5(uuid.UUID(self._store.installation_id), key))
        with self._store.transaction() as uow:
            if uow.actors.get(actor_context_id) is None:
                context = LocalActorContext(
                    actor_context_id=actor_context_id,
                    installation_id=self._store.installation_id,
                    session_id=self._session_id,
                    actor_kind="service",
                    declared_name=declared_name,
                    registered_at_utc=self._clock(),
                )
                uow.actors.insert(context.model_dump(mode="json"))
                uow.events.append(
                    "operations",
                    {
                        "event": "actor_context_registered",
                        "actor_context_id": actor_context_id,
                        "actor_kind": "service",
                        "at_utc": context.registered_at_utc,
                    },
                )
                return context
        existing = self.resolve(actor_context_id)
        if existing is None or existing.actor_kind != "service":
            raise ActorContextError(f"contexto de sistema {actor_context_id} incoerente")
        return existing

    def resolve(self, actor_context_id: str) -> LocalActorContext | None:
        """Contexto registrado, ou ``None``; registro incoerente é ``ActorContextError``."""
        with self._store.transaction() as uow:
            row = uow.actors.get(actor_context_id)
        if row is None:
            return None
        try:
            context = LocalActorContext.model_validate(row.document)
        except ValidationError as exc:
            raise ActorContextError(f"contexto de ator {actor_context_id} inválido") from exc
        if context.installation_id != self._store.installation_id:
            raise ActorContextError(
                f"contexto de ator {actor_context_id} pertence a outra instalação"
            )
        return context

    def require(self, actor_context_id: str, *, requirement: ActorKindRequirement) -> ActorSnapshot:
        """Snapshot do ator resolvido, se o tipo atender à exigência da operação."""
        try:
            context = self.resolve(actor_context_id)
        except ActorContextError as exc:
            raise OperationalError("invalid_actor", str(exc)) from exc
        if context is None:
            raise OperationalError("invalid_actor", f"contexto {actor_context_id} inexistente")
        if context.actor_kind not in _ALLOWED[requirement]:
            reason: OperationalErrorReason = (
                "human_actor_required" if requirement == "human" else "invalid_actor"
            )
            raise OperationalError(
                reason, f"operação exige {requirement}; contexto é {context.actor_kind}"
            )
        return snapshot_actor(context)
