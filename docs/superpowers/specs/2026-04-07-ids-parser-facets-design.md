# Design: Suporte a Facets Adicionais no IDS Parser

**Data:** 2026-04-07  
**Escopo:** `src/translator/ids_parser.py`, `src/models.py`, `tests/test_translator.py`  
**Status:** Aprovado

---

## Contexto

O `parse_ids()` atual suporta apenas `<property>`, `<attribute>` e `<relation>` nos `<requirements>`. Os novos arquivos `budget_readiness.ids` e `energy_readiness.ids` usam facets adicionais do padrão IDS 1.0: `<material>`, `<classification>` e `<partOf>`. Além disso, o campo `facet_type` está ausente nos dicts de requirement, dificultando o downstream (rule_generator) distinguir o tipo de verificação a realizar.

---

## Objetivos

1. Adicionar suporte a `<material>`, `<classification>` e `<partOf>` em `<requirements>` (e `<material>` em `<applicability>`).
2. Adicionar campo `facet_type` obrigatório em todos os dicts de requirement (novos e existentes).
3. Centralizar extração de constraints (`xs:restriction`) em um helper reutilizável.
4. Manter `IDSSpecification.requirements: list[dict[str, str]]` — todos os valores são strings.
5. Cobrir com 5 novos testes.

---

## Estrutura do Dict de Requirement

Após a mudança, cada entry em `requirements` terá:

```python
{
    "facet_type":      str,  # "property" | "quantity" | "material" | "classification" | "relation"
    "pset":            str,  # "" se não aplicável
    "prop":            str,  # nome da propriedade, atributo, material ou entidade
    "constraint":      str,  # "exists" | "not_empty" | "equals:X" | "minInclusive" | tag_local
    "constraint_type": str,  # "xs:string" | "xs:double" | "" (vazio se sem restriction)
}
```

Regras de `facet_type`:
- `<property>` com pset começando em `"Qto_"` → `"quantity"`
- `<property>` demais → `"property"`
- `<attribute>` → `"property"` (atributo direto, semanticamente equivalente)
- `<relation>` (customizado) → `"relation"`, `pset="IFC_RELATION"`
- `<material>` → `"material"`, `pset=""`
- `<classification>` → `"classification"`, `pset=<sistema>` (ex: `"Uniclass"`)
- `<partOf>` → `"relation"`, `pset="IFC_RELATION"`, `prop=<entity>` (ex: `"IfcBuildingStorey"`)

---

## Novos Parsers

### `_extract_constraint(value_el) -> tuple[str, str]`

Helper privado centralizado para extrair `(constraint, constraint_type)` de um elemento `<value>` (ou None).

| Situação | constraint | constraint_type |
|---|---|---|
| `value_el` é None | `"exists"` | `""` |
| `<simpleValue>X</simpleValue>` | `"equals:X"` | `"xs:string"` |
| `<xs:restriction base="xs:string"><xs:enumeration value="X"/>` | `"equals:X"` | `"xs:string"` |
| `<xs:restriction base="xs:double"><xs:minInclusive value="0"/>` | `"minInclusive"` | `"xs:double"` |
| `<xs:restriction base="xs:string"><xs:minLength value="1"/>` | `"not_empty"` | `"xs:string"` |
| Outro restriction | tag local do primeiro filho | base sem namespace |

### `_parse_material_requirement(mat_el) -> dict[str, str]`

Extrai material de `<material>` em `<requirements>`:
- `facet_type`: `"material"`
- `pset`: `""`
- `prop`: valor de `<value>` (simpleValue ou enumeration), ou `""` se ausente
- `constraint` / `constraint_type`: via `_extract_constraint`

### `_parse_classification_requirement(cls_el) -> dict[str, str]`

Extrai classificação de `<classification>` em `<requirements>`:
- `facet_type`: `"classification"`
- `pset`: valor de `<system>` (o sistema de classificação, ex: `"Uniclass"`)
- `prop`: valor de `<value>` (o código ou referência)
- `constraint` / `constraint_type`: via `_extract_constraint` no `<value>`

### `_parse_partof_requirement(part_el) -> dict[str, str]`

Extrai contenção espacial de `<partOf>` em `<requirements>`:
- `facet_type`: `"relation"`
- `pset`: `"IFC_RELATION"`
- `prop`: valor de `<entity><name>` (ex: `"IfcBuildingStorey"`)
- `constraint`: `"exists"`
- `constraint_type`: `""`

---

## Parsers Existentes — Mudanças

| Parser | Mudança |
|---|---|
| `_parse_property_requirement` | Adiciona `facet_type` (`"quantity"` se pset começa com `"Qto_"`, senão `"property"`); migra para `_extract_constraint` |
| `_parse_attribute_requirement` | Adiciona `facet_type: "property"`; migra para `_extract_constraint` |
| `_parse_relation_requirement` | Adiciona `facet_type: "relation"` |

---

## `_parse_specification()` — Novos Loops

```python
for mat_el in requirements_el.findall(f"{_IDS}material"):
    requirements.append(_parse_material_requirement(mat_el))
for cls_el in requirements_el.findall(f"{_IDS}classification"):
    requirements.append(_parse_classification_requirement(cls_el))
for part_el in requirements_el.findall(f"{_IDS}partOf"):
    requirements.append(_parse_partof_requirement(part_el))
```

`<material>` em `<applicability>` também é suportado: adicionar loop em `_parse_specification()` que chama `_parse_material_applicability_filter(mat_el) -> dict[str, str]`, retornando `{"pset": "", "prop": "material", "value": <simpleValue>}`.

---

## `IDSSpecification` em `models.py`

Nenhuma mudança no tipo Pydantic — `requirements: list[dict[str, str]]` permanece. A semântica dos campos é documentada via docstring atualizada.

---

## Testes

Todos os testes usam XML inline via `etree.fromstring()` para não depender de arquivos `.ids` em disco.

| Teste | O que verifica |
|---|---|
| `test_parse_budget_ids_reads_quantity_facets` | `<property>` em `Qto_WallBaseQuantities` → `facet_type: "quantity"` |
| `test_parse_energy_ids_reads_thermal_specs` | `<property>` ThermalTransmittance com restriction double → `constraint_type: "xs:double"` |
| `test_parse_ids_material_facet` | `<material>` com simpleValue → `facet_type: "material"`, `prop` correto |
| `test_parse_ids_classification_facet` | `<classification>` com sistema e valor → `facet_type: "classification"`, `pset` = sistema |
| `test_parse_ids_with_restriction` | `<restriction base="xs:double"><minInclusive value="0">` → `constraint: "minInclusive"`, `constraint_type: "xs:double"` |

`_make_spec()` em `test_translator.py` recebe parâmetro opcional `facet_type: str = "property"` e inclui `"constraint_type": ""` no dict. Testes que usam `Qto_` passam `facet_type="quantity"` explicitamente (ex: `test_generate_rules_quantities_*`). Isso mantém todos os testes existentes passando sem alteração de assinatura pública.

---

## O que NÃO está no escopo

- Mudanças no `rule_generator.py` para consumir `facet_type` (próxima iteração).
- Suporte a `<classification>` e `<partOf>` em `<applicability>` (apenas `<material>` em applicability está no escopo).
- Arquivo `.ids` de fixture para os novos testes (XML inline é suficiente).
