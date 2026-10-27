"""Contratos dos artefatos retidos: objetos de fonte, releases retidos e erros tipados."""

from typing import Annotated, Literal, Self

from pydantic import StringConstraints, model_validator

from src.domain_catalog.contracts import CatalogReleaseRef, ContractModel
from src.domain_catalog.models import Sha256Hex
from src.domain_catalog.package import ContentOrigin
from src.operations.contracts import (
    DisplayName,
    NonNegativeInt,
    SchemaVersionOne,
    SourceRole,
    StorageKey,
)

ArtifactErrorReason = Literal[
    "artifact_unavailable",
    "artifact_integrity_error",
    "unsafe_source",
    "resource_limit_exceeded",
    "storage_collision",
    "storage_failure",
]


class ArtifactError(Exception):
    """Falha tipada do armazenamento de artefatos; a causa original fica em ``__cause__``."""

    code = "artifact_error"

    def __init__(self, reason: ArtifactErrorReason, message: str) -> None:
        """Guarda o motivo estável."""
        self.reason: ArtifactErrorReason = reason
        super().__init__(f"[{reason}] {message}")


class RetainedSourceObject(ContractModel):
    """Bytes exatos de um IFC/IDS retidos; não aloca identidade lógica nem revisão."""

    schema_version: SchemaVersionOne = 1
    role: SourceRole
    sha256: Sha256Hex
    size_bytes: NonNegativeInt
    storage_key: StorageKey
    display_name: DisplayName

    @model_validator(mode="after")
    def _key_matches(self) -> Self:
        """A chave interna é derivada de papel e hash."""
        if self.storage_key != f"s/{self.role}/{self.sha256}":
            raise ValueError("storage_key não corresponde ao papel e ao hash")
        return self


CatalogStorageKey = Annotated[str, StringConstraints(pattern=r"^r/[0-9a-f]{32}$")]


class RetainedFile(ContractModel):
    """Arquivo do pacote retido, com tamanho e hash conferidos na cópia."""

    path: Annotated[str, StringConstraints(pattern=r"^[a-z_]+\.json$")]
    bytes: NonNegativeInt
    sha256: Sha256Hex


class RetainedCatalogRef(ContractModel):
    """Cópia local verificada de um release; retenção não é publicação nem aprovação."""

    schema_version: SchemaVersionOne = 1
    catalog: CatalogReleaseRef
    storage_key: CatalogStorageKey
    origin: Literal["retained_local_package"] = "retained_local_package"
    content_origin: ContentOrigin
    files: tuple[RetainedFile, ...]


class OrphanReport(ContractModel):
    """Objetos sem referência no banco e restos de preparo; relatório somente leitura."""

    sources: tuple[str, ...] = ()
    releases: tuple[str, ...] = ()
    staging: tuple[str, ...] = ()
