# IDS Parser Facets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expandir `parse_ids()` para suportar facets adicionais do IDS 1.0 (`<material>`, `<classification>`, `<partOf>`), adicionar `facet_type` e `constraint_type` em todos os dicts de requirement, e cobrir com 5 novos testes.

**Architecture:** Adicionar `_extract_constraint()` como helper centralizado para extração de `xs:restriction`; adicionar três novos parsers de facet; atualizar parsers existentes com os novos campos; wirear tudo em `_parse_specification()`.

**Tech Stack:** Python 3.11+, lxml, Pydantic v2, pytest

---

## File Map

| Arquivo | Tipo de mudança |
|---|---|
| `src/translator/ids_parser.py` | Modify — novo helper, 3 novos parsers, atualizar 3 existentes, wirear |
| `tests/test_translator.py` | Modify — 5+1 novos testes, atualizar `_make_spec()` |

`src/models.py` não é alterado (docstring de `IDSSpecification` permanece inalterada — tipo `list[dict[str, str]]` já cobre os novos campos).

---

## Task 1: `_extract_constraint` + atualizar `_parse_property_requirement`

**Spec:** Adiciona helper centralizado de extração de constraints e atualiza `_parse_property_requirement` para usá-lo, adicionando `facet_type` e `constraint_type` ao dict retornado.

**Files:**
- Modify: `src/translator/ids_parser.py` — novo helper `_extract_constraint`, reescrita de `_parse_property_requirement`
- Modify: `tests/test_translator.py` — `test_parse_ids_with_restriction`, `test_parse_energy_ids_reads_thermal_specs`

---

- [ ] **Step 1.1: Adicionar helper `_make_ids_xml` nos testes**

No final da seção de helpers de `tests/test_translator.py` (antes dos testes de `apply_rules`), adicionar:

```python
# ---------------------------------------------------------------------------
# Helpers para testes de parse_ids com XML inline
# ---------------------------------------------------------------------------

IDS_NS_DECL = (
    'xmlns:ids="http://standards.buildingsmart.org/IDS" '
    'xmlns:xs="http://www.w3.org/2001/XMLSchema"'
)


def _make_ids_xml(requirements_xml: str, entity: str = "IFCWALL") -> str:
    """Monta XML IDS mínimo com uma specification e os requirements fornecidos."""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<ids:ids {IDS_NS_DECL}>
  <ids:specifications>
    <ids:specification name="Test">
      <ids:applicability>
        <ids:entity>
          <ids:name><ids:simpleValue>{entity}</ids:simpleValue></ids:name>
        </ids:entity>
      </ids:applicability>
      <ids:requirements>
        {requirements_xml}
      </ids:requirements>
    </ids:specification>
  </ids:specifications>
</ids:ids>"""
```

- [ ] **Step 1.2: Escrever testes que vão falhar**

Logo após `_make_ids_xml`, adicionar:

```python
# ---------------------------------------------------------------------------
# Testes de facets adicionais
# ---------------------------------------------------------------------------

def test_parse_ids_with_restriction(tmp_path: Path) -> None:
    """<xs:restriction base="xs:double"><xs:minInclusive> deve resultar em
    constraint='minInclusive' e constraint_type='xs:double'."""
    xml = _make_ids_xml("""
        <ids:property>
          <ids:propertySet><ids:simpleValue>Pset_WallCommon</ids:simpleValue></ids:propertySet>
          <ids:baseName><ids:simpleValue>ThermalTransmittance</ids:simpleValue></ids:baseName>
          <ids:value>
            <xs:restriction base="xs:double">
              <xs:minInclusive value="0"/>
            </xs:restriction>
          </ids:value>
        </ids:property>
    """)
    ids_file = tmp_path / "test.ids"
    ids_file.write_text(xml, encoding="utf-8")

    specs = parse_ids(str(ids_file))
    req = specs[0].requirements[0]

    assert req["constraint"] == "minInclusive"
    assert req["constraint_type"] == "xs:double"


def test_parse_energy_ids_reads_thermal_specs(tmp_path: Path) -> None:
    """Requisito de ThermalTransmittance com restriction double deve ter
    facet_type='property' e constraint_type='xs:double'."""
    xml = _make_ids_xml("""
        <ids:property>
          <ids:propertySet><ids:simpleValue>Pset_WallCommon</ids:simpleValue></ids:propertySet>
          <ids:baseName><ids:simpleValue>ThermalTransmittance</ids:simpleValue></ids:baseName>
          <ids:value>
            <xs:restriction base="xs:double">
              <xs:minInclusive value="0"/>
            </xs:restriction>
          </ids:value>
        </ids:property>
    """)
    ids_file = tmp_path / "test.ids"
    ids_file.write_text(xml, encoding="utf-8")

    specs = parse_ids(str(ids_file))
    req = specs[0].requirements[0]

    assert req["facet_type"] == "property"
    assert req["prop"] == "ThermalTransmittance"
    assert req["pset"] == "Pset_WallCommon"
    assert req["constraint_type"] == "xs:double"
```

- [ ] **Step 1.3: Rodar e confirmar falha**

```bash
cd "C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot"
pytest tests/test_translator.py::test_parse_ids_with_restriction tests/test_translator.py::test_parse_energy_ids_reads_thermal_specs -v
```

Esperado: `FAILED` com `KeyError: 'facet_type'` ou `KeyError: 'constraint_type'`.

- [ ] **Step 1.4: Implementar `_extract_constraint` em `ids_parser.py`**

Inserir após a função `_parse_property_filter` (linha ~38), antes de `_parse_property_requirement`:

```python
def _extract_constraint(value_el: "etree._Element | None") -> tuple[str, str]:
    """Extrai (constraint, constraint_type) de um elemento <value> ou None.

    Retorna:
        ("exists", "")                  → sem <value>
        ("equals:X", "xs:string")       → <simpleValue>X</simpleValue>
        ("equals:X", "xs:string")       → <xs:enumeration value="X"/>
        ("not_empty", "xs:string")      → <xs:minLength value="N"/> com N > 0
        ("minInclusive", "xs:double")   → <xs:minInclusive/> com base xs:double
        (tag_local, base)               → outros restriction types
    """
    if value_el is None:
        return "exists", ""

    sv = value_el.find(f"{_IDS}simpleValue")
    if sv is not None:
        return f"equals:{_text(sv)}", "xs:string"

    restriction = value_el.find(f"{_XS}restriction")
    if restriction is None:
        return "exists", ""

    base = restriction.get("base", "")
    # Normaliza base: remove prefixo de namespace se vier como "{uri}localname"
    if "}" in base:
        base = base.split("}")[-1]
    # Mantém prefixo "xs:" se presente no atributo (ex: "xs:double")
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
```

- [ ] **Step 1.5: Reescrever `_parse_property_requirement` para usar `_extract_constraint`**

Substituir a função `_parse_property_requirement` existente por:

```python
def _parse_property_requirement(prop_el: "etree._Element") -> dict[str, str]:
    """Extrai requirement de <property> em <requirements>.

    facet_type é 'quantity' se o pset começa com 'Qto_', senão 'property'.
    """
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
```

- [ ] **Step 1.6: Rodar e confirmar que os 2 novos testes passam + nenhum existente quebrou**

```bash
pytest tests/test_translator.py -v
```

Esperado: `test_parse_ids_with_restriction` PASSED, `test_parse_energy_ids_reads_thermal_specs` PASSED. Todos os demais testes existentes PASSED.

- [ ] **Step 1.7: Commit**

```bash
git add src/translator/ids_parser.py tests/test_translator.py
git commit -m "feat(ids_parser): adiciona _extract_constraint e facet_type em _parse_property_requirement"
```

---

## Task 2: Atualizar parsers existentes + `test_parse_budget_ids_reads_quantity_facets` + `_make_spec()`

**Spec:** Adiciona `facet_type`/`constraint_type` a `_parse_attribute_requirement` e `_parse_relation_requirement`. Adiciona teste de Qto_. Atualiza `_make_spec()` para incluir os novos campos por padrão.

**Files:**
- Modify: `src/translator/ids_parser.py` — atualizar `_parse_attribute_requirement`, `_parse_relation_requirement`
- Modify: `tests/test_translator.py` — novo teste, atualizar `_make_spec()`

---

- [ ] **Step 2.1: Escrever teste que vai falhar**

No bloco de testes de facets adicionais, adicionar:

```python
def test_parse_budget_ids_reads_quantity_facets(tmp_path: Path) -> None:
    """<property> com pset Qto_ deve resultar em facet_type='quantity'."""
    xml = _make_ids_xml("""
        <ids:property>
          <ids:propertySet><ids:simpleValue>Qto_WallBaseQuantities</ids:simpleValue></ids:propertySet>
          <ids:baseName><ids:simpleValue>NetSideArea</ids:simpleValue></ids:baseName>
        </ids:property>
    """)
    ids_file = tmp_path / "test.ids"
    ids_file.write_text(xml, encoding="utf-8")

    specs = parse_ids(str(ids_file))
    req = specs[0].requirements[0]

    assert req["facet_type"] == "quantity"
    assert req["pset"] == "Qto_WallBaseQuantities"
    assert req["prop"] == "NetSideArea"
    assert req["constraint"] == "exists"
    assert req["constraint_type"] == ""
```

- [ ] **Step 2.2: Rodar e confirmar falha**

```bash
pytest tests/test_translator.py::test_parse_budget_ids_reads_quantity_facets -v
```

Esperado: `FAILED` — `facet_type` já está correto (implementado no Task 1), mas `constraint` e `constraint_type` podem falhar se o parser retornar o formato antigo. Se passar, prosseguir.

- [ ] **Step 2.3: Atualizar `_parse_attribute_requirement`**

Substituir a função existente por:

```python
def _parse_attribute_requirement(attr_el: "etree._Element") -> dict[str, str]:
    """Extrai requirement de <attribute> em <requirements>.

    Convenção interna: pset="" indica atributo direto do elemento IFC (ex: LongName).
    facet_type é 'property' (atributo direto é semanticamente equivalente a propriedade).
    """
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
```

- [ ] **Step 2.4: Atualizar `_parse_relation_requirement`**

Substituir a função existente por:

```python
def _parse_relation_requirement(rel_el: "etree._Element") -> dict[str, str]:
    """Extrai requirement de <relation> em <requirements>.

    Convenção interna: pset="IFC_RELATION" indica relação IFC (ex: IfcRelFillsElement).
    """
    prop = _simplevalue(rel_el.find(f"{_IDS}name"))
    return {
        "facet_type": "relation",
        "pset": "IFC_RELATION",
        "prop": prop,
        "constraint": "exists",
        "constraint_type": "",
    }
```

- [ ] **Step 2.5: Atualizar `_make_spec()` nos testes**

Substituir a função `_make_spec` existente por:

```python
def _make_spec(
    entity: str,
    pset: str,
    prop: str,
    constraint: str = "exists",
    facet_type: str = "property",
) -> IDSSpecification:
    """Cria IDSSpecification mínima com um único requisito."""
    return IDSSpecification(
        name="Spec Teste",
        applicability_entity=entity,
        requirements=[{
            "facet_type": facet_type,
            "pset": pset,
            "prop": prop,
            "constraint": constraint,
            "constraint_type": "",
        }],
    )
```

- [ ] **Step 2.6: Atualizar chamadas de `_make_spec` que usam `Qto_`**

Os testes `test_generate_rules_quantities_*` usam `_make_spec("IFCWALL", "Qto_WallBaseQuantities", "NetSideArea")`. Atualizar cada chamada para passar `facet_type="quantity"`:

```python
# test_generate_rules_quantities_gets_geometric_strategy
spec = _make_spec("IFCWALL", "Qto_WallBaseQuantities", "NetSideArea", facet_type="quantity")

# test_generate_rules_quantities_infers_geometry_context
spec = _make_spec("IFCWALL", "Qto_WallBaseQuantities", "NetSideArea", facet_type="quantity")

# test_generate_rules_quantities_infers_write_action
spec = _make_spec("IFCWALL", "Qto_WallBaseQuantities", "NetSideArea", facet_type="quantity")
```

- [ ] **Step 2.7: Rodar suite completa**

```bash
pytest tests/test_translator.py -v
```

Esperado: todos PASSED incluindo `test_parse_budget_ids_reads_quantity_facets`.

- [ ] **Step 2.8: Commit**

```bash
git add src/translator/ids_parser.py tests/test_translator.py
git commit -m "feat(ids_parser): adiciona facet_type/constraint_type em parsers existentes e atualiza _make_spec"
```

---

## Task 3: `_parse_material_requirement` + `_parse_material_applicability_filter`

**Spec:** Suporte a `<material>` em `<requirements>` e em `<applicability>`.

**Files:**
- Modify: `src/translator/ids_parser.py` — 2 novas funções + wiring em `_parse_specification()`
- Modify: `tests/test_translator.py` — `test_parse_ids_material_facet`

---

- [ ] **Step 3.1: Escrever teste que vai falhar**

```python
def test_parse_ids_material_facet(tmp_path: Path) -> None:
    """<material> com simpleValue deve resultar em facet_type='material'
    e prop com o nome do material."""
    xml = _make_ids_xml("""
        <ids:material>
          <ids:value><ids:simpleValue>Concrete</ids:simpleValue></ids:value>
        </ids:material>
    """)
    ids_file = tmp_path / "test.ids"
    ids_file.write_text(xml, encoding="utf-8")

    specs = parse_ids(str(ids_file))

    assert len(specs[0].requirements) == 1
    req = specs[0].requirements[0]
    assert req["facet_type"] == "material"
    assert req["pset"] == ""
    assert req["prop"] == "Concrete"
    assert req["constraint"] == "equals:Concrete"
    assert req["constraint_type"] == "xs:string"
```

- [ ] **Step 3.2: Rodar e confirmar falha**

```bash
pytest tests/test_translator.py::test_parse_ids_material_facet -v
```

Esperado: `FAILED` — requirements vazio (parser não conhece `<material>` ainda).

- [ ] **Step 3.3: Implementar `_parse_material_requirement` e `_parse_material_applicability_filter`**

Inserir após `_parse_relation_requirement`:

```python
def _parse_material_requirement(mat_el: "etree._Element") -> dict[str, str]:
    """Extrai requirement de <material> em <requirements>.

    prop: nome/valor do material (de <value>), ou "" se ausente.
    constraint/constraint_type: via _extract_constraint.
    """
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
    """Extrai filtro de <material> em <applicability>.

    Retorna {pset: "", prop: "material", value: <simpleValue>}.
    """
    value_el = mat_el.find(f"{_IDS}value")
    value = _simplevalue(value_el) if value_el is not None else ""
    return {"pset": "", "prop": "material", "value": value}
```

- [ ] **Step 3.4: Wirear em `_parse_specification()`**

No bloco de `applicability_el`, após o loop de `property`:

```python
        for mat_el in applicability_el.findall(f"{_IDS}material"):
            applicability_filters.append(_parse_material_applicability_filter(mat_el))
```

No bloco de `requirements_el`, após o loop de `relation`:

```python
        for mat_el in requirements_el.findall(f"{_IDS}material"):
            requirements.append(_parse_material_requirement(mat_el))
```

- [ ] **Step 3.5: Rodar e confirmar que o teste passa**

```bash
pytest tests/test_translator.py -v
```

Esperado: `test_parse_ids_material_facet` PASSED. Todos os demais PASSED.

- [ ] **Step 3.6: Commit**

```bash
git add src/translator/ids_parser.py tests/test_translator.py
git commit -m "feat(ids_parser): adiciona suporte a facet <material> em requirements e applicability"
```

---

## Task 4: `_parse_classification_requirement`

**Spec:** Suporte a `<classification>` em `<requirements>`.

**Files:**
- Modify: `src/translator/ids_parser.py` — nova função + wiring
- Modify: `tests/test_translator.py` — `test_parse_ids_classification_facet`

---

- [ ] **Step 4.1: Escrever teste que vai falhar**

```python
def test_parse_ids_classification_facet(tmp_path: Path) -> None:
    """<classification> deve resultar em facet_type='classification',
    pset=sistema e prop=código."""
    xml = _make_ids_xml("""
        <ids:classification>
          <ids:system><ids:simpleValue>Uniclass</ids:simpleValue></ids:system>
          <ids:value><ids:simpleValue>Ss_20_10_30</ids:simpleValue></ids:value>
        </ids:classification>
    """)
    ids_file = tmp_path / "test.ids"
    ids_file.write_text(xml, encoding="utf-8")

    specs = parse_ids(str(ids_file))
    req = specs[0].requirements[0]

    assert req["facet_type"] == "classification"
    assert req["pset"] == "Uniclass"
    assert req["prop"] == "Ss_20_10_30"
    assert req["constraint"] == "equals:Ss_20_10_30"
    assert req["constraint_type"] == "xs:string"
```

- [ ] **Step 4.2: Rodar e confirmar falha**

```bash
pytest tests/test_translator.py::test_parse_ids_classification_facet -v
```

Esperado: `FAILED` — requirements vazio.

- [ ] **Step 4.3: Implementar `_parse_classification_requirement`**

Inserir após `_parse_material_applicability_filter`:

```python
def _parse_classification_requirement(cls_el: "etree._Element") -> dict[str, str]:
    """Extrai requirement de <classification> em <requirements>.

    pset: nome do sistema de classificação (ex: "Uniclass", "OmniClass").
    prop: código/referência de classificação (de <value>).
    """
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
```

- [ ] **Step 4.4: Wirear em `_parse_specification()`**

No bloco de `requirements_el`, após o loop de `material`:

```python
        for cls_el in requirements_el.findall(f"{_IDS}classification"):
            requirements.append(_parse_classification_requirement(cls_el))
```

- [ ] **Step 4.5: Rodar suite completa**

```bash
pytest tests/test_translator.py -v
```

Esperado: `test_parse_ids_classification_facet` PASSED. Todos os demais PASSED.

- [ ] **Step 4.6: Commit**

```bash
git add src/translator/ids_parser.py tests/test_translator.py
git commit -m "feat(ids_parser): adiciona suporte a facet <classification> em requirements"
```

---

## Task 5: `_parse_partof_requirement`

**Spec:** Suporte a `<partOf>` em `<requirements>` para contenção espacial IFC.

**Files:**
- Modify: `src/translator/ids_parser.py` — nova função + wiring
- Modify: `tests/test_translator.py` — `test_parse_ids_partof_facet`

---

- [ ] **Step 5.1: Escrever teste que vai falhar**

```python
def test_parse_ids_partof_facet(tmp_path: Path) -> None:
    """<partOf> deve resultar em facet_type='relation', pset='IFC_RELATION'
    e prop com o nome da entidade contenedora."""
    xml = _make_ids_xml("""
        <ids:partOf>
          <ids:entity>
            <ids:name><ids:simpleValue>IFCBUILDINGSTOREY</ids:simpleValue></ids:name>
          </ids:entity>
        </ids:partOf>
    """)
    ids_file = tmp_path / "test.ids"
    ids_file.write_text(xml, encoding="utf-8")

    specs = parse_ids(str(ids_file))
    req = specs[0].requirements[0]

    assert req["facet_type"] == "relation"
    assert req["pset"] == "IFC_RELATION"
    assert req["prop"] == "IFCBUILDINGSTOREY"
    assert req["constraint"] == "exists"
    assert req["constraint_type"] == ""
```

- [ ] **Step 5.2: Rodar e confirmar falha**

```bash
pytest tests/test_translator.py::test_parse_ids_partof_facet -v
```

Esperado: `FAILED` — requirements vazio.

- [ ] **Step 5.3: Implementar `_parse_partof_requirement`**

Inserir após `_parse_classification_requirement`:

```python
def _parse_partof_requirement(part_el: "etree._Element") -> dict[str, str]:
    """Extrai requirement de <partOf> em <requirements>.

    Trata contenção espacial IFC (ex: IfcRelContainedInSpatialStructure).
    prop: nome da entidade contenedora (ex: "IFCBUILDINGSTOREY").
    Convenção interna: pset="IFC_RELATION" (mesma de <relation>).
    """
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
```

- [ ] **Step 5.4: Wirear em `_parse_specification()`**

No bloco de `requirements_el`, após o loop de `classification`:

```python
        for part_el in requirements_el.findall(f"{_IDS}partOf"):
            requirements.append(_parse_partof_requirement(part_el))
```

- [ ] **Step 5.5: Rodar suite completa**

```bash
pytest tests/test_translator.py -v
```

Esperado: todos os testes PASSED — incluindo os 5 exigidos pelo spec + `test_parse_ids_partof_facet`.

- [ ] **Step 5.6: Rodar testes de modelos para garantir nenhuma regressão**

```bash
pytest tests/test_models.py tests/test_translator.py -v
```

Esperado: todos PASSED.

- [ ] **Step 5.7: Commit final**

```bash
git add src/translator/ids_parser.py tests/test_translator.py
git commit -m "feat(ids_parser): adiciona suporte a facet <partOf> em requirements"
```

---

## Self-Review

**Spec coverage:**
- ✅ `<material>` em requirements → Task 3
- ✅ `<classification>` em requirements → Task 4
- ✅ `<partOf>` em requirements → Task 5
- ✅ `<material>` em applicability_filters → Task 3 (`_parse_material_applicability_filter`)
- ✅ constraint extraction com `xs:string enumeration` → `_extract_constraint` (Task 1)
- ✅ constraint extraction com `xs:double minInclusive` → `_extract_constraint` (Task 1)
- ✅ `facet_type` em todos os requirements → Tasks 1, 2, 3, 4, 5
- ✅ `constraint_type` em todos os requirements → Tasks 1, 2, 3, 4, 5
- ✅ `test_parse_budget_ids_reads_quantity_facets` → Task 2
- ✅ `test_parse_energy_ids_reads_thermal_specs` → Task 1
- ✅ `test_parse_ids_material_facet` → Task 3
- ✅ `test_parse_ids_classification_facet` → Task 4
- ✅ `test_parse_ids_with_restriction` → Task 1
- ✅ `_make_spec()` atualizado → Task 2
