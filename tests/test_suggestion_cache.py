"""Testes para SuggestionCache (SQLite) e cálculo de assinatura."""

from __future__ import annotations

import pytest

from src.models import Suggestion
from src.suggestion_engine.suggestion_cache import (
    PROMPT_VERSION,
    SuggestionCache,
    compute_signature,
)


def _suggestion(label: str = "Sala de Estar", value: str = "Sala de Estar") -> Suggestion:
    return Suggestion(
        label=label,
        value=value,
        justification="teste",
        confidence="alta",
        source="llm",
    )


def _signature(**overrides) -> str:
    base = dict(
        model_version="qwen3.5:9b",
        prompt_version=PROMPT_VERSION,
        issue_type="pset_missing",
        ifc_class="IfcWall",
        target_pset="Pset_WallCommon",
        target_property="ThermalTransmittance",
        expected_type="real",
        expected_unit="W/(m²·K)",
        requirement_id="rule-1",
        candidates=["2.5", "1.8"],
        context_payload={"is_external": True},
    )
    base.update(overrides)
    return compute_signature(**base)


def test_signature_is_stable():
    """Mesmos parâmetros produzem mesma assinatura."""
    sig_a = _signature()
    sig_b = _signature()
    assert sig_a == sig_b


def test_signature_changes_with_model_version():
    sig_qwen = _signature(model_version="qwen3.5:9b")
    sig_llama = _signature(model_version="llama3:8b")
    assert sig_qwen != sig_llama


def test_signature_changes_with_grounding_mode():
    """Modos de grounding distintos não devem colidir no cache (F4)."""
    sig_none = _signature(grounding_mode="none")
    sig_bsdd = _signature(grounding_mode="ids_bsdd")
    assert sig_none != sig_bsdd


def test_signature_changes_with_prompt_version():
    sig_v1 = _signature(prompt_version="v1")
    sig_v2 = _signature(prompt_version="v2")
    assert sig_v1 != sig_v2


def test_signature_invariant_to_candidate_order():
    sig_a = _signature(candidates=["1.8", "2.5"])
    sig_b = _signature(candidates=["2.5", "1.8"])
    assert sig_a == sig_b


def test_cache_get_miss_returns_none(tmp_path):
    cache = SuggestionCache(tmp_path / "cache.db")
    try:
        assert cache.get("inexistente") is None
    finally:
        cache.close()


def test_cache_set_and_get_roundtrip(tmp_path):
    cache = SuggestionCache(tmp_path / "cache.db")
    try:
        sig = _signature()
        suggestions = [_suggestion("Sala"), _suggestion("Cozinha")]
        cache.set(sig, suggestions, model_version="qwen3.5:9b", prompt_version=PROMPT_VERSION)
        got = cache.get(sig)
        assert got is not None
        assert [s.label for s in got] == ["Sala", "Cozinha"]
        assert got[0].source == "llm"
    finally:
        cache.close()


def test_cache_invalidate_by_model(tmp_path):
    cache = SuggestionCache(tmp_path / "cache.db")
    try:
        sig_old = _signature(model_version="llama3:8b")
        sig_new = _signature(model_version="qwen3.5:9b")
        cache.set(sig_old, [_suggestion("Old")], "llama3:8b", PROMPT_VERSION)
        cache.set(sig_new, [_suggestion("New")], "qwen3.5:9b", PROMPT_VERSION)

        removed = cache.invalidate_by_model("qwen3.5:9b")
        assert removed == 1
        assert cache.get(sig_old) is None
        assert cache.get(sig_new) is not None
    finally:
        cache.close()


def test_cache_invalidate_by_prompt(tmp_path):
    cache = SuggestionCache(tmp_path / "cache.db")
    try:
        sig_v0 = _signature(prompt_version="v0")
        sig_v1 = _signature(prompt_version="v1")
        cache.set(sig_v0, [_suggestion()], "qwen3.5:9b", "v0")
        cache.set(sig_v1, [_suggestion()], "qwen3.5:9b", "v1")

        removed = cache.invalidate_by_prompt("v1")
        assert removed == 1
        assert cache.get(sig_v0) is None
        assert cache.get(sig_v1) is not None
    finally:
        cache.close()


def test_cache_set_empty_is_noop(tmp_path):
    cache = SuggestionCache(tmp_path / "cache.db")
    try:
        sig = _signature()
        cache.set(sig, [], "qwen3.5:9b", PROMPT_VERSION)
        assert cache.get(sig) is None
        assert cache.size() == 0
    finally:
        cache.close()


def test_cache_replaces_existing_entry(tmp_path):
    cache = SuggestionCache(tmp_path / "cache.db")
    try:
        sig = _signature()
        cache.set(sig, [_suggestion("v1")], "qwen3.5:9b", PROMPT_VERSION)
        cache.set(sig, [_suggestion("v2")], "qwen3.5:9b", PROMPT_VERSION)
        got = cache.get(sig)
        assert got is not None
        assert got[0].label == "v2"
    finally:
        cache.close()
