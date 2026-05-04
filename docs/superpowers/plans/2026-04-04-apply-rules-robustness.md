# apply_rules Robustness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tornar `apply_rules()` em `src/translator/rule_generator.py` robusto com novos operadores de filtro, checagens corretas por tipo e descrições padronizadas de Issues.

**Architecture:** Refatoria os helpers internos de `rule_generator.py` em dois: `_get_pset_value` (leitura de propriedade) e `_evaluate_condition` (avalia um condition dict com qualquer operador). `_matches_filter` passa a delegar para `_evaluate_condition`. A função `apply_rules` usa esses helpers e passa a gerar descrições no formato canônico. Nenhum modelo de dados é alterado.

**Tech Stack:** Python 3.11, ifcopenshell 0.8+, ifcopenshell.util.element.get_psets, Pydantic v2, pytest

---

## File Map

| Arquivo | Ação |
|---|---|
| `src/translator/rule_generator.py` | Modificar: renomear `_get_prop_value` → `_get_pset_value`, adicionar `_evaluate_condition`, expandir operadores, corrigir checagens, corrigir descrição das Issues |
| `tests/test_translator.py` | Modificar: adicionar 6 novos testes para `apply_rules` |

---

## Current State (o que existe e o que está errado)

Antes de codificar, entenda o que precisa mudar em `rule_generator.py`:

| Função | Estado atual | Problema |
|---|---|---|
| `_get_prop_value` | existe | nome diferente do especificado; renomear para `_get_pset_value` |
| `_matches_filter` | existe | só suporta `"EXISTS"` e `"=="` — faltam `"!="`, `"NOT_EXISTS"`, `"CONTAINS"` |
| `_passes_check` `"is_numeric"` | existe | não verifica `> 0` |
| `_passes_check` `"equals"` | existe | retorna `value is not None` — não compara valor real |
| `_evaluate_condition` | não existe | precisa ser criado |
| Issue `description` | formato livre | precisa ser `f"{filter_entity} #{short_guid}: {check_pset}.{check_property} — regra '{source_spec}'"` |

---

## Task 1: Escrever os 6 testes falhando

**Files:**
- Modify: `tests/test_translator.py`

### Contexto dos fixtures IFC

Cada teste cria um `ifcopenshell.file` em memória com o elemento necessário. Use o padrão mínimo:

```python
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid
import ifcopenshell.util.element

def _make_ifc() -> ifcopenshell.file:
    """Cria arquivo IFC2X3 mínimo (sem hierarquia, só o file objeto)."""
    return ifcopenshell.api.run("project.create_file", version="IFC2X3")
```

Não é necessário criar Project/Site/Building/Storey para `apply_rules` — a função usa `ifc_file.by_type()` diretamente.

- [ ] **Step 1.1: Adicionar imports e helper `_make_ifc` ao test_translator.py**

No topo do arquivo, após os imports existentes, adicione:

```python
import ifcopenshell.api
import ifcopenshell.guid
import ifcopenshell.util.element

from src.models import OperationalRule
from src.translator.rule_generator import apply_rules


def _make_ifc() -> ifcopenshell.file:
    """Cria arquivo IFC2X3 mínimo para testes de apply_rules."""
    return ifcopenshell.api.run("project.create_file", version="IFC2X3")


def _wall_with_pset(
    f: ifcopenshell.file,
    props: dict,
    pset_name: str = "Pset_WallCommon",
) -> ifcopenshell.entity_instance:
    """Cria IfcWall com as propriedades informadas no pset_name."""
    wall = f.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="Wall Test")
    pset = ifcopenshell.api.run("pset.add_pset", f, product=wall, name=pset_name)
    ifcopenshell.api.run("pset.edit_pset", f, pset=pset, properties=props)
    return wall


def _rule_thermal(filter_is_external: bool = True) -> OperationalRule:
    """OperationalRule que exige ThermalTransmittance numérico em paredes externas."""
    conditions = (
        [{"pset": "Pset_WallCommon", "prop": "IsExternal", "operator": "==", "value": "TRUE"}]
        if filter_is_external
        else []
    )
    return OperationalRule(
        source_spec="NBR 15575 Thermal",
        filter_entity="IfcWall",
        filter_conditions=conditions,
        check_pset="Pset_WallCommon",
        check_property="ThermalTransmittance",
        check_type="is_numeric",
        severity="high",
    )
```

- [ ] **Step 1.2: Adicionar test_apply_rules_wall_missing_thermal**

```python
def test_apply_rules_wall_missing_thermal():
    """Parede externa sem ThermalTransmittance gera 1 Issue high."""
    f = _make_ifc()
    wall = _wall_with_pset(f, {"IsExternal": True})
    # ThermalTransmittance NÃO está no pset

    issues = apply_rules(f, [_rule_thermal()])

    assert len(issues) == 1
    issue = issues[0]
    assert issue.element_guid == wall.GlobalId
    assert issue.severity == "high"
    assert issue.issue_type == "pset_missing"
    assert "ThermalTransmittance" in issue.description
    assert "NBR 15575 Thermal" in issue.description
```

- [ ] **Step 1.3: Adicionar test_apply_rules_wall_with_thermal_passes**

```python
def test_apply_rules_wall_with_thermal_passes():
    """Parede externa com ThermalTransmittance numérico positivo não gera Issue."""
    f = _make_ifc()
    _wall_with_pset(f, {"IsExternal": True, "ThermalTransmittance": 2.48})

    issues = apply_rules(f, [_rule_thermal()])

    assert issues == []
```

- [ ] **Step 1.4: Adicionar test_apply_rules_filter_is_external_true**

```python
def test_apply_rules_filter_is_external_true():
    """Parede sem IsExternal=True não passa no filtro e não gera Issue."""
    f = _make_ifc()
    _wall_with_pset(f, {"IsExternal": False})
    # Filtro exige IsExternal == TRUE → elemento rejeitado

    issues = apply_rules(f, [_rule_thermal(filter_is_external=True)])

    assert issues == []
```

- [ ] **Step 1.5: Adicionar test_apply_rules_space_empty_longname**

```python
def test_apply_rules_space_empty_longname():
    """IfcSpace com LongName vazio gera Issue para regra not_empty."""
    f = _make_ifc()
    space = f.create_entity(
        "IfcSpace",
        GlobalId=ifcopenshell.guid.new(),
        Name="Room 1",
        LongName="",
    )

    rule = OperationalRule(
        source_spec="NBR 15575 Space",
        filter_entity="IfcSpace",
        filter_conditions=[],
        check_pset="",          # atributo direto
        check_property="LongName",
        check_type="not_empty",
        issue_type="space_unnamed",
        severity="low",
    )

    issues = apply_rules(f, [rule])

    assert len(issues) == 1
    assert issues[0].element_guid == space.GlobalId
    assert issues[0].issue_type == "space_unnamed"
    assert "LongName" in issues[0].description
```

- [ ] **Step 1.6: Adicionar test_apply_rules_unknown_entity_skipped**

```python
def test_apply_rules_unknown_entity_skipped():
    """Regra com filter_entity inexistente não levanta exceção e retorna lista vazia."""
    f = _make_ifc()

    rule = OperationalRule(
        source_spec="Spec Fantasma",
        filter_entity="IfcClasseQueNaoExiste",
        filter_conditions=[],
        check_pset="Pset_X",
        check_property="PropX",
        check_type="exists",
        severity="low",
    )

    issues = apply_rules(f, [rule])

    assert issues == []
```

- [ ] **Step 1.7: Adicionar test_apply_rules_boolean_filter**

```python
def test_apply_rules_boolean_filter():
    """Filtro com operador '!=' exclui parede com IsExternal=True do check."""
    f = _make_ifc()
    # Parede externa: IsExternal=True → filtro != TRUE rejeita → sem Issue
    _wall_with_pset(f, {"IsExternal": True, "ThermalTransmittance": None})
    # Parede interna: IsExternal=False → filtro != TRUE aceita → Issue (Thermal ausente)
    wall_int = _wall_with_pset(f, {"IsExternal": False})

    rule = OperationalRule(
        source_spec="Internal Walls",
        filter_entity="IfcWall",
        filter_conditions=[
            {"pset": "Pset_WallCommon", "prop": "IsExternal", "operator": "!=", "value": "TRUE"}
        ],
        check_pset="Pset_WallCommon",
        check_property="ThermalTransmittance",
        check_type="is_numeric",
        severity="medium",
    )

    issues = apply_rules(f, [rule])

    assert len(issues) == 1
    assert issues[0].element_guid == wall_int.GlobalId
```

- [ ] **Step 1.8: Executar os testes — confirmar que TODOS falham**

```bash
cd "C:\Users\Keller_\Desktop\Projetos FC\Pesquisa\ifc-quality-copilot"
python -m pytest tests/test_translator.py -k "apply_rules" -v
```

Saída esperada: 6 FAILED (podem falhar por `AssertionError` ou `NameError` dependendo do estado atual).

> **Nota:** `test_apply_rules_unknown_entity_skipped` pode passar já, pois `apply_rules` existente captura exceções. Isso é esperado.

- [ ] **Step 1.9: Commit dos testes**

```bash
git add tests/test_translator.py
git commit -m "test(translator): adiciona 6 testes falhando para apply_rules robusto"
```

---

## Task 2: Renomear `_get_prop_value` → `_get_pset_value`

**Files:**
- Modify: `src/translator/rule_generator.py`

O helper atual `_get_prop_value` faz essencialmente o que o spec pede, mas com nome diferente. Vamos renomear e garantir que trata todos os casos.

- [ ] **Step 2.1: Substituir a definição de `_get_prop_value` por `_get_pset_value`**

Localize (aprox. linha 262) e substitua toda a função:

```python
def _get_pset_value(
    element: ifcopenshell.entity_instance,
    pset_name: str,
    prop_name: str,
) -> Any:
    """Retorna o valor de uma propriedade ou atributo de um elemento IFC.

    Convenções:
        pset_name == ""            → atributo direto via getattr (ex: LongName, Name)
        pset_name == "IFC_RELATION" → não aplicável aqui; retorna None
        outros                     → lê via ifcopenshell.util.element.get_psets()
    """
    if pset_name == _PSET_ATTRIBUTE:
        return getattr(element, prop_name, None)

    if pset_name == _PSET_RELATION:
        return None

    try:
        psets = ifcopenshell.util.element.get_psets(element)
    except Exception:
        return None

    pset_data = psets.get(pset_name)
    if pset_data is None:
        return None
    return pset_data.get(prop_name)
```

- [ ] **Step 2.2: Atualizar todas as chamadas internas de `_get_prop_value` para `_get_pset_value`**

Em `_passes_check` (aprox. linha 302), a linha:
```python
value = _get_prop_value(element, pset_name, prop_name)
```
vira:
```python
value = _get_pset_value(element, pset_name, prop_name)
```

- [ ] **Step 2.3: Rodar os testes existentes para garantir que não quebramos nada**

```bash
python -m pytest tests/test_translator.py -v
```

Saída esperada: os 4 testes anteriores passam. Os 6 novos ainda falham.

---

## Task 3: Implementar `_evaluate_condition`

**Files:**
- Modify: `src/translator/rule_generator.py`

Este helper centraliza toda a lógica de avaliação de um condition dict. Substitui a lógica inline de `_matches_filter`.

- [ ] **Step 3.1: Adicionar `_evaluate_condition` logo após `_get_pset_value`**

```python
def _evaluate_condition(
    element: ifcopenshell.entity_instance,
    condition: dict[str, str],
    ifc_file: ifcopenshell.file,
) -> bool:
    """Avalia se um elemento satisfaz uma condition dict.

    Operadores suportados:
        "EXISTS"     → propriedade existe e não é None
        "NOT_EXISTS" → propriedade é None ou ausente
        "=="         → valor == condition["value"] (com normalização booleana)
        "!="         → valor != condition["value"] (com normalização booleana)
        "CONTAINS"   → str(valor) contém condition["value"] (case-insensitive)

    Atributos diretos (pset == "") são lidos via getattr.
    Propriedades de Pset são lidas via get_psets().
    """
    pset = condition.get("pset", "")
    prop = condition.get("prop", "")
    operator = condition.get("operator", "EXISTS")
    expected_raw = condition.get("value", "")

    value = _get_pset_value(element, pset, prop)

    if operator == "EXISTS":
        return value is not None

    if operator == "NOT_EXISTS":
        return value is None

    if operator in ("==", "!="):
        normalized_expected = _normalize_bool(expected_raw)
        if normalized_expected is not None:
            # comparação booleana
            match = (value == normalized_expected)
        else:
            match = (str(value) == expected_raw)
        return match if operator == "==" else not match

    if operator == "CONTAINS":
        if value is None:
            return False
        return expected_raw.lower() in str(value).lower()

    # operador desconhecido → passa (comportamento conservador)
    return True
```

- [ ] **Step 3.2: Rodar os testes novamente — confirmar estado**

```bash
python -m pytest tests/test_translator.py -v
```

Saída esperada: os 4 testes anteriores passam. Os 6 novos ainda falham (ainda não atualizamos `_matches_filter` nem `_passes_check` nem a descrição).

---

## Task 4: Atualizar `_matches_filter` para usar `_evaluate_condition`

**Files:**
- Modify: `src/translator/rule_generator.py`

- [ ] **Step 4.1: Substituir a implementação de `_matches_filter`**

Localize a função (aprox. linha 223) e substitua:

```python
def _matches_filter(
    element: ifcopenshell.entity_instance,
    conditions: list[dict[str, str]],
    ifc_file: ifcopenshell.file | None = None,
) -> bool:
    """Verifica se um elemento satisfaz TODAS as filter_conditions.

    Delega a avaliação de cada condição para _evaluate_condition.
    """
    if not conditions:
        return True

    _ifc = ifc_file or element.wrapped_data.file  # fallback; normalmente não usado aqui
    for condition in conditions:
        try:
            if not _evaluate_condition(element, condition, _ifc):
                return False
        except Exception:
            return False

    return True
```

> **Nota sobre `ifc_file`:** A assinatura da função interna pode ser mantida sem o parâmetro `ifc_file` para compatibilidade com os chamadores existentes em `apply_rules`. O `_ifc` interno é um fallback seguro. O parâmetro público de `_evaluate_condition` recebe o `ifc_file` passado de `apply_rules`.

- [ ] **Step 4.2: Verificar que `apply_rules` passa `ifc_file` para `_matches_filter`**

Em `apply_rules`, localize a chamada:
```python
if not _matches_filter(element, rule.filter_conditions):
```
Substitua por:
```python
if not _matches_filter(element, rule.filter_conditions, ifc_file):
```

- [ ] **Step 4.3: Rodar testes — verificar progresso**

```bash
python -m pytest tests/test_translator.py -k "apply_rules" -v
```

Saída esperada: `test_apply_rules_filter_is_external_true`, `test_apply_rules_unknown_entity_skipped` e `test_apply_rules_boolean_filter` devem passar agora. Os outros 3 ainda falham.

---

## Task 5: Corrigir `_passes_check` — `is_numeric` e `equals`

**Files:**
- Modify: `src/translator/rule_generator.py`

- [ ] **Step 5.1: Substituir a implementação de `_passes_check`**

Localize (aprox. linha 288) e substitua:

```python
def _passes_check(
    element: ifcopenshell.entity_instance,
    pset_name: str,
    prop_name: str,
    check_type: str,
) -> bool:
    """Verifica se o elemento passa no check definido pela regra.

    Relações IFC (pset_name == "IFC_RELATION") são ignoradas aqui —
    tratadas por relation_diagnostics.
    """
    if pset_name == _PSET_RELATION:
        return True

    value = _get_pset_value(element, pset_name, prop_name)

    if check_type == "exists":
        return value is not None

    if check_type == "is_numeric":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0

    if check_type == "is_boolean":
        return isinstance(value, bool)

    if check_type == "not_empty":
        if value is None:
            return False
        return str(value).strip() != ""

    if check_type == "equals":
        # Sem check_value no OperationalRule: verifica apenas existência
        return value is not None

    return True
```

A única mudança real é `is_numeric`: adicionado `and value > 0`.

- [ ] **Step 5.2: Rodar testes — verificar progresso**

```bash
python -m pytest tests/test_translator.py -k "apply_rules" -v
```

Saída esperada: `test_apply_rules_wall_with_thermal_passes` e `test_apply_rules_space_empty_longname` devem passar. Restam `test_apply_rules_wall_missing_thermal` e `test_apply_rules_boolean_filter` (a descrição ainda está no formato antigo).

---

## Task 6: Corrigir o formato de `description` das Issues em `apply_rules`

**Files:**
- Modify: `src/translator/rule_generator.py`

- [ ] **Step 6.1: Substituir o bloco de criação do Issue em `apply_rules`**

Localize (aprox. linha 362) o trecho:
```python
element_name: str | None = getattr(element, "Name", None)
description = (
    f"{rule.check_pset}.{rule.check_property} ausente ou inválido"
    if rule.check_pset
    else f"Atributo {rule.check_property} ausente ou vazio"
)
```

Substitua por:
```python
short_guid = element.GlobalId[:8]
description = (
    f"{rule.filter_entity} #{short_guid}: "
    f"{rule.check_pset}.{rule.check_property} — regra '{rule.source_spec}'"
)
```

E remova `element_name` da linha abaixo (se ainda referenciada no Issue — mantenha `element_name=getattr(element, "Name", None)` no Issue, apenas mude o `description`):

O bloco final de criação do Issue deve ficar:

```python
short_guid = element.GlobalId[:8]
description = (
    f"{rule.filter_entity} #{short_guid}: "
    f"{rule.check_pset}.{rule.check_property} — regra '{rule.source_spec}'"
)

issue = Issue(
    element_guid=element.GlobalId,
    element_class=element.is_a(),
    element_name=getattr(element, "Name", None),
    issue_type=rule.issue_type,  # type: ignore[arg-type]
    severity=rule.severity,
    description=description,
    context={
        "rule_id": rule.id,
        "check_pset": rule.check_pset,
        "check_property": rule.check_property,
        "check_type": rule.check_type,
        "normative_ref": rule.normative_ref,
    },
)
```

- [ ] **Step 6.2: Rodar todos os testes do translator**

```bash
python -m pytest tests/test_translator.py -v
```

Saída esperada: **10 passed** (4 existentes + 6 novos).

- [ ] **Step 6.3: Rodar suite completa para detectar regressões**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Saída esperada: todos os testes do projeto passam.

- [ ] **Step 6.4: Commit final**

```bash
git add src/translator/rule_generator.py tests/test_translator.py
git commit -m "feat(translator): torna apply_rules robusto com novos operadores e descrição padronizada"
```

---

## Self-Review

### Cobertura da spec

| Requisito | Task que implementa |
|---|---|
| Operadores "==", "!=" | Task 3 (`_evaluate_condition`) |
| Operadores "EXISTS", "NOT_EXISTS" | Task 3 (`_evaluate_condition`) |
| Operador "CONTAINS" | Task 3 (`_evaluate_condition`) |
| Conversão booleana TRUE/FALSE | Task 3 (`_evaluate_condition`) |
| `is_numeric` > 0 | Task 5 (`_passes_check`) |
| `is_boolean` | Task 5 (já existia, mantido) |
| `not_empty` | Task 5 (já existia, mantido) |
| `equals` (sem check_value) | Task 5 (`_passes_check` → exists fallback) |
| `_get_pset_value` helper | Task 2 (renomear + melhorar) |
| `_evaluate_condition` helper | Task 3 |
| Descrição canônica das Issues | Task 6 |
| test_apply_rules_wall_missing_thermal | Task 1 |
| test_apply_rules_wall_with_thermal_passes | Task 1 |
| test_apply_rules_filter_is_external_true | Task 1 |
| test_apply_rules_space_empty_longname | Task 1 |
| test_apply_rules_unknown_entity_skipped | Task 1 |
| test_apply_rules_boolean_filter | Task 1 |

### Verificação de tipos e nomes

- `_get_pset_value(element, pset_name, prop_name)` → usado em `_passes_check` (Task 5) e `_evaluate_condition` (Task 3) ✓
- `_evaluate_condition(element, condition, ifc_file)` → chamado em `_matches_filter` (Task 4) ✓
- `_matches_filter(element, conditions, ifc_file=None)` → chamado em `apply_rules` com `ifc_file` (Task 4) ✓
- `issue.description` usa `rule.filter_entity`, `rule.check_pset`, `rule.check_property`, `rule.source_spec` — todos campos de `OperationalRule` ✓

### Placeholders

Nenhum TBD ou TODO no plano. Todos os code blocks são completos.
