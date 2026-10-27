"""Entrada IDS estrita: XML seguro, XSD oficial offline e inventário fiel ao documento."""

import hashlib
import socket

import pytest

pytest.importorskip("xmlschema", reason="extra e3 não instalado (xmlschema==4.3.2)")

from src.translator.ids_document import IDSFacet, IDSGateError, IDSValue, parse_ids_document
from src.validation.schema_bundle import SchemaBundle
from tests.validation import ids_builders as x


def _p(facet: IDSFacet, name: str) -> IDSValue:
    value = facet.parameter(name)
    assert value is not None
    return value


@pytest.fixture(scope="module")
def bundle() -> SchemaBundle:
    return SchemaBundle.load()


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("rede proibida")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)


def test_inventory_keeps_bytes_identity_and_literal_parameters(bundle: SchemaBundle) -> None:
    data = x.ids(
        x.spec(
            "Paredes",
            x.entity("IFCWALL", "SOLIDWALL"),
            x.prop("Pset_X", "Target", value=x.simple("ABC")),
            identifier="R-1",
        )
    )
    document = parse_ids_document(data, bundle)

    assert document.ids_sha256 == hashlib.sha256(data).hexdigest()
    assert document.size_bytes == len(data)
    (spec,) = document.specifications
    assert (spec.index, spec.name, spec.identifier, spec.ifc_versions) == (
        0,
        "Paredes",
        "R-1",
        ("IFC4",),
    )
    (applicability,) = spec.applicability
    assert applicability.tag == "entity"
    assert _p(applicability, "name").text == "IFCWALL"
    assert _p(applicability, "predefinedType").text == "SOLIDWALL"
    (requirement,) = spec.requirements
    assert requirement.location.section == "requirements"
    assert requirement.location.index == 0
    assert requirement.attribute("dataType") == "IFCLABEL"
    assert _p(requirement, "value").text == "ABC"
    assert requirement.fragment_sha256 == hashlib.sha256(requirement.fragment.encode()).hexdigest()


def test_empty_simple_value_and_whitespace_are_literal_not_omitted(bundle: SchemaBundle) -> None:
    data = x.ids(
        x.spec(
            "S",
            x.entity("IFCWALL"),
            x.prop("P", "A", value=x.simple(""))
            + x.prop("P", "B")
            + x.prop("P", "C", value=x.simple("  ")),
        )
    )
    a, b, c = parse_ids_document(data, bundle).specifications[0].requirements

    assert _p(a, "value").kind == "simple"
    assert _p(a, "value").text == ""
    assert b.parameter("value") is None
    assert _p(c, "value").text == "  "


def test_full_enumeration_is_preserved_in_order(bundle: SchemaBundle) -> None:
    data = x.ids(x.spec("S", x.entity("IFCWALL"), x.prop("P", "E", value=x.enum("C", "A", "B"))))
    (requirement,) = parse_ids_document(data, bundle).specifications[0].requirements
    value = _p(requirement, "value")

    assert value.kind == "restriction"
    assert value.base == "xs:string"
    assert [(f.name, f.value) for f in value.facets] == [
        ("enumeration", "C"),
        ("enumeration", "A"),
        ("enumeration", "B"),
    ]


def test_interleaved_facets_keep_original_order_and_occurrence_indexes(
    bundle: SchemaBundle,
) -> None:
    data = x.ids(
        x.spec(
            "S",
            x.entity("IFCWALL"),
            x.prop("P", "Um") + x.attribute("Name") + x.prop("P", "Dois"),
        )
    )
    requirements = parse_ids_document(data, bundle).specifications[0].requirements

    assert [(r.location.index, r.tag, r.occurrence_index) for r in requirements] == [
        (0, "property", 0),
        (1, "attribute", 0),
        (2, "property", 1),
    ]
    assert [_p(r, "baseName").text for r in requirements if r.tag == "property"] == [
        "Um",
        "Dois",
    ]


def test_duplicate_identifiers_are_separate_locations(bundle: SchemaBundle) -> None:
    data = x.ids(
        x.spec("A", x.entity("IFCWALL"), x.prop("P", "X"), identifier="mesmo"),
        x.spec("A", x.entity("IFCWALL"), x.prop("P", "X"), identifier="mesmo"),
    )
    first, second = parse_ids_document(data, bundle).specifications

    assert first.requirements[0].location != second.requirements[0].location
    assert (first.index, second.index) == (0, 1)
    assert first.requirements[0].location.key() != second.requirements[0].location.key()


@pytest.mark.parametrize(
    ("min_occurs", "max_occurs", "expected"),
    [
        ("1", "unbounded", ((1, "explicit"), ("unbounded", "explicit"))),
        (None, None, ((1, "schema_default"), (1, "schema_default"))),
        (None, "unbounded", ((1, "schema_default"), ("unbounded", "explicit"))),
        ("0", None, ((0, "explicit"), (1, "schema_default"))),
        ("2", "1", ((2, "explicit"), (1, "explicit"))),
    ],
)
def test_specification_cardinality_applies_bundle_defaults(
    bundle: SchemaBundle, min_occurs: str | None, max_occurs: str | None, expected: tuple
) -> None:
    data = x.ids(x.spec("S", x.entity("IFCWALL"), min_occurs=min_occurs, max_occurs=max_occurs))
    card = parse_ids_document(data, bundle).specifications[0].cardinality

    assert (
        (card.min_effective, card.min_origin),
        (card.max_effective, card.max_origin),
    ) == expected
    assert card.min_raw == min_occurs
    assert card.max_raw == max_occurs


@pytest.mark.parametrize(
    "prolog",
    [
        '<!DOCTYPE ids [<!ENTITY xxe SYSTEM "http://example.invalid/segredo">]>',
        '<!DOCTYPE ids [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]>',
        '<!DOCTYPE ids SYSTEM "http://example.invalid/ids.dtd">',
    ],
)
def test_dtd_and_entities_are_refused_offline(
    bundle: SchemaBundle, prolog: str, no_network: None
) -> None:
    with pytest.raises(IDSGateError) as refused:
        parse_ids_document(x.ids(x.spec("S", x.entity("IFCWALL")), prolog=prolog), bundle)
    assert refused.value.reason == "xml_unsafe"


def test_schema_location_hint_is_ignored_and_never_fetched(
    bundle: SchemaBundle, no_network: None
) -> None:
    hint = (
        ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        ' xsi:schemaLocation="http://standards.buildingsmart.org/IDS https://example.invalid/x.xsd"'
    )
    document = parse_ids_document(x.ids(x.spec("S", x.entity("IFCWALL")), root_attrs=hint), bundle)
    assert document.specifications[0].name == "S"


def test_size_depth_and_node_limits_allow_equality_and_refuse_excess(
    bundle: SchemaBundle,
) -> None:
    data = x.ids(x.spec("S", x.entity("IFCWALL")))
    exact = {"max_bytes": len(data), "max_depth": 7, "max_nodes": 9}
    assert parse_ids_document(data, bundle, **exact).specifications
    for name in exact:
        smaller = {**exact, name: exact[name] - 1}
        with pytest.raises(IDSGateError) as refused:
            parse_ids_document(data, bundle, **smaller)
        assert refused.value.reason == "resource_limit_exceeded"


def test_malformed_xml_and_xsd_invalid_are_distinct_refusals(bundle: SchemaBundle) -> None:
    with pytest.raises(IDSGateError) as malformed:
        parse_ids_document(b"<ids><unclosed></ids>", bundle)
    assert malformed.value.reason == "xml_malformed"
    assert malformed.value.partial is None

    invalid = x.ids(x.spec("S", x.entity("IFCWALL"), ifc="IFC9"))
    with pytest.raises(IDSGateError) as xsd:
        parse_ids_document(invalid, bundle)
    assert xsd.value.reason == "xsd_invalid"
    assert xsd.value.partial is not None
    assert xsd.value.partial.specifications[0].name == "S"


def test_unsupported_features_are_inventoried_not_invalid(bundle: SchemaBundle) -> None:
    data = x.ids(
        x.spec(
            "S",
            x.entity("IFCWALL") + x.prop("P", "Filtro"),
            x.attribute("Name")
            + x.prop("P", "Q", data_type="IFCLENGTHMEASURE")
            + x.prop("P", "R", pset_value=x.pattern("Pset_.*")),
        )
    )
    spec = parse_ids_document(data, bundle).specifications[0]

    assert [f.tag for f in spec.applicability] == ["entity", "property"]
    assert [r.tag for r in spec.requirements] == ["attribute", "property", "property"]
    assert _p(spec.requirements[2], "propertySet").kind == "restriction"
    assert _p(spec.requirements[2], "propertySet").facets[0].name == "pattern"


def test_inventory_diverging_from_backend_decode_is_refused(
    bundle: SchemaBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E3-03: inventário truncado (como antes da correção) não chega ao backend."""
    import src.translator.ids_document as module

    data = x.ids(
        x.spec(
            "S",
            x.entity("IFCWALL"),
            x.prop("Pset_X", "A", value="<simpleValue>AB<!-- c -->C</simpleValue>"),
        )
    )
    assert _p(parse_ids_document(data, bundle).specifications[0].requirements[0], "value").text == (
        "ABC"
    )
    original = module._value

    def truncated(element: object) -> IDSValue | None:
        value = original(element)
        if value is not None and value.kind == "simple" and value.text == "ABC":
            return IDSValue(kind="simple", text="AB")
        return value

    monkeypatch.setattr(module, "_value", truncated)
    with pytest.raises(IDSGateError) as refused:
        parse_ids_document(data, bundle)
    assert refused.value.reason == "inventory_mismatch"
