"""Mapeia Psets, propriedades, tipos e unidades por classe IFC e por software de origem.

Responde à pergunta "qual mapeamento de classes/propriedades os softwares entregam?"
e gera a base de observação para sinônimos do catálogo (M1) e para o estudo de
evidência por campo (M3). É um INVENTÁRIO: nada aqui prova equivalência de conceito.

Somente leitura: nenhum IFC é alterado. A saída padrão fica em ``research/``, que
é ignorada pelo git — modelos reais e saídas derivadas não são versionados.

Uso:
    uv run python scripts/mapear_propriedades.py ARQ1.ifc ARQ2.ifc
    uv run python scripts/mapear_propriedades.py *.ifc --classes IfcColumn IfcBeam \
        --termos fck cobrimento
    uv run python scripts/mapear_propriedades.py casa_v1.ifc --out research/M3/mapeamento/casa
    uv run python scripts/mapear_propriedades.py casa_v1.ifc --todas-as-classes

Saídas em --out:
    manifesto.json            arquivo, SHA-256, schema, software de origem, contagens por classe
                              e classes pedidas que não existem no schema do arquivo
    propriedades_longo.csv    uma linha por (arquivo, classe, origem, Pset, propriedade,
                              tipo, unidade)
    matriz_softwares.csv      caminho Pset.Propriedade × arquivo (cobertura em %)
    candidatos_termos.csv     propriedades cujo nome, Pset ou valor lembra os termos pedidos

Origem de cada propriedade: ``ocorrencia`` (IfcRelDefinesByProperties), ``tipo``
(HasPropertySets do tipo) ou ``material`` (IfcMaterialProperties no IFC4,
IfcExtendedMaterialProperties e subtipos tipados no IFC2X3). Origens não são
combinadas como em ``get_psets``: o mesmo caminho em tipo e ocorrência gera duas linhas.

Unidade (``unidade_origem``): ``explicita`` (atributo Unit), ``projeto``
(IfcUnitAssignment para a grandeza), ``ausente`` (grandeza dimensional sem unidade
declarada) ou ``adimensional`` (IfcReal, IfcLabel, IfcBoolean...).

A coluna ``alias_legado_de`` só informa que o nome consta na tabela de aliases de
``src/translator/pset_resolver.py``; o plano (M1 §2.2) não valida esses aliases como
sinônimos — p.ex. ``fck``/``fcd`` não são a mesma grandeza.
"""

# ruff: noqa: E402 -- execução direta exige incluir a raiz antes dos imports locais.

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Iterator
from functools import cache
from pathlib import Path
from typing import Literal

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import ifcopenshell
import ifcopenshell.util.element as uel
import ifcopenshell.util.unit as uunit
from loguru import logger

from src.translator.pset_resolver import PROPERTY_ALIASES, normalize_canonical

DEFAULT_CLASSES = [
    "IfcColumn",
    "IfcBeam",
    "IfcSlab",
    "IfcFooting",
    "IfcWall",
    "IfcMember",
    "IfcPile",
]
DEFAULT_TERMS = [
    "fck",
    "resistencia",
    "concreto",
    "classe",
    "cobrimento",
    "agressividade",
    "caa",
    "strength",
    "cover",
    "exposure",
]
DEFAULT_OUT = Path("research/M3/mapeamento")
MAX_EXAMPLES = 3
MATERIAL_NAME_PSET = "(nome do material)"

Origin = Literal["ocorrencia", "tipo", "material"]
UnitSource = Literal["explicita", "projeto", "ausente", "adimensional", ""]

# Atributos de IfcMaterialProperties (IFC2X3) que não são propriedades do material.
_MATERIAL_PROPS_SKIP = {"Material", "Name", "Description", "ExtendedProperties"}


def normalize_term(text: object) -> str:
    """Normaliza texto para busca de termos: sem acento, minúsculo, separadores viram espaço."""
    ascii_text = unicodedata.normalize("NFD", str(text or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[_\-.]+", " ", ascii_text.lower())).strip()


def sha256_file(path: Path) -> str:
    """SHA-256 do arquivo, lido em blocos."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def originating_software(ifc: ifcopenshell.file) -> str:
    """Software de origem declarado no cabeçalho e em IfcApplication, sem repetições."""
    parts: list[str] = []
    try:
        file_name = ifc.header.file_name
        parts += [file_name.originating_system, file_name.preprocessor_version]
    except (AttributeError, RuntimeError):
        logger.debug("cabeçalho FILE_NAME ilegível")
    for app in ifc.by_type("IfcApplication"):
        parts.append(f"{app.ApplicationFullName} {app.Version}")
    seen: set[str] = set()
    unique: list[str] = []
    for part in parts:
        text = str(part or "").strip()
        if text and text not in seen:
            seen.add(text)
            unique.append(text)
    return " | ".join(unique) or "desconhecido"


@cache
def _dimensional_unit_types(schema: str) -> frozenset[str]:
    """IfcUnitEnum ∪ IfcDerivedUnitEnum do schema (grandezas que admitem unidade de projeto)."""
    wrapper = ifcopenshell.ifcopenshell_wrapper.schema_by_name(schema)
    items: set[str] = set()
    for enum in ("IfcUnitEnum", "IfcDerivedUnitEnum"):
        items.update(wrapper.declaration_by_name(enum).enumeration_items())
    return frozenset(items - {"USERDEFINED"})


def legacy_alias_of(name: str) -> str:
    """Nome canônico da tabela legada de aliases, se ``name`` for só alias nela.

    Nomes que já são chave canônica da tabela (p.ex. ``LoadBearing``, oficial em
    Pset_SlabCommon) não são anotados, embora a tabela também os liste como alias.
    """
    if name in PROPERTY_ALIASES:
        return ""
    canonical = normalize_canonical(name)
    return canonical if canonical != name else ""


def _unit_name(unit: ifcopenshell.entity_instance) -> str:
    """Nome legível da unidade; derivadas viram produto dos elementos (WATT·METRE^-2...)."""
    if unit.is_a("IfcDerivedUnit"):
        parts = []
        for element in unit.Elements or []:
            exponent = "" if element.Exponent == 1 else f"^{element.Exponent}"
            parts.append(f"{_unit_name(element.Unit)}{exponent}")
        return "·".join(parts) or str(unit.UnitType)
    try:
        return uunit.get_full_unit_name(unit)
    except (AttributeError, KeyError, TypeError):
        return getattr(unit, "Name", None) or unit.is_a()


def _unit_type_for(value_type: str) -> str | None:
    """Tipo de unidade (IfcUnitEnum/IfcDerivedUnitEnum) da medida ou quantidade, se houver."""
    if value_type.startswith("IfcQuantity"):
        return {
            "IfcQuantityLength": "LENGTHUNIT",
            "IfcQuantityArea": "AREAUNIT",
            "IfcQuantityVolume": "VOLUMEUNIT",
            "IfcQuantityWeight": "MASSUNIT",
            "IfcQuantityTime": "TIMEUNIT",
        }.get(value_type)
    try:
        return uunit.get_measure_unit_type(value_type)
    except (KeyError, TypeError, ValueError):
        return None


def resolve_unit(
    ifc: ifcopenshell.file, entity: ifcopenshell.entity_instance | None, value_type: str
) -> tuple[str, UnitSource]:
    """Unidade e sua origem: Unit explícito, unidade de projeto, ausente ou adimensional."""
    explicit = getattr(entity, "Unit", None) if entity is not None else None
    if explicit is not None:
        return _unit_name(explicit), "explicita"
    if not value_type:
        return "", ""
    unit_type = _unit_type_for(value_type)
    if unit_type not in _dimensional_unit_types(ifc.schema):
        return "", "adimensional"
    project_unit = uunit.get_project_unit(ifc, unit_type)
    if project_unit is None:
        return "", "ausente"
    return _unit_name(project_unit), "projeto"


PropertyItem = tuple[str, str, object, ifcopenshell.entity_instance | None]


def _single_value(prop: ifcopenshell.entity_instance) -> PropertyItem:
    """(nome, tipo, valor, entidade) de uma IfcProperty."""
    if prop.is_a("IfcPropertySingleValue"):
        value = prop.NominalValue
        return (
            prop.Name,
            (value.is_a() if value is not None else ""),
            (value.wrappedValue if value is not None else None),
            prop,
        )
    if prop.is_a("IfcPropertyEnumeratedValue"):
        values = list(prop.EnumerationValues or [])
        value_type = values[0].is_a() if values else ""
        return prop.Name, value_type, "; ".join(str(v.wrappedValue) for v in values), prop
    return prop.Name, prop.is_a(), None, prop


def _typed_attributes(definition: ifcopenshell.entity_instance) -> Iterator[PropertyItem]:
    """Atributos preenchidos de um IfcMaterialProperties tipado do IFC2X3 (p.ex. concreto)."""
    entity = definition.wrapped_data.declaration().as_entity()
    for index, attribute in enumerate(entity.all_attributes()):
        name = attribute.name()
        value = definition[index]
        if name in _MATERIAL_PROPS_SKIP or value is None:
            continue
        declared = attribute.type_of_attribute()
        named = declared.declared_type() if hasattr(declared, "declared_type") else None
        value_type = named.name() if named is not None else ""
        yield name, value_type, value, None


def iter_properties(definition: ifcopenshell.entity_instance) -> Iterator[PropertyItem]:
    """Gera (nome, tipo_valor, valor, entidade) de Pset, Qto ou propriedades de material."""
    if definition.is_a("IfcPropertySet"):
        for prop in definition.HasProperties or []:
            yield _single_value(prop)
    elif definition.is_a("IfcElementQuantity"):
        for quantity in definition.Quantities or []:
            value = quantity[3] if len(quantity) > 3 else None
            yield quantity.Name, quantity.is_a(), value, quantity
    elif definition.is_a("IfcExtendedMaterialProperties"):  # IFC2X3
        for prop in definition.ExtendedProperties or []:
            yield _single_value(prop)
    elif definition.is_a("IfcMaterialProperties"):
        if hasattr(definition, "Properties"):  # IFC4
            for prop in definition.Properties or []:
                yield _single_value(prop)
        else:  # subtipos tipados do IFC2X3
            yield from _typed_attributes(definition)


def material_properties_index(
    ifc: ifcopenshell.file,
) -> dict[int, list[ifcopenshell.entity_instance]]:
    """IfcMaterial.id() → IfcMaterialProperties (no IFC2X3 não há inverso HasProperties)."""
    index: dict[int, list[ifcopenshell.entity_instance]] = defaultdict(list)
    for props in ifc.by_type("IfcMaterialProperties"):
        material = getattr(props, "Material", None)
        if material is not None:
            index[material.id()].append(props)
    return index


def property_set_name(definition: ifcopenshell.entity_instance) -> str:
    """Nome do conjunto; IfcMaterialProperties tipado do IFC2X3 não tem Name e usa a classe."""
    return getattr(definition, "Name", None) or definition.is_a()


def element_materials(element: ifcopenshell.entity_instance) -> list[ifcopenshell.entity_instance]:
    """IfcMaterial do elemento (camadas, perfis, constituintes ou lista), sem repetição."""
    try:
        materials = uel.get_materials(element)
    except (AttributeError, RuntimeError, TypeError):
        logger.debug("materiais ilegíveis em #{}", element.id())
        return []
    unique: dict[int, ifcopenshell.entity_instance] = {}
    for material in materials or []:
        unique.setdefault(material.id(), material)
    return list(unique.values())


def definitions_of(
    element: ifcopenshell.entity_instance,
    material_index: dict[int, list[ifcopenshell.entity_instance]],
) -> Iterator[tuple[Origin, ifcopenshell.entity_instance]]:
    """Gera (origem, definição) para ocorrência, tipo e materiais do elemento."""
    for rel in getattr(element, "IsDefinedBy", None) or []:
        if rel.is_a("IfcRelDefinesByProperties"):
            relating = rel.RelatingPropertyDefinition
            # IFC4 admite IfcPropertySetDefinitionSet (agregado).
            for definition in relating if isinstance(relating, tuple) else [relating]:
                yield "ocorrencia", definition
    element_type = uel.get_type(element)
    if element_type is not None:
        for definition in getattr(element_type, "HasPropertySets", None) or []:
            yield "tipo", definition
    for material in element_materials(element):
        for definition in material_index.get(material.id(), []):
            yield "material", definition


def _is_mappable(definition: ifcopenshell.entity_instance) -> bool:
    """Pset, Qto ou propriedades de material."""
    return any(
        definition.is_a(c)
        for c in ("IfcPropertySet", "IfcElementQuantity", "IfcMaterialProperties")
    )


def map_file(
    path: Path, classes: Iterable[str] | None
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Inventaria um IFC: manifesto do arquivo e linhas agregadas por caminho de propriedade.

    Com ``classes`` dadas, cada classe inclui seus subtipos (IfcWall conta
    IfcWallStandardCase). Com ``None``, inventaria cada classe concreta de
    IfcElement presente no arquivo, sem subtipos, para não contar duas vezes.
    """
    ifc = ifcopenshell.open(str(path))
    include_subtypes = classes is not None
    if classes is None:
        classes = sorted({element.is_a() for element in ifc.by_type("IfcElement")})
    elements_per_class: dict[str, int] = {}
    missing_classes: list[str] = []
    info: dict[str, object] = {
        "arquivo": path.name,
        "sha256": sha256_file(path),
        "schema": ifc.schema,
        "software": originating_software(ifc),
        "elementos_por_classe": elements_per_class,
        "classes_ausentes_no_schema": missing_classes,
    }
    material_index = material_properties_index(ifc)
    aggregates: dict[tuple[str, ...], dict[str, object]] = {}

    def register(key: tuple[str, ...], value: object, seen: set[tuple[str, ...]]) -> None:
        entry = aggregates.setdefault(key, {"elementos": 0, "exemplos": []})
        if key not in seen:
            entry["elementos"] = int(entry["elementos"]) + 1
            seen.add(key)
        examples = entry["exemplos"]
        assert isinstance(examples, list)
        if value is not None and str(value) not in examples and len(examples) < MAX_EXAMPLES:
            examples.append(str(value))

    for ifc_class in classes:
        try:
            elements = ifc.by_type(ifc_class, include_subtypes=include_subtypes)
        except RuntimeError:
            missing_classes.append(ifc_class)
            continue
        elements_per_class[ifc_class] = len(elements)
        for element in elements:
            seen: set[tuple[str, ...]] = set()
            for origin, definition in definitions_of(element, material_index):
                if not _is_mappable(definition):
                    continue
                pset = property_set_name(definition)
                for name, value_type, value, entity in iter_properties(definition):
                    unit, unit_source = resolve_unit(ifc, entity, value_type)
                    key = (ifc_class, origin, pset, name, value_type, unit, unit_source)
                    register(key, value, seen)
            for material in element_materials(element):
                if material.Name:
                    key = (
                        ifc_class,
                        "material",
                        MATERIAL_NAME_PSET,
                        "Name",
                        "IfcLabel",
                        "",
                        "adimensional",
                    )
                    register(key, material.Name, seen)

    rows: list[dict[str, object]] = []
    for (ifc_class, origin, pset, name, value_type, unit, unit_source), entry in sorted(
        aggregates.items()
    ):
        total = elements_per_class.get(ifc_class, 0)
        count = int(entry["elementos"])
        examples = entry["exemplos"]
        assert isinstance(examples, list)
        rows.append(
            {
                "arquivo": info["arquivo"],
                "software": info["software"],
                "schema": info["schema"],
                "classe": ifc_class,
                "origem": origin,
                "pset": pset,
                "propriedade": name,
                "tipo_valor": value_type,
                "unidade": unit,
                "unidade_origem": unit_source,
                "elementos_com": count,
                "elementos_classe": total,
                "cobertura_pct": round(100 * count / total, 1) if total else 0.0,
                "exemplos": " | ".join(examples),
                "alias_legado_de": legacy_alias_of(name),
            }
        )
    return info, rows


def term_candidates(rows: list[dict[str, object]], terms: Iterable[str]) -> list[dict[str, object]]:
    """Linhas cujo nome, Pset ou exemplos contêm algum termo (busca por substring normalizada)."""
    normalized = [normalize_term(t) for t in terms]
    found: list[dict[str, object]] = []
    for row in rows:
        haystacks = [normalize_term(row[k]) for k in ("propriedade", "pset", "exemplos")]
        for term in normalized:
            if term and any(term in h for h in haystacks):
                found.append({**row, "termo": term})
    return found


def write_outputs(
    out: Path,
    manifest: list[dict[str, object]],
    rows: list[dict[str, object]],
    terms: Iterable[str],
) -> int:
    """Grava as quatro saídas e devolve o número de candidatos a termos."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifesto.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    fields = list(rows[0].keys()) if rows else ["arquivo"]
    with (out / "propriedades_longo.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    files = [str(m["arquivo"]) for m in manifest]
    matrix: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for row in rows:
        key = (str(row["classe"]), f"{row['pset']}.{row['propriedade']}")
        current = matrix[key].get(str(row["arquivo"]), 0.0)
        # Mesmo caminho com tipos/unidades/origens diferentes: vale a maior cobertura.
        matrix[key][str(row["arquivo"])] = max(current, float(row["cobertura_pct"]))  # type: ignore[arg-type]
    with (out / "matriz_softwares.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer_m = csv.writer(handle)
        writer_m.writerow(["classe", "caminho", *files])
        for (ifc_class, prop_path), coverage in sorted(matrix.items()):
            writer_m.writerow([ifc_class, prop_path, *[coverage.get(f, "") for f in files]])

    candidates = term_candidates(rows, terms)
    with (out / "candidatos_termos.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer_c = csv.DictWriter(handle, fieldnames=[*fields, "termo"])
        writer_c.writeheader()
        writer_c.writerows(candidates)
    return len(candidates)


def main(argv: list[str] | None = None) -> None:
    """Inventaria os IFCs pedidos e grava as saídas em --out."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("ifcs", nargs="+", type=Path)
    classes = parser.add_mutually_exclusive_group()
    classes.add_argument("--classes", nargs="+", default=DEFAULT_CLASSES)
    classes.add_argument(
        "--todas-as-classes",
        action="store_true",
        help="cada classe concreta de IfcElement presente no arquivo, sem subtipos",
    )
    parser.add_argument("--termos", nargs="+", default=DEFAULT_TERMS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    manifest: list[dict[str, object]] = []
    all_rows: list[dict[str, object]] = []
    for path in args.ifcs:
        info, rows = map_file(path, None if args.todas_as_classes else args.classes)
        manifest.append(info)
        all_rows += rows
        counts = info["elementos_por_classe"]
        assert isinstance(counts, dict)
        logger.info(
            "{}: {} · {} · {} elementos · {} caminhos · ausentes no schema: {}",
            path.name,
            info["software"],
            info["schema"],
            sum(counts.values()),
            len(rows),
            info["classes_ausentes_no_schema"] or "nenhuma",
        )
    candidates = write_outputs(args.out, manifest, all_rows, args.termos)
    logger.info(
        "Saídas em {} · {} caminhos · {} candidatos a termos", args.out, len(all_rows), candidates
    )


if __name__ == "__main__":
    main()
