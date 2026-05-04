"""Parser de arquivos IDS (Information Delivery Specification) no formato buildingSMART IDS 1.0."""

from functools import lru_cache
from pathlib import Path

from loguru import logger
from lxml import etree

from src.config import IDS_XSD_PATH
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

    sv = parent.find(f"{_IDS}simpleValue")
    if sv is not None:
        return _text(sv)

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


def _extract_constraint(value_el: "etree._Element | None") -> tuple[str, str]:
    """Extrai (constraint, constraint_type) de um elemento <value> ou None."""
    if value_el is None:
        return "exists", ""

    sv = value_el.find(f"{_IDS}simpleValue")
    if sv is not None:
        return f"equals:{_text(sv)}", "xs:string"

    restriction = value_el.find(f"{_XS}restriction")
    if restriction is None:
        return "exists", ""

    base = restriction.get("base", "")
    if "}" in base:
        base = base.split("}")[-1]
    constraint_type = base

    children = list(restriction)
    if not children:
        return "exists", constraint_type

    first = children[0]
    tag_local = first.tag.split("}")[-1] if "}" in first.tag else first.tag

    if tag_local == "enumeration":
        return f"equals:{first.get('value', '')}", "xs:string"

    if tag_local == "minLength":
        if first.get("value", "0") != "0":
            return "not_empty", "xs:string"
        return "exists", "xs:string"

    return tag_local, constraint_type


def _parse_property_requirement(prop_el: "etree._Element") -> dict[str, str]:
    """Extrai requirement de <property> em <requirements>."""
    pset = _simplevalue(prop_el.find(f"{_IDS}propertySet"))
    prop = _simplevalue(prop_el.find(f"{_IDS}baseName"))
    facet_type = "quantity" if pset.startswith("Qto_") else "property"
    value_el = prop_el.find(f"{_IDS}value")
    constraint, constraint_type = _extract_constraint(value_el)
    return {
        "facet_type": facet_type,
        "pset": pset,
        "prop": prop,
        "constraint": constraint,
        "constraint_type": constraint_type,
    }


def _parse_attribute_requirement(attr_el: "etree._Element") -> dict[str, str]:
    """Extrai requirement de <attribute> em <requirements>."""
    prop = _simplevalue(attr_el.find(f"{_IDS}name"))
    value_el = attr_el.find(f"{_IDS}value")
    constraint, constraint_type = _extract_constraint(value_el)
    return {
        "facet_type": "property",
        "pset": "",
        "prop": prop,
        "constraint": constraint,
        "constraint_type": constraint_type,
    }


def _parse_relation_requirement(rel_el: "etree._Element") -> dict[str, str]:
    """Extrai requirement de <relation> em <requirements>."""
    prop = _simplevalue(rel_el.find(f"{_IDS}name"))
    return {
        "facet_type": "relation",
        "pset": "IFC_RELATION",
        "prop": prop,
        "constraint": "exists",
        "constraint_type": "",
    }


def _parse_material_requirement(mat_el: "etree._Element") -> dict[str, str]:
    """Extrai requirement de <material> em <requirements>."""
    value_el = mat_el.find(f"{_IDS}value")
    prop = _simplevalue(value_el) if value_el is not None else ""
    constraint, constraint_type = _extract_constraint(value_el)
    return {
        "facet_type": "material",
        "pset": "",
        "prop": prop,
        "constraint": constraint,
        "constraint_type": constraint_type,
    }


def _parse_material_applicability_filter(mat_el: "etree._Element") -> dict[str, str]:
    """Extrai filtro de <material> em <applicability>."""
    value_el = mat_el.find(f"{_IDS}value")
    value = _simplevalue(value_el) if value_el is not None else ""
    return {"pset": "", "prop": "material", "value": value}


def _parse_classification_requirement(cls_el: "etree._Element") -> dict[str, str]:
    """Extrai requirement de <classification> em <requirements>."""
    system_el = cls_el.find(f"{_IDS}system")
    pset = _simplevalue(system_el) if system_el is not None else ""
    value_el = cls_el.find(f"{_IDS}value")
    prop = _simplevalue(value_el) if value_el is not None else ""
    constraint, constraint_type = _extract_constraint(value_el)
    return {
        "facet_type": "classification",
        "pset": pset,
        "prop": prop,
        "constraint": constraint,
        "constraint_type": constraint_type,
    }


def _parse_partof_requirement(part_el: "etree._Element") -> dict[str, str]:
    """Extrai requirement de <partOf> em <requirements>."""
    entity_el = part_el.find(f"{_IDS}entity")
    prop = ""
    if entity_el is not None:
        name_el = entity_el.find(f"{_IDS}name")
        prop = _simplevalue(name_el)
    return {
        "facet_type": "relation",
        "pset": "IFC_RELATION",
        "prop": prop,
        "constraint": "exists",
        "constraint_type": "",
    }


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
        for mat_el in applicability_el.findall(f"{_IDS}material"):
            applicability_filters.append(_parse_material_applicability_filter(mat_el))

    requirements_el = spec_el.find(f"{_IDS}requirements")
    if requirements_el is not None:
        for prop_el in requirements_el.findall(f"{_IDS}property"):
            requirements.append(_parse_property_requirement(prop_el))
        for attr_el in requirements_el.findall(f"{_IDS}attribute"):
            requirements.append(_parse_attribute_requirement(attr_el))
        for rel_el in requirements_el.findall(f"{_IDS}relation"):
            requirements.append(_parse_relation_requirement(rel_el))
        for mat_el in requirements_el.findall(f"{_IDS}material"):
            requirements.append(_parse_material_requirement(mat_el))
        for cls_el in requirements_el.findall(f"{_IDS}classification"):
            requirements.append(_parse_classification_requirement(cls_el))
        for part_el in requirements_el.findall(f"{_IDS}partOf"):
            requirements.append(_parse_partof_requirement(part_el))

    return IDSSpecification(
        name=name,
        description=description,
        applicability_entity=applicability_entity,
        applicability_filters=applicability_filters,
        requirements=requirements,
    )


def validate_ids_against_xsd(ids_path: Path, xsd_path: Path) -> list[str]:
    """Valida o XML IDS contra o XSD informado e retorna os erros encontrados."""
    try:
        tree = etree.parse(str(ids_path))
    except OSError as exc:
        raise ValueError(f"Arquivo IDS não encontrado ou inacessível: '{ids_path}' - {exc}") from exc
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"Arquivo IDS inválido (XML malformado): '{ids_path}' - {exc}") from exc

    try:
        schema_doc = etree.parse(str(xsd_path))
        schema = etree.XMLSchema(schema_doc)
    except OSError as exc:
        raise ValueError(f"Arquivo XSD não encontrado ou inacessível: '{xsd_path}' - {exc}") from exc
    except (etree.XMLSyntaxError, etree.XMLSchemaParseError) as exc:
        raise ValueError(f"Arquivo XSD inválido: '{xsd_path}' - {exc}") from exc

    if schema.validate(tree):
        return []

    errors = [f"line {error.line}: {error.message}" for error in schema.error_log]
    logger.error(
        "Falha na validação XSD do IDS '{}': {}",
        ids_path.name,
        " | ".join(errors),
    )
    raise ValueError(f"Arquivo IDS inválido contra XSD '{xsd_path.name}': " + "; ".join(errors))


def parse_ids(ids_filepath: str) -> list[IDSSpecification]:
    """Parseia um arquivo IDS (XML, padrão buildingSMART IDS 1.0) e retorna lista de specifications.

    Resultado cacheado por (caminho absoluto, mtime, size) para evitar reparse e revalidação XSD.
    """
    ids_path = Path(ids_filepath)
    try:
        stat = ids_path.stat()
        cache_key = (str(ids_path.resolve()), stat.st_mtime_ns, stat.st_size)
    except OSError:
        cache_key = (str(ids_path), 0, 0)
    return list(_parse_ids_cached(cache_key))


@lru_cache(maxsize=32)
def _parse_ids_cached(cache_key: tuple[str, int, int]) -> tuple[IDSSpecification, ...]:
    """Implementação cacheada do parse_ids; chave inclui mtime para invalidar quando o arquivo muda."""
    ids_path = Path(cache_key[0])
    if IDS_XSD_PATH.exists():
        validate_ids_against_xsd(ids_path, IDS_XSD_PATH)
    else:
        logger.warning(
            "XSD IDS não encontrado em '{}'; prosseguindo sem validação XSD.",
            IDS_XSD_PATH,
        )

    tree = etree.parse(str(ids_path))
    root = tree.getroot()

    specifications_el = root.find(f"{_IDS}specifications")
    if specifications_el is None:
        return ()

    return tuple(
        _parse_specification(spec_el)
        for spec_el in specifications_el.findall(f"{_IDS}specification")
    )
