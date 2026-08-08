"""Identidade imutável e canônica de uma execução oficial do benchmark."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass, fields

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _validate_sha_fields(value: object) -> None:
    """Valida todos os campos SHA-256 declarados em um dataclass."""
    for descriptor in fields(value):
        if descriptor.name.endswith("_sha256"):
            digest = getattr(value, descriptor.name)
            if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
                raise ValueError(f"{descriptor.name} deve ser SHA-256 lowercase")


@dataclass(frozen=True)
class DatasetIdentity:
    """Entradas congeladas de um dataset, incluindo seu contexto semântico."""

    key: str
    ifc_sha256: str
    ground_truth_sha256: str
    ids_sha256: str
    building_context: Sequence[tuple[str, str]]

    def __post_init__(self) -> None:
        if not isinstance(self.building_context, tuple):
            raise TypeError("building_context deve ser tuple")
        if tuple(sorted(self.building_context)) != self.building_context:
            raise ValueError("building_context deve estar ordenado")
        _validate_sha_fields(self)


@dataclass(frozen=True)
class ExecutionIdentity:
    """Todas as dimensões capazes de alterar um resultado experimental."""

    release_id: str
    project_sha256: str
    models_lock_sha256: str
    datasets: Sequence[DatasetIdentity]
    replica_count: int
    cache_enabled: bool
    prompt_version: str
    prompt_sha256: str
    reuse_equivalent: bool

    def __post_init__(self) -> None:
        if not isinstance(self.datasets, tuple):
            raise TypeError("datasets deve ser tuple")
        if [dataset.key for dataset in self.datasets] != ["predio", "casa"]:
            raise ValueError("datasets devem estar na ordem predio,casa")
        if self.replica_count < 1:
            raise ValueError("replica_count deve ser positivo")
        _validate_sha_fields(self)


def canonical_identity_sha256(identity: ExecutionIdentity) -> str:
    """Calcula SHA-256 sobre JSON UTF-8 compacto e com chaves ordenadas."""
    payload = json.dumps(
        asdict(identity), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
