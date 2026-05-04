"""Testes para integração bSDD."""

from unittest.mock import MagicMock

import httpx

from src.bsdd.client import BSDDClient
from src.bsdd.context_builder import BSDDContextBuilder
from src.models import IDSContext, Issue


def _make_issue() -> Issue:
    return Issue(
        element_guid="A" * 22,
        element_class="IfcWall",
        element_name="Parede básica:parede externa 20cm_growarq:780998",
        issue_type="pset_missing",
        severity="high",
        description="FireRating ausente",
        context={"check_property": "FireRating"},
    )


def test_bsdd_client_disables_path_after_404(tmp_path):
    client = BSDDClient(
        base_url="https://api.bsdd.buildingsmart.org",
        cache_path=str(tmp_path / "bsdd_cache.json"),
    )
    response = MagicMock(spec=httpx.Response)
    response.status_code = 404
    error = httpx.HTTPStatusError("404", request=MagicMock(spec=httpx.Request), response=response)

    client._client.get = MagicMock(side_effect=error)

    result1 = client.search_class("IfcWall")
    result2 = client.search_class("IfcDoor")

    assert result1 == []
    assert result2 == []
    assert client._client.get.call_count == 1


def test_bsdd_context_builder_sanitizes_search_query():
    client = MagicMock(spec=BSDDClient)
    client.search_class.return_value = []
    builder = BSDDContextBuilder(client)
    issue = _make_issue()
    ids_context = IDSContext(
        issue_id=issue.id,
        requirement_id="req-1",
        specification_name="Spec",
        check_pset="Pset_WallCommon",
        check_property="FireRating",
        check_type="exists",
        severity="high",
    )

    context = builder.build(issue, ids_context)

    assert context is not None
    assert "growarq" not in context.search_query.lower()
    assert "780998" not in context.search_query
    assert client.search_class.called
