"""Testes do lock reproduzível da matriz de modelos."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.experiment.model_lock import (
    ModelMatrixLock,
    load_model_lock,
    model_digest_mismatches,
    required_free_bytes,
)

ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = ROOT / "src" / "experiment" / "results" / "models.lock.json"


def test_official_lock_has_full_digests_and_exact_total():
    """O lock oficial fixa todos os dez artefatos com seus tamanhos exatos."""
    lock = load_model_lock(LOCK_PATH)

    assert lock.schema_version == 2
    assert lock.runtime.version == "0.32.5"
    assert lock.runtime.platform == "windows-amd64"
    assert len(lock.models) == 10
    assert all(len(model.digest) == 64 for model in lock.models)
    assert sum(model.size_bytes for model in lock.models) == 91_733_110_513


def test_all_missing_requires_partial_and_reserve_space():
    """Sem modelos instalados, o orçamento inclui download, staging e reserva."""
    lock = load_model_lock(LOCK_PATH)

    assert required_free_bytes(lock, {}) == 114_699_862_808


def test_partial_and_complete_store_have_exact_space_budgets():
    """Um modelo divergente é tratado como ausente; matriz idêntica não ocupa espaço."""
    lock = load_model_lock(LOCK_PATH)
    partial = {model.name: model.digest for model in lock.models[:-1]}
    only_missing = lock.models[-1].size_bytes

    assert required_free_bytes(lock, partial) == (
        only_missing + only_missing + max(only_missing // 10, 4 * 1024**3)
    )

    complete = {model.name: model.digest for model in lock.models}
    assert required_free_bytes(lock, complete) == 0


def test_digest_drift_is_reported_with_full_expected_and_actual():
    """A mensagem de drift identifica tag e ambos os digests completos."""
    lock = load_model_lock(LOCK_PATH)
    installed = {lock.models[0].name: "0" * 64}

    errors = model_digest_mismatches(lock, installed)

    assert lock.models[0].name in errors[0]
    assert lock.models[0].digest in errors[0]
    assert "0" * 64 in errors[0]


@pytest.mark.parametrize(
    ("field", "value"),
    [("digest", "abc"), ("digest", "z" * 64), ("size_bytes", 0)],
)
def test_model_entry_rejects_invalid_digest_or_size(field, value):
    """Entradas inválidas não podem representar artefatos reproduzíveis."""
    raw = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    raw["models"][0][field] = value

    with pytest.raises(ValidationError):
        ModelMatrixLock.model_validate(raw)


def test_lock_rejects_duplicate_tag_and_wrong_platform():
    """A matriz é uma lista de tags únicas e só vale para o runtime pinado."""
    duplicate = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    duplicate["models"][1]["name"] = duplicate["models"][0]["name"]

    with pytest.raises(ValidationError, match="duplicado"):
        ModelMatrixLock.model_validate(duplicate)

    wrong_platform = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    wrong_platform["runtime"]["platform"] = "linux-amd64"

    with pytest.raises(ValidationError):
        ModelMatrixLock.model_validate(wrong_platform)
