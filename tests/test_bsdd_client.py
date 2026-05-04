"""Testes do cliente bSDD com cache e fallback."""

import json
from unittest.mock import MagicMock

import httpx

from src.bsdd.client import BSDDClient
from src.bsdd.models import BSDDClassData, BSDDPropertyData
from src.models import BSDDProperty


def _mock_response(payload: dict) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def test_search_class_returns_results(tmp_path) -> None:
    client = BSDDClient(cache_path=str(tmp_path / "bsdd_cache.json"))
    client._client.get = MagicMock(
        return_value=_mock_response(
            {
                "classes": [
                    {
                        "referenceCode": "IfcWall",
                        "name": "Wall",
                        "uri": "https://example.org/classes/ifcwall",
                        "dictionaryName": "IFC",
                    }
                ]
            }
        )
    )
    client._cache["dictionary_uri:IFC"] = "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3"

    result = client.search_class("IfcWall")

    assert result == [
        {
            "name": "IfcWall",
            "uri": "https://example.org/classes/ifcwall",
            "domain": "IFC",
        }
    ]
    client._client.get.assert_called_once_with(
        "/api/Class/Search/v1",
        params={
            "SearchText": "IfcWall",
            "DictionaryUris": ["https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3"],
        },
    )


def test_search_class_caches_result(tmp_path) -> None:
    client = BSDDClient(cache_path=str(tmp_path / "bsdd_cache.json"))
    client._client.get = MagicMock(
        return_value=_mock_response(
            {
                "classes": [
                    {
                        "referenceCode": "IfcDoor",
                        "uri": "https://example.org/classes/ifcdoor",
                        "dictionaryName": "IFC",
                    }
                ]
            }
        )
    )
    client._cache["dictionary_uri:IFC"] = "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3"

    result1 = client.search_class("IfcDoor")
    result2 = client.search_class("IfcDoor")

    assert result1 == result2
    client._client.get.assert_called_once()


def test_search_class_offline_returns_empty(tmp_path) -> None:
    client = BSDDClient(cache_path=str(tmp_path / "bsdd_cache.json"))
    client._client.get = MagicMock(side_effect=httpx.ConnectError("offline"))
    client._cache["dictionary_uri:IFC"] = "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3"

    result = client.search_class("IfcWindow")

    assert result == []


def test_get_class_properties_parses_correctly(tmp_path) -> None:
    client = BSDDClient(cache_path=str(tmp_path / "bsdd_cache.json"))
    client._client.get = MagicMock(
        return_value=_mock_response(
            {
                "classProperties": [
                    {
                        "name": "FireRating",
                        "propertyUri": "https://example.org/properties/firerating",
                        "dataType": "String",
                        "unit": {"symbol": "min"},
                        "allowedValues": [{"value": "30"}, {"value": "60"}],
                        "description": "Tempo de resistencia ao fogo",
                    }
                ]
            }
        )
    )

    result = client.get_class_properties("https://example.org/classes/ifcwall")

    assert result == [
        BSDDProperty(
            name="FireRating",
            uri="https://example.org/properties/firerating",
            data_type="String",
            unit="min",
            allowed_values=["30", "60"],
            description="Tempo de resistencia ao fogo",
        )
    ]
    client._client.get.assert_called_once_with(
        "/api/Class/Properties/v1",
        params={"ClassUri": "https://example.org/classes/ifcwall"},
    )


def test_get_property_values_empty_when_none(tmp_path) -> None:
    client = BSDDClient(cache_path=str(tmp_path / "bsdd_cache.json"))
    client._client.get = MagicMock(
        return_value=_mock_response(
            {
                "name": "AcousticRating",
                "allowedValues": None,
            }
        )
    )

    result = client.get_property_values("https://example.org/properties/acousticrating")

    assert result == []
    client._client.get.assert_called_once_with(
        "/api/Property/v4",
        params={"uri": "https://example.org/properties/acousticrating"},
    )


def test_resolve_class_returns_structured_object_and_persistent_cache(tmp_path) -> None:
    cache_path = str(tmp_path / "bsdd_cache.json")
    client = BSDDClient(cache_path=cache_path)
    client._client.get = MagicMock(
        return_value=_mock_response(
            {
                "classes": [
                    {
                        "referenceCode": "IfcWall",
                        "name": "IfcWall",
                        "uri": "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/class/IfcWall",
                        "dictionaryUri": "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3",
                        "dictionaryName": "IFC",
                    }
                ]
            }
        )
    )
    client._cache["dictionary_uri:IFC"] = "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3"

    result = client.resolve_class(query="IfcWall")

    assert isinstance(result, BSDDClassData)
    assert result.canonical_uri == "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/class/IfcWall"
    assert result.display_name == "IfcWall"
    assert result.dictionary_uri == "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3"
    assert result.source_origin == "bsdd_search"
    assert result.status == "resolved"

    payload = json.loads(tmp_path.joinpath("bsdd_cache.json").read_text(encoding="utf-8"))
    assert "class_search" in payload


def test_resolve_property_returns_structured_object() -> None:
    client = BSDDClient()
    client._client.get = MagicMock(
        return_value=_mock_response(
            {
                "name": "FireRating",
                "uri": "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/prop/FireRating",
                "dataType": "String",
                "allowedValues": [{"value": "REI 60"}],
            }
        )
    )

    result = client.resolve_property(
        "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/prop/FireRating"
    )

    assert isinstance(result, BSDDPropertyData)
    assert result.canonical_uri == "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/prop/FireRating"
    assert result.display_name == "FireRating"
    assert result.source_origin == "bsdd_property_uri"
    assert result.status == "resolved"


def test_resolve_class_marks_unresolved_when_no_safe_match() -> None:
    client = BSDDClient()
    client._client.get = MagicMock(return_value=_mock_response({"classes": []}))
    client._cache["dictionary_uri:IFC"] = "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3"

    result = client.resolve_class(query="InventedWall")

    assert result.canonical_uri is None
    assert result.status == "unresolved"
    assert result.review_required is True
