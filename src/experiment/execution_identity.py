"""Identidade imutável e canônica de uma execução oficial do benchmark."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

import yaml

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GROUND_TRUTH_POLICY_VERSION = "full-coverage-equivalent-v1"
CONFIDENCE_BUCKETS = ("high", "medium", "low")


def _validate_sha_fields(value: Any) -> None:
    """Valida todos os campos SHA-256 declarados em um dataclass."""
    for descriptor in fields(value):
        if descriptor.name.endswith("_sha256"):
            digest = getattr(value, descriptor.name)
            if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
                raise ValueError(f"{descriptor.name} deve ser SHA-256 lowercase")


@dataclass(frozen=True)
class GroundTruthIdentityMetadata:
    """Metadados científicos que participam da identidade de execução."""

    ground_truth_policy_version: str
    ground_truth_items: int
    equivalence_classes: int
    confidence_counts: Sequence[tuple[str, int]]

    def __post_init__(self) -> None:
        if self.ground_truth_policy_version != GROUND_TRUTH_POLICY_VERSION:
            raise ValueError("politica integral do ground truth invalida")
        if type(self.ground_truth_items) is not int or self.ground_truth_items <= 0:
            raise ValueError("ground_truth_items deve ser inteiro positivo")
        if (
            type(self.equivalence_classes) is not int
            or self.equivalence_classes <= 0
            or self.equivalence_classes > self.ground_truth_items
        ):
            raise ValueError("equivalence_classes deve estar entre 1 e ground_truth_items")
        if not isinstance(self.confidence_counts, tuple):
            raise TypeError("confidence_counts deve ser tuple")
        names = tuple(name for name, _count in self.confidence_counts)
        if names != CONFIDENCE_BUCKETS:
            raise ValueError("confidence_counts deve conter high,medium,low nessa ordem")
        counts = tuple(count for _name, count in self.confidence_counts)
        if any(type(count) is not int or count < 0 for count in counts):
            raise ValueError("confidence_counts deve conter inteiros nao negativos")
        if sum(counts) != self.ground_truth_items:
            raise ValueError("somatorio de confidence_counts diverge de ground_truth_items")


@dataclass(frozen=True)
class DatasetIdentity(GroundTruthIdentityMetadata):
    """Entradas congeladas de um dataset, incluindo seu contexto semântico."""

    key: str
    ifc_sha256: str
    ground_truth_sha256: str
    ids_sha256: str
    building_context: Sequence[tuple[str, str]]
    ground_truth_policy_version: str
    ground_truth_items: int
    equivalence_classes: int
    confidence_counts: Sequence[tuple[str, int]]

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.key not in {"predio", "casa"}:
            raise ValueError("dataset deve ser predio ou casa")
        if not isinstance(self.building_context, tuple):
            raise TypeError("building_context deve ser tuple")
        if tuple(sorted(self.building_context)) != self.building_context:
            raise ValueError("building_context deve estar ordenado")
        _validate_sha_fields(self)


def load_ground_truth_identity_metadata(
    path: str | Path,
) -> GroundTruthIdentityMetadata:
    """Lê somente o metadata integral de um YAML já validado por SHA-256."""
    document_path = Path(path)
    try:
        document = yaml.safe_load(document_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ValueError(f"ground truth invalido em {document_path}: {error}") from error
    if not isinstance(document, dict) or not isinstance(document.get("metadata"), dict):
        raise ValueError("ground truth deve conter metadata como mapeamento")
    metadata = document["metadata"]
    required = {
        "protocol",
        "total_items",
        "equivalence_class_count",
        "confidence_counts",
    }
    if not required.issubset(metadata):
        raise ValueError("metadata integral possui campos ausentes")
    raw_counts = metadata["confidence_counts"]
    if not isinstance(raw_counts, dict) or set(raw_counts) != set(CONFIDENCE_BUCKETS):
        raise ValueError("confidence_counts deve conter somente high,medium,low")
    return GroundTruthIdentityMetadata(
        ground_truth_policy_version=metadata["protocol"],
        ground_truth_items=metadata["total_items"],
        equivalence_classes=metadata["equivalence_class_count"],
        confidence_counts=tuple(
            (name, raw_counts[name]) for name in CONFIDENCE_BUCKETS
        ),
    )


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
    # Acrescentados em 2026-08-12. Todos alteram o resultado e nenhum estava na
    # identidade: dois runs com janela de contexto ou seed diferentes tinham o
    # mesmo canonical_identity_sha256 e eram tratados como a mesma condição.
    source_commit: str = ""
    """Commit (ou hash determinístico da árvore) do código empacotado."""
    num_ctx_policy: str = ""
    """``fixed`` ou ``fit`` — muda latência, VRAM e o número de recargas."""
    num_ctx: int = 0
    """Janela efetiva da política ``fixed``, ou o teto da política ``fit``."""
    num_predict: int = 0
    seed: int | None = None
    temperature: float = 0.0
    top_p: float = 0.0
    repeat_penalty: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.datasets, tuple):
            raise TypeError("datasets deve ser tuple")
        if [dataset.key for dataset in self.datasets] != ["predio", "casa"]:
            raise ValueError("datasets devem estar na ordem predio,casa")
        if self.replica_count < 1:
            raise ValueError("replica_count deve ser positivo")
        if self.num_ctx_policy not in ("", "fixed", "fit"):
            raise ValueError("num_ctx_policy deve ser 'fixed' ou 'fit'")
        _validate_sha_fields(self)


def canonical_identity_sha256(identity: ExecutionIdentity) -> str:
    """Calcula SHA-256 sobre JSON UTF-8 compacto e com chaves ordenadas."""
    payload = json.dumps(
        asdict(identity), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
