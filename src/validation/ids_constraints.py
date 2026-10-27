"""Matriz de suporte da condição ``m1-e3-evidence-v1`` e classificação estrita (plano §5.2).

O ``CAPABILITY_MANIFEST`` é artefato de código versionado; seu hash entra na
identidade do verificador. Fora da matriz, o resultado é explícito
(``not_verified`` com motivo próprio), nunca XML inválido nem aprovação. A matriz é
estreita de propósito: não é cobertura total do IDS.
"""

from dataclasses import dataclass
from typing import Final

from src.operations.contracts import canonical_sha256
from src.translator.ids_document import IDSFacet, IDSSpecification, SpecificationCardinality

TEXT_DATATYPES: Final = frozenset({"IFCLABEL", "IFCTEXT", "IFCIDENTIFIER"})
SCALAR_DATATYPES: Final = frozenset({"IFCBOOLEAN", "IFCINTEGER"})
PROPERTY_CARDINALITIES: Final = frozenset({"required", "optional", "prohibited"})
SUPPORTED_SPEC_CARDINALITIES: Final = frozenset({(1, "unbounded"), (0, "unbounded"), (0, 0)})
PHYSICAL_DATATYPES: Final = frozenset(
    {"IFCREAL", "IFCNUMERICMEASURE", "IFCPOSITIVERATIOMEASURE", "IFCRATIOMEASURE"}
)

CAPABILITY_MANIFEST: Final = {
    "manifest_id": "m1-e3-ids-capability",
    "version": "1.0.0",
    "backend": {"ifctester": "0.8.5", "ifcopenshell": "0.8.5", "xmlschema": "4.3.2"},
    "ifc_schemas": ["IFC4"],
    "specification_cardinality": [[1, "unbounded"], [0, "unbounded"], [0, 0]],
    "applicability": {
        "facets": ["entity"],
        "entity_name": "simple_literal_declared_in_IFC4",
        "entity_class": "IfcObject_subtype_only",
        "predefined_type": "absent_or_simple_literal_not_USERDEFINED",
        "include_subtypes": False,
    },
    "requirements": {
        "facets": ["property"],
        "selectors": "simple_literal_property_set_and_base_name",
        "carrier": "IfcPropertySingleValue",
        "text_datatypes": sorted(TEXT_DATATYPES),
        "scalar_datatypes": sorted(SCALAR_DATATYPES),
        "text_value": ["absent", "simple_nonempty_literal", "xs_string_enumeration"],
        "scalar_value": ["absent"],
        "property_cardinality": sorted(PROPERTY_CARDINALITIES),
        "units": "not_applicable_only",
    },
    "element_gates": [
        "ambiguous_source",
        "unsupported_carrier",
        "unsupported_inherited_property_overlay",
        "unsupported_unit",
    ],
    "document_gates": ["unknown_entity_name", "unsupported_empty_simple_value"],
}
CAPABILITY_MANIFEST_SHA256: Final = canonical_sha256(CAPABILITY_MANIFEST)


@dataclass(frozen=True)
class Support:
    """Resultado da classificação de uma célula da matriz."""

    cell_id: str
    reason: str | None = None

    @property
    def supported(self) -> bool:
        """Sem motivo de recusa."""
        return self.reason is None


def classify_schema(model_schema: str, spec: IDSSpecification) -> Support:
    """IFC4 no modelo e declarado pela especificação."""
    if model_schema != "IFC4":
        return Support("schema", "unsupported_schema")
    if "IFC4" not in spec.ifc_versions:
        return Support("schema", "schema_mismatch")
    return Support("schema")


def classify_cardinality(card: SpecificationCardinality) -> Support:
    """Só as três tuplas cobertas; máximo finito menor que o mínimo é inválido."""
    pair = (card.min_effective, card.max_effective)
    if card.max_effective != "unbounded" and card.max_effective < card.min_effective:
        return Support("specification_cardinality", "invalid_cardinality")
    if pair not in SUPPORTED_SPEC_CARDINALITIES:
        return Support("specification_cardinality", "unsupported_cardinality")
    return Support("specification_cardinality")


def _literal(facet: IDSFacet, name: str) -> str | None:
    value = facet.parameter(name)
    if value is None or value.kind != "simple" or not value.text:
        return None
    return value.text


def classify_applicability(spec: IDSSpecification) -> Support:
    """Uma faceta entity com nome literal e PredefinedType ordinário opcional."""
    if len(spec.applicability) != 1 or spec.applicability[0].tag != "entity":
        return Support("applicability", "unsupported_applicability")
    facet = spec.applicability[0]
    if _literal(facet, "name") is None:
        return Support("applicability", "unsupported_applicability")
    predefined = facet.parameter("predefinedType")
    if predefined is not None:
        literal = _literal(facet, "predefinedType")
        if literal is None or literal == "USERDEFINED":
            return Support("applicability", "unsupported_applicability")
    return Support("applicability")


def entity_name(spec: IDSSpecification) -> str:
    """Nome literal da classe aplicável (só depois de ``classify_applicability``)."""
    name = _literal(spec.applicability[0], "name")
    assert name is not None
    return name


def requirement_cardinality(facet: IDSFacet) -> tuple[str, str]:
    """Cardinalidade da faceta e sua origem; omitida é ``required`` pelo XSD."""
    raw = facet.attribute("cardinality")
    return (raw, "explicit") if raw is not None else ("required", "schema_default")


def classify_requirement(facet: IDSFacet) -> Support:
    """Faceta property literal, portador simples, tipo e restrição dentro da matriz."""
    cell = f"requirement:{facet.tag}"
    if facet.tag != "property":
        return Support(cell, "unsupported_facet")
    if _literal(facet, "propertySet") is None or _literal(facet, "baseName") is None:
        return Support(cell, "unsupported_selector")
    cardinality, _ = requirement_cardinality(facet)
    if cardinality not in PROPERTY_CARDINALITIES:
        return Support(cell, "unsupported_cardinality")
    data_type = facet.attribute("dataType")
    if data_type is None:
        return Support(cell, "unsupported_datatype")
    if data_type.endswith("MEASURE") or data_type in PHYSICAL_DATATYPES:
        return Support(cell, "unsupported_unit")
    if data_type not in TEXT_DATATYPES | SCALAR_DATATYPES:
        return Support(cell, "unsupported_datatype")
    value = facet.parameter("value")
    if value is None:
        return Support(f"{cell}:presence")
    if value.kind == "simple":
        if value.text == "":
            return Support(cell, "unsupported_empty_simple_value")
        if data_type not in TEXT_DATATYPES:
            return Support(cell, "unsupported_constraint")
        return Support(f"{cell}:literal")
    if (
        data_type in TEXT_DATATYPES
        and value.base == "xs:string"
        and value.facets
        and all(item.name == "enumeration" for item in value.facets)
    ):
        return Support(f"{cell}:enumeration")
    return Support(cell, "unsupported_constraint")


def property_selector(facet: IDSFacet) -> tuple[str, str]:
    """Conjunto e nome literais de uma faceta property suportada."""
    pset, name = _literal(facet, "propertySet"), _literal(facet, "baseName")
    assert pset is not None
    assert name is not None
    return pset, name
