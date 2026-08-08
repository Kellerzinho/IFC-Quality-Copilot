"""Validação do lock reproduzível da matriz de modelos Ollama."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MINIMUM_RESERVE_BYTES = 4 * 1024**3


class RuntimeLock(BaseModel):
    """Runtime Ollama suportado pelo lock da matriz."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: Literal["ollama"]
    version: Literal["0.32.5"]
    platform: Literal["windows-amd64"]
    asset_sha256: str

    @field_validator("asset_sha256")
    @classmethod
    def validate_asset_sha256(cls, value: str) -> str:
        """Exige o digest SHA-256 completo e em minúsculas do instalador."""
        if not _SHA256_PATTERN.fullmatch(value):
            msg = "asset_sha256 deve conter 64 caracteres hexadecimais minúsculos"
            raise ValueError(msg)
        return value


class ModelLockEntry(BaseModel):
    """Artefato Ollama que compõe a matriz reproduzível."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1)
    digest: str
    size_bytes: int = Field(gt=0)
    architecture: str = Field(min_length=1)
    parameters: str = Field(min_length=1)
    context_length: int = Field(gt=0)
    quantization: str = Field(min_length=1)

    @field_validator("digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        """Exige o digest SHA-256 completo e em minúsculas da imagem."""
        if not _SHA256_PATTERN.fullmatch(value):
            msg = "digest deve conter 64 caracteres hexadecimais minúsculos"
            raise ValueError(msg)
        return value


class ModelMatrixLock(BaseModel):
    """Schema v2 da matriz completa de modelos e runtime do benchmark."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[2]
    runtime: RuntimeLock
    models: list[ModelLockEntry] = Field(min_length=10, max_length=10)

    @model_validator(mode="after")
    def validate_unique_model_names(self) -> ModelMatrixLock:
        """Garante que cada tag Ollama apareça uma única vez na matriz."""
        names = [model.name for model in self.models]
        if len(names) != len(set(names)):
            raise ValueError("tags de modelo duplicado no lock")
        return self


def load_model_lock(path: Path) -> ModelMatrixLock:
    """Carrega e valida um arquivo JSON de lock de modelos."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ModelMatrixLock.model_validate(raw)


def model_digest_mismatches(lock: ModelMatrixLock, installed: Mapping[str, str]) -> list[str]:
    """Retorna divergências entre os digests pinados e os reportados pelo Ollama."""
    errors: list[str] = []
    for model in lock.models:
        actual = installed.get(model.name)
        if actual != model.digest:
            actual_display = actual if actual is not None else "<ausente>"
            errors.append(
                f"Digest divergente para {model.name}: esperado {model.digest}, "
                f"atual {actual_display}"
            )
    return errors


def required_free_bytes(lock: ModelMatrixLock, installed: Mapping[str, str]) -> int:
    """Calcula o espaço livre necessário para completar a matriz sem sobrescrever modelos."""
    missing = [
        model.size_bytes for model in lock.models if installed.get(model.name) != model.digest
    ]
    if not missing:
        return 0
    return sum(missing) + max(missing) + max(sum(missing) // 10, _MINIMUM_RESERVE_BYTES)
