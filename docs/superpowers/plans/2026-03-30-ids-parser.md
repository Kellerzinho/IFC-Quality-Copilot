# IDS Parser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar `parse_ids()` em `src/translator/ids_parser.py` que lê arquivos IDS XML (buildingSMART IDS 1.0) e retorna `list[IDSSpecification]`, mais criar `data/ids_templates/residencial_nbr15575.ids` com 5 specifications e os 4 testes pedidos.

**Architecture:** O parser usa `lxml.etree` com namespace explícito `http://standards.buildingsmart.org/IDS`. Para cada `<specification>` extrai entity, applicability filters (property facets) e requirements. Casos especiais (atributo `LongName`, relação IfcRelFillsElement) são representados com convenções de campo documentadas em comentários.

**Tech Stack:** Python 3.11, lxml, Pydantic v2 (IDSSpecification de `src/models.py`), pytest

---

## File Structure

| Arquivo | Ação |
|---|---|
| `data/ids_templates/residencial_nbr15575.ids` | Criar — IDS XML com 5 specs |
| `src/translator/ids_parser.py` | Criar — função `parse_ids()` |
| `tests/test_translator.py` | Criar — 4 testes pedidos |

### IDSSpecification (já existe em `src/models.py:274`)

```python
class IDSSpecification(BaseModel):
    name: str
    description: str | None = None
    applicability_entity: str          # ex: "IFCWALL"
    applicability_filters: list[dict[str, str]]  # [{pset, prop, value}]
    requirements: list[dict[str, str]]           # [{pset, prop, constraint}]
```

### Convenções para casos especiais

- **Atributo IFC** (ex: `LongName`): `pset=""`, `prop="LongName"`, `constraint="not_empty"`
- **Relação IFC** (ex: `IfcRelFillsElement`): `pset="IFC_RELATION"`, `prop="IfcRelFillsElement"`, `constraint="exists"`

Essas convenções são usadas no XML com elementos `<attribute>` e `<relation>` (não-padrão, interpretados pelo parser interno).

---

## Task 1: Criar o arquivo IDS XML

**Files:**
- Create: `data/ids_templates/residencial_nbr15575.ids`

- [ ] **Step 1: Criar o arquivo IDS XML com 5 specifications**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ids xmlns="http://standards.buildingsmart.org/IDS"
     xmlns:xs="http://www.w3.org/2001/XMLSchema"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     xsi:schemaLocation="http://standards.buildingsmart.org/IDS
                         http://standards.buildingsmart.org/IDS/1.0/ids.xsd">
  <info>
    <title>Requisitos NBR 15575 — Edificações Residenciais</title>
    <description>5 verificações baseadas na NBR 15575 para modelos IFC residenciais</description>
    <author>IFC Quality Copilot</author>
    <date>2026-03-30</date>
    <version>1.0</version>
  </info>
  <specifications>

    <specification name="Paredes externas devem ter transmitância térmica"
                   description="NBR 15575-4: paredes externas exigem ThermalTransmittance preenchido">
      <applicability>
        <entity>
          <name>
            <xs:restriction base="xs:string">
              <xs:enumeration value="IFCWALL"/>
            </xs:restriction>
          </name>
        </entity>
        <property datatype="IfcBoolean">
          <propertySet>
            <xs:restriction base="xs:string">
              <xs:enumeration value="Pset_WallCommon"/>
            </xs:restriction>
          </propertySet>
          <baseName>
            <xs:restriction base="xs:string">
              <xs:enumeration value="IsExternal"/>
            </xs:restriction>
          </baseName>
          <value>
            <xs:restriction base="xs:string">
              <xs:enumeration value="TRUE"/>
            </xs:restriction>
          </value>
        </property>
      </applicability>
      <requirements>
        <property datatype="IfcThermalTransmittanceMeasure">
          <propertySet>
            <xs:restriction base="xs:string">
              <xs:enumeration value="Pset_WallCommon"/>
            </xs:restriction>
          </propertySet>
          <baseName>
            <xs:restriction base="xs:string">
              <xs:enumeration value="ThermalTransmittance"/>
            </xs:restriction>
          </baseName>
        </property>
      </requirements>
    </specification>

    <specification name="Paredes externas devem ter resistência ao fogo"
                   description="NBR 15575-1: paredes externas exigem FireRating preenchido">
      <applicability>
        <entity>
          <name>
            <xs:restriction base="xs:string">
              <xs:enumeration value="IFCWALL"/>
            </xs:restriction>
          </name>
        </entity>
        <property datatype="IfcBoolean">
          <propertySet>
            <xs:restriction base="xs:string">
              <xs:enumeration value="Pset_WallCommon"/>
            </xs:restriction>
          </propertySet>
          <baseName>
            <xs:restriction base="xs:string">
              <xs:enumeration value="IsExternal"/>
            </xs:restriction>
          </baseName>
          <value>
            <xs:restriction base="xs:string">
              <xs:enumeration value="TRUE"/>
            </xs:restriction>
          </value>
        </property>
      </applicability>
      <requirements>
        <property datatype="IfcLabel">
          <propertySet>
            <xs:restriction base="xs:string">
              <xs:enumeration value="Pset_WallCommon"/>
            </xs:restriction>
          </propertySet>
          <baseName>
            <xs:restriction base="xs:string">
              <xs:enumeration value="FireRating"/>
            </xs:restriction>
          </baseName>
        </property>
      </requirements>
    </specification>

    <specification name="Espaços devem ter nome funcional"
                   description="Cada IfcSpace deve ter LongName preenchido com classificação funcional">
      <applicability>
        <entity>
          <name>
            <xs:restriction base="xs:string">
              <xs:enumeration value="IFCSPACE"/>
            </xs:restriction>
          </name>
        </entity>
      </applicability>
      <requirements>
        <attribute>
          <name>
            <xs:restriction base="xs:string">
              <xs:enumeration value="LongName"/>
            </xs:restriction>
          </name>
          <value>
            <xs:restriction base="xs:string">
              <xs:minLength value="1"/>
            </xs:restriction>
          </value>
        </attribute>
      </requirements>
    </specification>

    <specification name="Portas devem estar vinculadas a paredes"
                   description="Cada IfcDoor deve possuir IfcRelFillsElement ligando-a a uma abertura em parede">
      <applicability>
        <entity>
          <name>
            <xs:restriction base="xs:string">
              <xs:enumeration value="IFCDOOR"/>
            </xs:restriction>
          </name>
        </entity>
      </applicability>
      <requirements>
        <relation>
          <name>
            <xs:restriction base="xs:string">
              <xs:enumeration value="IfcRelFillsElement"/>
            </xs:restriction>
          </name>
        </relation>
      </requirements>
    </specification>

    <specification name="Lajes devem indicar carga"
                   description="Cada IfcSlab deve ter Pset_SlabCommon.LoadBearing preenchido">
      <applicability>
        <entity>
          <name>
            <xs:restriction base="xs:string">
              <xs:enumeration value="IFCSLAB"/>
            </xs:restriction>
          </name>
        </entity>
      </applicability>
      <requirements>
        <property datatype="IfcBoolean">
          <propertySet>
            <xs:restriction base="xs:string">
              <xs:enumeration value="Pset_SlabCommon"/>
            </xs:restriction>
          </propertySet>
          <baseName>
            <xs:restriction base="xs:string">
              <xs:enumeration value="LoadBearing"/>
            </xs:restriction>
          </baseName>
        </property>
      </requirements>
    </specification>

  </specifications>
</ids>
```

- [ ] **Step 2: Verificar que o arquivo é XML válido**

```bash
python -c "from lxml import etree; etree.parse('data/ids_templates/residencial_nbr15575.ids'); print('XML OK')"
```
Esperado: `XML OK`

---

## Task 2: Implementar ids_parser.py com TDD

**Files:**
- Create: `src/translator/ids_parser.py`
- Create: `tests/test_translator.py`

### Passo a passo TDD

- [ ] **Step 1: Escrever os 4 testes antes do código**

Criar `tests/test_translator.py`:

```python
"""Testes para src/translator/ids_parser.py."""

import pytest

from src.models import IDSSpecification
from src.translator.ids_parser import parse_ids

IDS_PATH = "data/ids_templates/residencial_nbr15575.ids"


def test_parse_ids_reads_file():
    """parse_ids deve retornar uma lista (não levantar exceção)."""
    result = parse_ids(IDS_PATH)
    assert isinstance(result, list)


def test_parse_ids_extracts_5_specs():
    """parse_ids deve retornar exatamente 5 IDSSpecification do arquivo NBR 15575."""
    result = parse_ids(IDS_PATH)
    assert len(result) == 5
    assert all(isinstance(s, IDSSpecification) for s in result)


def test_parse_ids_wall_thermal_spec():
    """Primeira spec deve cobrir paredes externas com ThermalTransmittance."""
    specs = parse_ids(IDS_PATH)
    spec = specs[0]

    assert spec.applicability_entity == "IFCWALL"
    # filtro de aplicabilidade: IsExternal = TRUE
    assert len(spec.applicability_filters) == 1
    filt = spec.applicability_filters[0]
    assert filt["pset"] == "Pset_WallCommon"
    assert filt["prop"] == "IsExternal"
    assert filt["value"] == "TRUE"
    # requisito: ThermalTransmittance
    assert len(spec.requirements) == 1
    req = spec.requirements[0]
    assert req["pset"] == "Pset_WallCommon"
    assert req["prop"] == "ThermalTransmittance"


def test_parse_ids_space_name_spec():
    """Terceira spec deve cobrir IfcSpace com requisito de LongName não vazio."""
    specs = parse_ids(IDS_PATH)
    spec = specs[2]

    assert spec.applicability_entity == "IFCSPACE"
    assert spec.applicability_filters == []
    assert len(spec.requirements) == 1
    req = spec.requirements[0]
    assert req["prop"] == "LongName"
    assert req["pset"] == ""
    assert req["constraint"] == "not_empty"
```

- [ ] **Step 2: Confirmar que os testes falham (módulo inexistente)**

```bash
cd "C:\Users\Keller_\Desktop\Projetos FC\Pesquisa\ifc-quality-copilot" && python -m pytest tests/test_translator.py -v 2>&1 | head -20
```
Esperado: `ModuleNotFoundError` ou `ImportError` para `ids_parser`

- [ ] **Step 3: Implementar `src/translator/ids_parser.py`**

```python
"""Parser de arquivos IDS (Information Delivery Specification) no formato buildingSMART IDS 1.0."""

from lxml import etree

from src.models import IDSSpecification

IDS_NS = "http://standards.buildingsmart.org/IDS"
XS_NS = "http://www.w3.org/2001/XMLSchema"

_IDS = f"{{{IDS_NS}}}"
_XS = f"{{{XS_NS}}}"


def _text(element: etree._Element | None) -> str:
    """Retorna o texto de um elemento, ou string vazia se None."""
    if element is None:
        return ""
    return (element.text or "").strip()


def _simplevalue(parent: etree._Element | None) -> str:
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


def _parse_property_filter(prop_el: etree._Element) -> dict[str, str]:
    """Extrai {pset, prop, value} de um elemento <property> em <applicability>."""
    pset = _simplevalue(prop_el.find(f"{_IDS}propertySet"))
    prop = _simplevalue(prop_el.find(f"{_IDS}baseName"))
    value_el = prop_el.find(f"{_IDS}value")
    value = _simplevalue(value_el) if value_el is not None else ""
    return {"pset": pset, "prop": prop, "value": value}


def _parse_property_requirement(prop_el: etree._Element) -> dict[str, str]:
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


def _parse_attribute_requirement(attr_el: etree._Element) -> dict[str, str]:
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


def _parse_relation_requirement(rel_el: etree._Element) -> dict[str, str]:
    """Extrai {pset, prop, constraint} de um elemento <relation> em <requirements>.

    Convenção interna: pset="IFC_RELATION" indica relação IFC (ex: IfcRelFillsElement).
    """
    prop = _simplevalue(rel_el.find(f"{_IDS}name"))
    return {"pset": "IFC_RELATION", "prop": prop, "constraint": "exists"}


def _parse_specification(spec_el: etree._Element) -> IDSSpecification:
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
    tree = etree.parse(ids_filepath)
    root = tree.getroot()

    specifications_el = root.find(f"{_IDS}specifications")
    if specifications_el is None:
        return []

    return [
        _parse_specification(spec_el)
        for spec_el in specifications_el.findall(f"{_IDS}specification")
    ]
```

- [ ] **Step 4: Rodar os 4 testes**

```bash
cd "C:\Users\Keller_\Desktop\Projetos FC\Pesquisa\ifc-quality-copilot" && python -m pytest tests/test_translator.py -v
```
Esperado:
```
PASSED tests/test_translator.py::test_parse_ids_reads_file
PASSED tests/test_translator.py::test_parse_ids_extracts_5_specs
PASSED tests/test_translator.py::test_parse_ids_wall_thermal_spec
PASSED tests/test_translator.py::test_parse_ids_space_name_spec
```

- [ ] **Step 5: Commit**

```bash
git add data/ids_templates/residencial_nbr15575.ids \
        src/translator/ids_parser.py \
        tests/test_translator.py
git commit -m "feat(translator): implementa parse_ids e template IDS NBR 15575"
```

---

## Self-Review

**Cobertura da spec:**
- ✅ `parse_ids(ids_filepath)` com namespace correto
- ✅ `lxml.etree` para parse XML
- ✅ `<entity><name>` → `applicability_entity`
- ✅ `<property>` em `<applicability>` → `applicability_filters` com `{pset, prop, value}`
- ✅ `<property>` em `<requirements>` → `requirements` com `{pset, prop, constraint}` (inclui `<restriction>`)
- ✅ Retorna `list[IDSSpecification]`
- ✅ 5 specifications no IDS XML (paredes externas térmicas, paredes externas fogo, espaços LongName, portas relação, lajes carga)
- ✅ `test_parse_ids_reads_file`
- ✅ `test_parse_ids_extracts_5_specs`
- ✅ `test_parse_ids_wall_thermal_spec`
- ✅ `test_parse_ids_space_name_spec`

**Tipos consistentes:** `IDSSpecification.applicability_filters` e `.requirements` são `list[dict[str, str]]` — todos os parsers retornam `dict[str, str]`.

**Sem placeholders:** Código completo em cada step.
