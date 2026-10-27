"""Contratos operacionais comuns da E3: IDs, comandos, recibos, erros e fontes.

Todo DTO persistido herda ``ContractModel`` (imutável, campos extras proibidos) e
declara ``schema_version=1``. IDs operacionais são UUIDs canônicos gerados pelo
serviço (texto minúsculo ``8-4-4-4-12``); nunca GlobalId IFC nem nome de arquivo.
Hashes são SHA-256 inteiros. O hash de payload de um comando usa uma única função
canônica (``canonical_json_bytes``), sem ``default=str``: tipos são preservados e
NaN/infinito são recusados.
"""

import hashlib
import re
import uuid
from collections.abc import Mapping
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BeforeValidator,
    Field,
    PlainSerializer,
    StrictInt,
    StringConstraints,
    model_validator,
)

from src.domain_catalog.actor import ActorSnapshot
from src.domain_catalog.canonical import canonical_json_bytes
from src.domain_catalog.contracts import ContractModel
from src.domain_catalog.models import NonEmptyText, Sha256Hex
from src.domain_catalog.package import UtcTimestamp

_UUID_TEXT = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _canonical_uuid(value: object) -> uuid.UUID:
    """Aceita só ``uuid.UUID`` ou texto canônico minúsculo; outras grafias são recusadas."""
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str) and _UUID_TEXT.match(value):
        return uuid.UUID(value)
    raise ValueError(f"UUID canônico esperado (minúsculo 8-4-4-4-12), recebido {value!r}")


CanonicalUUID = Annotated[
    uuid.UUID,
    BeforeValidator(_canonical_uuid),
    PlainSerializer(lambda value: str(value), return_type=str, when_used="json"),
]
"""UUID operacional; em JSON, texto canônico minúsculo."""

PositiveInt = Annotated[StrictInt, Field(ge=1)]
NonNegativeInt = Annotated[StrictInt, Field(ge=0)]


def _exact_one(value: Any) -> Any:
    if type(value) is not int:
        raise ValueError("schema_version exige o inteiro 1 (bool/float/texto recusados)")
    return value


SchemaVersionOne = Annotated[Literal[1], BeforeValidator(_exact_one)]
"""Versão de schema 1, estrita: ``True`` ou ``1.0`` não são coagidos (E3-16)."""


def new_uuid() -> uuid.UUID:
    """Novo UUID operacional (versão 4), gerado pelo serviço."""
    return uuid.uuid4()


def canonical_sha256(value: Any) -> str:
    """SHA-256 dos bytes JSON canônicos de um valor (tipos preservados, sem NaN)."""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def model_sha256(model: ContractModel) -> str:
    """SHA-256 canônico de um DTO serializado em modo JSON."""
    return canonical_sha256(model.model_dump(mode="json"))


OperationalErrorReason = Literal[
    "not_found",
    "invalid_actor",
    "human_actor_required",
    "invalid_command",
    "idempotency_conflict",
    "stale_pair_set",
    "stale_pair",
    "stale_source",
    "stale_pin",
    "stale_plan",
    "pair_limit_exceeded",
    "foreign_reference",
    "role_mismatch",
    "store_busy",
    "store_unavailable",
    "integrity_error",
    "artifact_unavailable",
    "artifact_integrity_error",
    "version_hash_collision",
    "schema_unsupported",
    "purpose_mismatch",
    "analysis_in_progress",
    "analysis_interrupted",
    "execution_claim_conflict",
    "analysis_identity_mismatch",
    "execution_profile_mismatch",
    "coordinator_busy",
]
"""Motivos estáveis dos erros operacionais; nunca deduzidos de texto de mensagem."""


class OperationalError(Exception):
    """Falha tipada de um comando ou consulta operacional; nada foi gravado.

    ``reason`` é o identificador estável; ``expected``/``actual`` conservam os tokens
    comparados (CAS, hash) e ``__cause__`` a exceção original quando houver.
    """

    code = "operational_error"

    def __init__(
        self,
        reason: OperationalErrorReason,
        message: str,
        *,
        expected: object | None = None,
        actual: object | None = None,
    ) -> None:
        """Guarda motivo e tokens comparados sem interpretar a mensagem."""
        self.reason: OperationalErrorReason = reason
        self.expected = expected
        self.actual = actual
        super().__init__(f"[{reason}] {message}")


def require_tokens(**tokens: object) -> None:
    """Tokens públicos (revisões esperadas) são ``int`` exatos; bool/float recusados (M-04)."""
    for name, value in tokens.items():
        if type(value) is not int:
            raise OperationalError("invalid_command", f"{name} exige inteiro, não {value!r}")


ActorKindRequirement = Literal["human", "human_or_service", "any"]

OperationName = Literal[
    "create_project",
    "create_model",
    "register_source_revision",
    "register_pair",
    "revise_pair",
    "apply_catalog_adoption",
    "queue_reanalysis",
    "queue_initial_analysis",
    "execute_analysis",
]
"""Operações do namespace ``operations`` no índice global de comandos."""


def command_payload_sha256(
    *,
    operation: str,
    actor_context_id: str,
    project_id: uuid.UUID | None,
    arguments: Mapping[str, Any],
) -> str:
    """Hash do pedido: operação, ator, projeto e todos os argumentos semânticos.

    Hora gerada pelo servidor nunca entra; tokens esperados (CAS) entram como
    argumentos. Mesma chave com qualquer diferença aqui é conflito de idempotência.
    """
    return canonical_sha256(
        {
            "operation": operation,
            "actor_context_id": actor_context_id,
            "project_id": None if project_id is None else str(project_id),
            "arguments": dict(arguments),
        }
    )


class OperationalCommand(ContractModel):
    """Envelope idempotente de um comando operacional (M6 mínimo).

    ``command_id`` é a chave gerada por quem envia, única na instalação e partilhada
    com o namespace da curadoria E2. O serviço recalcula ``payload_sha256`` a partir
    dos argumentos recebidos e recusa envelope que não os represente.
    """

    schema_version: SchemaVersionOne = 1
    command_id: CanonicalUUID
    actor_context_id: CanonicalUUID
    operation: OperationName
    project_id: CanonicalUUID | None = None
    payload_sha256: Sha256Hex

    @classmethod
    def build(
        cls,
        *,
        command_id: uuid.UUID,
        actor_context_id: uuid.UUID,
        operation: OperationName,
        project_id: uuid.UUID | None,
        arguments: Mapping[str, Any],
    ) -> "OperationalCommand":
        """Monta o envelope calculando o hash canônico dos argumentos."""
        return cls(
            command_id=command_id,
            actor_context_id=actor_context_id,
            operation=operation,
            project_id=project_id,
            payload_sha256=command_payload_sha256(
                operation=operation,
                actor_context_id=str(actor_context_id),
                project_id=project_id,
                arguments=arguments,
            ),
        )


ResultingKind = Literal[
    "project",
    "model",
    "source",
    "pair",
    "adoption_plan",
    "adoption",
    "pin",
    "analysis",
    "diagnostic",
    "enrichment",
]


class ResultingRef(ContractModel):
    """Registro criado ou citado por um comando, com revisão quando versionado."""

    kind: ResultingKind
    ref_id: CanonicalUUID
    revision: PositiveInt | None = None


class OperationalReceipt(ContractModel):
    """Recibo de comando operacional; não reutiliza o ``CommitReceipt`` da curadoria.

    ``noop`` registra pedido aceito sem efeito de domínio (por exemplo, adotar a
    referência já corrente); replay devolve sempre este mesmo recibo.
    """

    schema_version: SchemaVersionOne = 1
    receipt_id: CanonicalUUID
    command_id: CanonicalUUID
    operation: OperationName
    status: Literal["applied", "noop"]
    actor_snapshot: ActorSnapshot
    project_id: CanonicalUUID | None
    resulting_refs: tuple[ResultingRef, ...]
    event_sequence: tuple[PositiveInt, ...] = Field(min_length=1)
    committed_at_utc: UtcTimestamp
    payload_sha256: Sha256Hex

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Sequência de eventos crescente e referências sem repetição."""
        if list(self.event_sequence) != sorted(set(self.event_sequence)):
            raise ValueError("event_sequence precisa ser estritamente crescente")
        keys = [(ref.kind, ref.ref_id, ref.revision) for ref in self.resulting_refs]
        if len(keys) != len(set(keys)):
            raise ValueError("resulting_refs não admite repetição")
        return self


SourceRole = Literal["ifc", "ids"]

StorageKey = Annotated[str, StringConstraints(pattern=r"^s/(ifc|ids)/[0-9a-f]{64}$")]
"""Chave interna de objeto retido: área, papel e hash; nunca caminho livre ou URL."""

DisplayName = Annotated[str, StringConstraints(pattern=r"^[^\\/:*?\"<>|\x00-\x1f]{1,255}$")]
"""Nome original do arquivo, sem diretório; serve só para exibição."""


class SourceArtifactRef(ContractModel):
    """Revisão exata de uma fonte IFC ou IDS registrada num modelo de projeto.

    A identidade inclui revisão e bytes (hash/tamanho); os mesmos bytes em revisões
    diferentes continuam revisões diferentes. ``storage_key`` é interno.
    """

    schema_version: SchemaVersionOne = 1
    project_id: CanonicalUUID
    model_id: CanonicalUUID
    source_id: CanonicalUUID
    revision: PositiveInt
    role: SourceRole
    sha256: Sha256Hex
    size_bytes: NonNegativeInt
    display_name: DisplayName
    storage_key: StorageKey
    declared_schema: NonEmptyText | None = None

    @model_validator(mode="after")
    def _storage_matches_bytes(self) -> Self:
        """A chave interna aponta exatamente o papel e o hash declarados."""
        if self.storage_key != f"s/{self.role}/{self.sha256}":
            raise ValueError("storage_key não corresponde ao papel e ao hash da fonte")
        return self


def ref_digest(ref: SourceArtifactRef) -> str:
    """Hash canônico da referência completa de uma fonte."""
    return model_sha256(ref)
