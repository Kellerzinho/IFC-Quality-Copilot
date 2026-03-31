"""Parser de arquivos IDS (Information Delivery Specification) no formato buildingSMART IDS 1.0."""

from lxml import etree

from src.models import IDSSpecification

IDS_NS = "http://standards.buildingsmart.org/IDS"
XS_NS = "http://www.w3.org/2001/XMLSchema"

_IDS = f"{{{IDS_NS}}}"
_XS = f"{{{XS_NS}}}"


def _text(element: "etree._Element | None") -> str:
    """Retorna o texto de um elemento, ou string vazia se None."""
    if element is None:
        return ""
    return (element.text or "").strip()


def _simplevalue(parent: "etree._Element | None") -> str:
    """Extrai valor de <simpleValue> ou <xs:restriction><xs:enumeration value=...>."""
    if parent is None:
        return ""
    # Tenta simpleValue direto (namespace IDS)
    sv = parent.find(f"{_IDS}simpleValue")
    if sv is not None:
        return _text(sv)
    # Tenta xs:restriction/xs:enumeration
    restriction = parent.find(f"{_XS}restriction")
    if restriction is not None:
        enum = restriction.find(f"{_XS}enumeration")
        if enum is not None:
            return enum.get("value", "")
    return ""


def _parse_property_filter(prop_el: "etree._Element") -> dict[str, str]:
    """Extrai {pset, prop, value} de um elemento <property> em <applicability>."""
    pset = _simplevalue(prop_el.find(f"{_IDS}propertySet"))
    prop = _simplevalue(prop_el.find(f"{_IDS}baseName"))
    value_el = prop_el.find(f"{_IDS}value")
    value = _simplevalue(value_el) if value_el is not None else ""
    return {"pset": pset, "prop": prop, "value": value}


def _parse_property_requirement(prop_el: "etree._Element") -> dict[str, str]:
    """Extrai {pset, prop, constraint} de um elemento <property> em <requirements>."""
    pset = _simplevalue(prop_el.find(f"{_IDS}propertySet"))
    prop = _simplevalue(prop_el.find(f"{_IDS}baseName"))
    constraint = "exists"
    value_el = prop_el.find(f"{_IDS}value")
    if value_el is not None:
        restriction = value_el.find(f"{_XS}restriction")
        if restriction is not None:
            # Extrai tipo de restrição do primeiro filho da restriction
            children = list(restriction)
            if children:
                tag_local = children[0].tag.split("}")[-1] if "}" in children[0].tag else children[0].tag
                constraint = tag_local  # ex: "minInclusive", "pattern"
            enum = restriction.find(f"{_XS}enumeration")
            if enum is not None:
                constraint = f"equals:{enum.get('value', '')}"
        else:
            sv = value_el.find(f"{_IDS}simpleValue")
            if sv is not None:
                constraint = f"equals:{_text(sv)}"
    return {"pset": pset, "prop": prop, "constraint": constraint}


def _parse_attribute_requirement(attr_el: "etree._Element") -> dict[str, str]:
    """Extrai {pset, prop, constraint} de um elemento <attribute> em <requirements>.

    Convenção interna: pset="" indica atributo direto do elemento IFC (ex: LongName).
    """
    prop = _simplevalue(attr_el.find(f"{_IDS}name"))
    constraint = "exists"
    value_el = attr_el.find(f"{_IDS}value")
    if value_el is not None:
        restriction = value_el.find(f"{_XS}restriction")
        if restriction is not None:
            min_len = restriction.find(f"{_XS}minLength")
            if min_len is not None and min_len.get("value", "0") != "0":
                constraint = "not_empty"
    return {"pset": "", "prop": prop, "constraint": constraint}


def _parse_relation_requirement(rel_el: "etree._Element") -> dict[str, str]:
    """Extrai {pset, prop, constraint} de um elemento <relation> em <requirements>.

    Convenção interna: pset="IFC_RELATION" indica relação IFC (ex: IfcRelFillsElement).
    """
    prop = _simplevalue(rel_el.find(f"{_IDS}name"))
    return {"pset": "IFC_RELATION", "prop": prop, "constraint": "exists"}


def _parse_specification(spec_el: "etree._Element") -> IDSSpecification:
    """Parseia um elemento <specification> e retorna IDSSpecification."""
    name = spec_el.get("name", "")
    description = spec_el.get("description") or None

    applicability_entity = ""
    applicability_filters: list[dict[str, str]] = []
    requirements: list[dict[str, str]] = []

    applicability_el = spec_el.find(f"{_IDS}applicability")
    if applicability_el is not None:
        entity_el = applicability_el.find(f"{_IDS}entity")
        if entity_el is not None:
            name_el = entity_el.find(f"{_IDS}name")
            applicability_entity = _simplevalue(name_el)

        for prop_el in applicability_el.findall(f"{_IDS}property"):
            applicability_filters.append(_parse_property_filter(prop_el))

    requirements_el = spec_el.find(f"{_IDS}requirements")
    if requirements_el is not None:
        for prop_el in requirements_el.findall(f"{_IDS}property"):
            requirements.append(_parse_property_requirement(prop_el))
        for attr_el in requirements_el.findall(f"{_IDS}attribute"):
            requirements.append(_parse_attribute_requirement(attr_el))
        for rel_el in requirements_el.findall(f"{_IDS}relation"):
            requirements.append(_parse_relation_requirement(rel_el))

    return IDSSpecification(
        name=name,
        description=description,
        applicability_entity=applicability_entity,
        applicability_filters=applicability_filters,
        requirements=requirements,
    )


def parse_ids(ids_filepath: str) -> list[IDSSpecification]:
    """Parseia um arquivo IDS (XML, padrão buildingSMART IDS 1.0) e retorna lista de specifications.

    Namespace IDS: http://standards.buildingsmart.org/IDS

    Convenções para facets não-padrão:
    - <attribute> em <requirements>: pset="" indica atributo direto do elemento IFC
    - <relation> em <requirements>: pset="IFC_RELATION" indica relação IFC
    """
    try:
        tree = etree.parse(ids_filepath)
    except OSError as exc:
        raise ValueError(f"Arquivo IDS não encontrado ou inacessível: '{ids_filepath}' — {exc}") from exc
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"Arquivo IDS inválido (XML malformado): '{ids_filepath}' — {exc}") from exc
    root = tree.getroot()

    specifications_el = root.find(f"{_IDS}specifications")
    if specifications_el is None:
        return []

    return [
        _parse_specification(spec_el)
        for spec_el in specifications_el.findall(f"{_IDS}specification")
    ]
