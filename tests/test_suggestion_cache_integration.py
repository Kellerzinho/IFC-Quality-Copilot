"""Testes de integração do SuggestionGenerator com cache e métricas."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.models import IDSContext, Issue, SuggestionSet
from src.suggestion_engine.ollama_client import OllamaClient
from src.suggestion_engine.suggestion import SuggestionGenerator
from src.suggestion_engine.suggestion_cache import SuggestionCache

_VALID_JSON = (
    '{"opcoes": [{"suggested_value": "Sala", "label": "Sala", '
    '"justification": "ok", "confidence": "alta"}]}'
)

_JSON_WITH_BSDD_URI = (
    '{"opcoes": [{"suggested_value": "Sala", "label": "Sala", '
    '"justification": "ok", "confidence": "alta", "bsdd_uri": "https://invented.example/uri"}]}'
)


@pytest.fixture(autouse=True)
def _clear_settings():
    from src.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _space_issue() -> Issue:
    return Issue(
        element_guid="S" * 22,
        element_class="IfcSpace",
        element_name="Sala",
        issue_type="space_unnamed",
        severity="low",
        description="sem nome",
        context={"area_m2": 12.0},
    )


def _ids_for(issue: Issue) -> IDSContext:
    return IDSContext(
        spec_name="NBR15575",
        requirement_description="Espaco deve ter Category",
        check_type="exists",
        expected_pset="Pset_SpaceCommon",
        expected_property="Category",
        severity="high",
        requirement_id="rule-1",
    )


def _make_client(response: str = _VALID_JSON) -> MagicMock:
    client = MagicMock(spec=OllamaClient)
    client.generate.return_value = (response, {
        "total_duration": 1_000_000,
        "load_duration": 100_000,
        "prompt_eval_duration": 200_000,
        "eval_duration": 700_000,
        "prompt_eval_count": 50,
        "eval_count": 30,
    })
    client.model = "qwen3.5:9b"
    return client


def test_cache_hit_skips_llm(tmp_path):
    cache = SuggestionCache(tmp_path / "c.db")
    try:
        client = _make_client()
        gen = SuggestionGenerator(client, cache=cache)
        issue = _space_issue()
        ids = _ids_for(issue)

        # Primeira chamada: miss → LLM é invocado
        first = gen.generate(issue, {}, ids_context=ids)
        assert first.has_suggestions
        assert client.generate.call_count == 1
        assert first.metrics is not None
        assert first.metrics.cache_hit is False

        # Segunda chamada: deve dar cache hit, sem nova invocação ao LLM
        second = gen.generate(issue, {}, ids_context=ids)
        assert second.has_suggestions
        assert client.generate.call_count == 1
        assert second.metrics is not None
        assert second.metrics.cache_hit is True
    finally:
        cache.close()


def test_metrics_capture_ollama_durations(tmp_path):
    cache = SuggestionCache(tmp_path / "c.db")
    try:
        client = _make_client()
        gen = SuggestionGenerator(client, cache=cache)
        issue = _space_issue()
        result = gen.generate(issue, {}, ids_context=_ids_for(issue))
        m = result.metrics
        assert m is not None
        assert m.prompt_tokens == 50
        assert m.output_tokens == 30
        assert m.ollama_eval_ms > 0
    finally:
        cache.close()


def test_bsdd_uri_from_llm_is_ignored(tmp_path):
    """LLM não deve ser fonte de verdade para URI; o campo é descartado."""
    cache = SuggestionCache(tmp_path / "c.db")
    try:
        client = _make_client(_JSON_WITH_BSDD_URI)
        gen = SuggestionGenerator(client, cache=cache)
        result = gen.generate(_space_issue(), {}, ids_context=_ids_for(_space_issue()))
        assert result.has_suggestions
        for s in result.suggestions:
            assert s.bsdd_uri is None
    finally:
        cache.close()


def test_dedup_reuse_in_batch(tmp_path):
    """generate_batch reaproveita sugestão da issue primária para secundárias."""
    cache = SuggestionCache(tmp_path / "c.db")
    try:
        client = _make_client()
        gen = SuggestionGenerator(client, cache=cache)
        a = _space_issue()
        b = _space_issue()
        b.id = "different-id"
        results = gen.generate_batch(
            [a, b],
            {},
            ids_context_map={a.id: _ids_for(a), b.id: _ids_for(b)},
            reuse_map={b.id: a.id},
        )
        assert len(results) == 2
        # primária chamou LLM exatamente uma vez (a segunda usou reuse_map ANTES do cache)
        # mas como reuse acontece em generate_batch e cache também, aceitar 1
        assert client.generate.call_count == 1
        assert results[1].metrics is not None
        assert results[1].metrics.reused_from_issue_id == a.id
    finally:
        cache.close()
