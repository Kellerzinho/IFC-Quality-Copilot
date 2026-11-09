"""Argumentos semânticos e envelopes dos comandos operacionais.

Cada operação tem **uma** função que monta seus argumentos canônicos; o serviço usa a
mesma função para recalcular o hash e recusar envelope que não represente o pedido.
As funções ``<operação>(...)`` montam o envelope do lado de quem envia o comando.
"""

import uuid
from typing import Any

from src.artifacts.contracts import RetainedSourceObject
from src.operations.contracts import OperationalCommand, SourceArtifactRef, SourceRole


def _id(value: uuid.UUID | None) -> str | None:
    return None if value is None else str(value)


def create_project_arguments(*, name: str) -> dict[str, Any]:
    """Argumentos de ``create_project``."""
    return {"name": name}


def create_model_arguments(*, project_id: uuid.UUID, discipline: str) -> dict[str, Any]:
    """Argumentos de ``create_model``."""
    return {"project_id": str(project_id), "discipline": discipline}


def register_source_revision_arguments(
    *,
    project_id: uuid.UUID,
    model_id: uuid.UUID,
    role: SourceRole,
    retained: RetainedSourceObject,
    source_id: uuid.UUID | None,
    expected_source_revision: int,
) -> dict[str, Any]:
    """Argumentos de ``register_source_revision`` (objeto retido completo)."""
    return {
        "project_id": str(project_id),
        "model_id": str(model_id),
        "role": role,
        "retained": retained.model_dump(mode="json"),
        "source_id": _id(source_id),
        "expected_source_revision": expected_source_revision,
    }


def register_pair_arguments(
    *,
    project_id: uuid.UUID,
    expected_pair_set_revision: int,
    ifc: SourceArtifactRef,
    ids: SourceArtifactRef,
    discipline: str,
) -> dict[str, Any]:
    """Argumentos de ``register_pair`` (referências completas das duas fontes)."""
    return {
        "project_id": str(project_id),
        "expected_pair_set_revision": expected_pair_set_revision,
        "ifc": ifc.model_dump(mode="json"),
        "ids": ids.model_dump(mode="json"),
        "discipline": discipline,
    }


def revise_pair_arguments(
    *,
    pair_id: uuid.UUID,
    expected_pair_revision: int,
    expected_pair_set_revision: int,
    ifc: SourceArtifactRef,
    ids: SourceArtifactRef,
    active: bool,
) -> dict[str, Any]:
    """Argumentos de ``revise_pair``."""
    return {
        "pair_id": str(pair_id),
        "expected_pair_revision": expected_pair_revision,
        "expected_pair_set_revision": expected_pair_set_revision,
        "ifc": ifc.model_dump(mode="json"),
        "ids": ids.model_dump(mode="json"),
        "active": active,
    }


def create_project(command_id: uuid.UUID, actor: uuid.UUID, *, name: str) -> OperationalCommand:
    """Envelope de ``create_project`` (sem projeto: o serviço gera o ID)."""
    return OperationalCommand.build(
        command_id=command_id,
        actor_context_id=actor,
        operation="create_project",
        project_id=None,
        arguments=create_project_arguments(name=name),
    )


def create_model(
    command_id: uuid.UUID, actor: uuid.UUID, project_id: uuid.UUID, discipline: str
) -> OperationalCommand:
    """Envelope de ``create_model``."""
    return OperationalCommand.build(
        command_id=command_id,
        actor_context_id=actor,
        operation="create_model",
        project_id=project_id,
        arguments=create_model_arguments(project_id=project_id, discipline=discipline),
    )


def register_source_revision(
    command_id: uuid.UUID,
    actor: uuid.UUID,
    project_id: uuid.UUID,
    model_id: uuid.UUID,
    role: SourceRole,
    retained: RetainedSourceObject,
    source_id: uuid.UUID | None,
    expected_source_revision: int,
) -> OperationalCommand:
    """Envelope de ``register_source_revision``."""
    return OperationalCommand.build(
        command_id=command_id,
        actor_context_id=actor,
        operation="register_source_revision",
        project_id=project_id,
        arguments=register_source_revision_arguments(
            project_id=project_id,
            model_id=model_id,
            role=role,
            retained=retained,
            source_id=source_id,
            expected_source_revision=expected_source_revision,
        ),
    )


def register_pair(
    command_id: uuid.UUID,
    actor: uuid.UUID,
    project_id: uuid.UUID,
    expected_pair_set_revision: int,
    ifc: SourceArtifactRef,
    ids: SourceArtifactRef,
    discipline: str,
) -> OperationalCommand:
    """Envelope de ``register_pair``."""
    return OperationalCommand.build(
        command_id=command_id,
        actor_context_id=actor,
        operation="register_pair",
        project_id=project_id,
        arguments=register_pair_arguments(
            project_id=project_id,
            expected_pair_set_revision=expected_pair_set_revision,
            ifc=ifc,
            ids=ids,
            discipline=discipline,
        ),
    )


def revise_pair(
    command_id: uuid.UUID,
    actor: uuid.UUID,
    project_id: uuid.UUID,
    pair_id: uuid.UUID,
    expected_pair_revision: int,
    expected_pair_set_revision: int,
    ifc: SourceArtifactRef,
    ids: SourceArtifactRef,
    active: bool,
) -> OperationalCommand:
    """Envelope de ``revise_pair`` (o projeto do par vai no envelope)."""
    return OperationalCommand.build(
        command_id=command_id,
        actor_context_id=actor,
        operation="revise_pair",
        project_id=project_id,
        arguments=revise_pair_arguments(
            pair_id=pair_id,
            expected_pair_revision=expected_pair_revision,
            expected_pair_set_revision=expected_pair_set_revision,
            ifc=ifc,
            ids=ids,
            active=active,
        ),
    )
