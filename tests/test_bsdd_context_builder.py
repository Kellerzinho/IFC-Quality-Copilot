"""Testes para BSDDContextBuilder."""

from unittest.mock import MagicMock

import httpx

from src.bsdd.client import BSDDClient
from src.bsdd.context_builder import BSDDContextBuilder
from src.models import BSDDClassification, BSDDContext, BSDDProperty, Issue


def _make_issue(issue_type: str, **context_overrides) -> Issue:
    return Issue(
        element_guid="A" * 22,
        element_class="IfcSpace" if issue_type == "space_unnamed" else "IfcWall",
        element_name="Room 101" if issue_type == "space_unnamed" else "Parede Externa 01",
        issue_type=issue_type,  # type: ignore[arg-type]
        severity="high",
        description="Issue de teste",
        context=context_overrides,
    )


def test_build_pset_missing_returns_properties():
    client = MagicMock(spec=BSDDClient)
    client.search_class.return_value = [
        {
            "name": "IfcWall",
            "uri": "https://example.org/classes/ifcwall",
            "domain": "IFC",
        }
    ]
    client.get_class_properties.return_value = [
        BSDDProperty(name="FireRating", data_type="String", allowed_values=["REI 60"]),
        BSDDProperty(name="IsExternal", data_type="Boolean"),
    ]

    builder = BSDDContextBuilder(client)
    issue = _make_issue("pset_missing", check_property="FireRating", pset_name="Pset_WallCommon")

    context = builder.build(issue)

    assert context.class_name == "IfcWall"
    assert context.class_uri == "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/class/IfcWall"
    assert [prop.name for prop in context.related_properties] == ["FireRating"]
    assert context.related_properties[0].uri == "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/prop/FireRating"
    assert context.source_uris == [
        "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/class/IfcWall",
        "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/prop/FireRating",
    ]
    assert context.source_status == "live"


def test_build_space_unnamed_returns_classifications():
    client = MagicMock(spec=BSDDClient)
    client.search_class.return_value = [
        {
            "name": "Space",
            "uri": "https://example.org/classes/space",
            "domain": "IFC",
        },
        {
            "name": "Toilet room",
            "uri": "https://example.org/classifications/omniclass/table13/toilet-room",
            "domain": "OmniClass Table 13",
        },
        {
            "name": "Office",
            "uri": "https://example.org/classifications/uniclass/spaces/office",
            "domain": "Uniclass Spaces",
        },
    ]
    client.get_class_properties.return_value = []

    builder = BSDDContextBuilder(client)
    issue = _make_issue("space_unnamed")

    context = builder.build(issue)

    assert context.source_status == "live"
    assert len(context.classification_suggestions) == 2
    assert context.classification_suggestions[0].system_name == "OmniClass Table 13"
    assert context.classification_suggestions[1].system_name == "Uniclass Spaces"


def test_build_offline_returns_empty_context():
    client = MagicMock(spec=BSDDClient)
    client.search_class.side_effect = httpx.ConnectError("offline")

    builder = BSDDContextBuilder(client)
    issue = _make_issue("system_unclassified")

    context = builder.build(issue)

    assert context.class_name is None
    assert context.class_uri is None
    assert context.related_properties == []
    assert context.classification_suggestions == []
    assert context.source_status == "offline"


def test_build_context_text_formats_correctly():
    builder = BSDDContextBuilder(MagicMock(spec=BSDDClient))
    context = BSDDContext(
        class_name="Wall",
        class_uri="https://example.org/classes/wall",
        related_properties=[
            BSDDProperty(
                name="ThermalTransmittance",
                data_type="real",
                unit="W/(m²·K)",
                description="Pset_WallCommon thermal performance",
            ),
            BSDDProperty(
                name="IsExternal",
                data_type="boolean",
            ),
            BSDDProperty(
                name="FireRating",
                data_type="string",
                allowed_values=["REI 30", "REI 60", "REI 90", "REI 120"],
            ),
        ],
        classification_suggestions=[
            BSDDClassification(
                name="External wall",
                code="EF_25_10",
                uri="https://example.org/classifications/external-wall",
                system_name="Uniclass 2015",
            )
        ],
    )

    text = builder.build_context_text(context)

    assert "VOCABULARIO bSDD (classe: Wall, URI: https://example.org/classes/wall):" in text
    assert "Propriedades validas para Pset_WallCommon:" in text
    assert "- ThermalTransmittance (real, W/(m²·K))" in text
    assert "- IsExternal (boolean)" in text
    assert "- FireRating (string), valores: REI 30, REI 60, REI 90, REI 120" in text
    assert "Classificacoes relevantes:" in text
    assert "- External wall, codigo: EF_25_10, sistema: Uniclass 2015, URI: https://example.org/classifications/external-wall" in text


def test_build_context_text_empty_when_no_data():
    builder = BSDDContextBuilder(MagicMock(spec=BSDDClient))

    assert builder.build_context_text(BSDDContext()) == ""


def test_build_preserves_non_ifc_uris_for_external_classifications():
    client = MagicMock(spec=BSDDClient)
    client.search_class.return_value = [
        {
            "name": "Space",
            "uri": "https://example.org/classes/space",
            "domain": "IFC",
        },
        {
            "name": "Office",
            "uri": "https://example.org/classifications/uniclass/spaces/office",
            "domain": "Uniclass Spaces",
        },
    ]
    client.get_class_properties.return_value = []

    builder = BSDDContextBuilder(client)
    issue = _make_issue("space_unnamed")

    context = builder.build(issue)

    assert context.class_uri == "https://example.org/classes/space"
    assert context.classification_suggestions[0].uri == "https://example.org/classifications/uniclass/spaces/office"
