# Profile Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand `src/suggestion_engine/prompt_templates.py` with a `PROFILE_TEMPLATES` dict containing 6 role-aware prompt variants keyed by `(profile_id, issue_type)`, wire them into `build_prompt`, and verify them with 4 focused tests.

**Architecture:** `PROFILE_TEMPLATES` lives in the same module as `TEMPLATES`. `build_prompt` gains an optional `profile_id` parameter; when provided it checks `PROFILE_TEMPLATES` before falling back to the generic `_select_template` path. `_normalize_option` is extended to handle the two new label keys (`codigo`, `nome_ativo`) introduced by the budget and FM profiles. A new test file `tests/test_prompt_templates.py` keeps template-rendering tests isolated from the suggestion-engine integration tests in `test_suggestion.py`.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, existing `src.models.Issue` and `src.models.Suggestion`.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `src/suggestion_engine/prompt_templates.py` | Add `PROFILE_TEMPLATES`, helper `_select_profile_template`, update `build_prompt` signature and `_normalize_option` |
| Create | `tests/test_prompt_templates.py` | Four focused tests for profile template rendering |

---

## Task 1: Add `PROFILE_TEMPLATES` dict

**Files:**
- Modify: `src/suggestion_engine/prompt_templates.py` (after the `TEMPLATES` dict, before `_format_list`)

- [ ] **Step 1: Write the failing test (import only)**

Create `tests/test_prompt_templates.py`:

```python
"""Testes para templates de prompt por perfil."""

import pytest

from src.suggestion_engine.prompt_templates import PROFILE_TEMPLATES


def test_profile_templates_keys_exist():
    expected = {
        ("budget_readiness", "quantity_missing"),
        ("budget_readiness", "classification_missing"),
        ("energy_readiness", "thermal_incomplete"),
        ("energy_readiness", "space_unnamed"),
        ("fm_readiness", "space_unnamed"),
        ("fm_readiness", "asset_unidentified"),
    }
    assert expected == set(PROFILE_TEMPLATES.keys())
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_prompt_templates.py::test_profile_templates_keys_exist -v
```

Expected: `ImportError` or `AttributeError` — `PROFILE_TEMPLATES` does not exist yet.

- [ ] **Step 3: Add `PROFILE_TEMPLATES` to `prompt_templates.py`**

Insert after the closing `}` of `TEMPLATES` (line 190) and before `_format_list`:

```python
PROFILE_TEMPLATES: dict[tuple[str, str], str] = {
    ("budget_readiness", "quantity_missing"): (
        "Você é um orçamentista brasileiro. O modelo BIM precisa de quantitativos confiáveis.\n"
        "ELEMENTO: {element_class} #{guid}\n"
        "DADOS GEOMÉTRICOS DISPONÍVEIS: {geometry_data}\n"
        "MATERIAL: {material}\n"
        "ESPESSURA: {thickness}\n"
        "QUANTIDADE FALTANTE: {quantity_name}\n"
        "Calcule ou estime {quantity_name} com base nos dados. "
        "Se o cálculo é direto, dê o valor exato. Se é estimativa, justifique.\n"
        '{{"opcoes": [{{"valor": ..., "unidade": "...", '
        '"metodo_calculo": "...", "confianca": "alta/media/baixa"}}]}}'
    ),
    ("budget_readiness", "classification_missing"): (
        "Você é um orçamentista brasileiro que trabalha com SINAPI e TCPO.\n"
        "ELEMENTO: {element_class} #{guid}\n"
        "MATERIAL: {material}, ESPESSURA: {thickness}cm, CAMADAS: {layers}\n"
        "TAREFA: Sugira 3 classificações orçamentárias para este elemento.\n"
        '{{"opcoes": [{{"codigo": "...", "descricao": "...", '
        '"fonte": "SINAPI/TCPO", "confianca": "..."}}]}}'
    ),
    ("energy_readiness", "thermal_incomplete"): (
        "Você é um engenheiro de desempenho térmico brasileiro, "
        "especialista em NBR 15575 e RTQ-C.\n"
        "CONTEXTO: Zona bioclimática {zone}, {building_type}\n"
        "ELEMENTO: {element_class} #{guid}\n"
        "PROPRIEDADE FALTANTE: {property_name}\n"
        "DADOS: material={material}, espessura={thickness}cm, "
        "camadas={layers}, IsExternal={is_external}\n"
        "Sugira 3 valores para {property_name} com referência normativa.\n"
        '{{"opcoes": [{{"valor": ..., "unidade": "...", "referencia": "...", '
        '"justificativa": "...", "confianca": "..."}}]}}'
    ),
    ("energy_readiness", "space_unnamed"): (
        "Você é um engenheiro de energia que precisa classificar zonas térmicas.\n"
        'ESPAÇO: #{guid}, nome atual "{current_name}", área {area_m2}m²\n'
        "CONTÉM: {contained_elements}\n"
        "ADJACENTE A: {adjacent_spaces}\n"
        "PAREDES EXTERNAS ADJACENTES: {external_wall_count}\n"
        "TEM JANELA EXTERNA: {has_external_window}\n"
        "Sugira 3 nomes funcionais que facilitem o zoneamento térmico "
        '(ex: diferencie "Sala de estar" de "Dormitório" pois tem '
        "requisitos térmicos distintos na NBR 15575).\n"
        '{{"opcoes": [{{"nome": "...", '
        '"zona_termica_sugerida": "condicionado/não-condicionado", '
        '"justificativa": "...", "confianca": "..."}}]}}'
    ),
    ("fm_readiness", "space_unnamed"): (
        "Você é um gestor de facilities brasileiro.\n"
        'ESPAÇO: #{guid}, nome atual "{current_name}", área {area_m2}m²\n'
        "CONTÉM: {contained_elements}\n"
        "EQUIPAMENTOS/ATIVOS: {assets}\n"
        "PAVIMENTO: {floor}\n"
        "Sugira 3 nomes funcionais orientados para operação e manutenção "
        "(priorize nomenclatura que facilite rotas de inspeção e ordens de serviço).\n"
        '{{"opcoes": [{{"nome": "...", "categoria_fm": "...", '
        '"justificativa": "...", "confianca": "..."}}]}}'
    ),
    ("fm_readiness", "asset_unidentified"): (
        "Você é um gestor de facilities.\n"
        "EQUIPAMENTO: {element_class} #{guid}, PredefinedType={predefined_type}\n"
        "LOCALIZAÇÃO: {containing_space}, pavimento {floor}\n"
        'NOME ATUAL: "{name}" (genérico ou vazio)\n'
        "Sugira 3 identificações para este ativo (nome funcional, categoria de manutenção).\n"
        '{{"opcoes": [{{"nome_ativo": "...", "categoria": "...", '
        '"periodicidade_manutencao": "...", "confianca": "..."}}]}}'
    ),
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_prompt_templates.py::test_profile_templates_keys_exist -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/suggestion_engine/prompt_templates.py tests/test_prompt_templates.py
git commit -m "feat(templates): add PROFILE_TEMPLATES with 6 role-aware prompt variants"
```

---

## Task 2: Update `_normalize_option` for new label keys

**Files:**
- Modify: `src/suggestion_engine/prompt_templates.py` (function `_normalize_option`, lines 327–358)

New issue types need different label extraction:
- `quantity_missing` → `opt["valor"]`  (same as generic `valor` path — already covered)
- `classification_missing` → `opt["codigo"]` as label
- `thermal_incomplete` → `opt["valor"]`  (already covered)
- `asset_unidentified` → `opt["nome_ativo"]` as label

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_prompt_templates.py`:

```python
from src.suggestion_engine.prompt_templates import _normalize_option


def test_normalize_option_classification_missing():
    opt = {
        "codigo": "74209/001",
        "descricao": "Alvenaria de vedação bloco cerâmico",
        "fonte": "SINAPI",
        "confianca": "alta",
    }
    suggestion = _normalize_option(opt, "classification_missing")
    assert suggestion is not None
    assert suggestion.label == "74209/001"
    assert suggestion.value == "74209/001"
    assert suggestion.confidence == "alta"


def test_normalize_option_asset_unidentified():
    opt = {
        "nome_ativo": "Fan Coil - Pavimento 2",
        "categoria": "HVAC",
        "periodicidade_manutencao": "Mensal",
        "confianca": "media",
    }
    suggestion = _normalize_option(opt, "asset_unidentified")
    assert suggestion is not None
    assert suggestion.label == "Fan Coil - Pavimento 2"
    assert suggestion.confidence == "media"


def test_normalize_option_returns_none_when_no_label():
    opt = {"justificativa": "sem código", "confianca": "baixa"}
    assert _normalize_option(opt, "classification_missing") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_prompt_templates.py::test_normalize_option_classification_missing tests/test_prompt_templates.py::test_normalize_option_asset_unidentified tests/test_prompt_templates.py::test_normalize_option_returns_none_when_no_label -v
```

Expected: `FAILED` — `_normalize_option` returns `None` for `classification_missing` (no `codigo` branch) and `asset_unidentified` (no `nome_ativo` branch).

- [ ] **Step 3: Update `_normalize_option` in `prompt_templates.py`**

Replace the `elif issue_type == "system_unclassified":` block and add the two new branches. Full updated function:

```python
def _normalize_option(opt: dict, issue_type: str) -> Suggestion | None:
    """Converte um item de 'opcoes' do JSON do LLM em Suggestion.

    Retorna None se o item não tiver label válido.
    """
    justification = opt.get("justificativa", "")
    confidence_raw = opt.get("confianca", "baixa")
    confidence = confidence_raw if confidence_raw in _VALID_CONFIDENCES else "baixa"
    normative_ref: str | None = opt.get("ref")

    if issue_type in ("space_unnamed",):
        label = opt.get("nome", "")
        value: Any = label
    elif issue_type == "system_unclassified":
        label = opt.get("sistema", "")
        value = label
    elif issue_type == "classification_missing":
        label = opt.get("codigo", "")
        value = label
    elif issue_type == "asset_unidentified":
        label = opt.get("nome_ativo", "")
        value = label
    else:
        raw_val = opt.get("valor", "")
        label = str(raw_val) if raw_val != "" else ""
        value = raw_val

    if not label:
        return None

    return Suggestion(
        label=label,
        value=value,
        justification=justification,
        confidence=confidence,
        normative_ref=normative_ref,
        source="llm",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_prompt_templates.py -v
```

Expected: all previously passing tests still pass, new tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/suggestion_engine/prompt_templates.py tests/test_prompt_templates.py
git commit -m "feat(templates): extend _normalize_option for classification_missing and asset_unidentified"
```

---

## Task 3: Update `build_prompt` to accept `profile_id`

**Files:**
- Modify: `src/suggestion_engine/prompt_templates.py` (functions `_select_profile_template` new, `build_prompt` signature update, lines 276–317)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_prompt_templates.py`:

```python
from src.models import Issue
from src.suggestion_engine.prompt_templates import build_prompt, SYSTEM_PROMPT


def _make_issue(issue_type: str, context: dict) -> Issue:
    return Issue(
        element_guid="A" * 22,
        element_class="IfcWall",
        element_name="Parede 01",
        issue_type=issue_type,
        severity="medium",
        description="teste",
        context=context,
    )


def test_profile_template_budget_quantity():
    issue = _make_issue(
        "quantity_missing",
        {
            "geometry_data": "comprimento=5.0m, altura=2.8m",
            "material": "Concreto C25",
            "thickness": "0.20",
            "quantity_name": "NetVolume",
        },
    )
    sys_p, user_p = build_prompt(
        issue,
        {"building_type": "Comercial", "bioclimatic_zone": "4"},
        profile_id="budget_readiness",
    )
    assert sys_p == SYSTEM_PROMPT
    assert "orçamentista" in user_p
    assert "NetVolume" in user_p
    assert "Concreto C25" in user_p
    assert "{" not in user_p.replace("{{", "").replace("}}", "")


def test_profile_template_energy_thermal():
    issue = Issue(
        element_guid="B" * 22,
        element_class="IfcWall",
        element_name="Parede Externa",
        issue_type="thermal_incomplete",
        severity="high",
        description="ThermalTransmittance ausente",
        context={
            "zone": "3",
            "property_name": "ThermalTransmittance",
            "material": "Bloco cerâmico",
            "thickness": "0.14",
            "layers": "reboco 1.5cm + bloco 11cm + reboco 1.5cm",
            "is_external": True,
        },
    )
    sys_p, user_p = build_prompt(
        issue,
        {"building_type": "Residencial", "bioclimatic_zone": "3"},
        profile_id="energy_readiness",
    )
    assert "NBR 15575" in user_p
    assert "ThermalTransmittance" in user_p
    assert "{" not in user_p.replace("{{", "").replace("}}", "")


def test_profile_template_fm_space():
    issue = Issue(
        element_guid="C" * 22,
        element_class="IfcSpace",
        element_name="Room",
        issue_type="space_unnamed",
        severity="low",
        description="Espaço sem nome funcional",
        context={
            "area_m2": 12.0,
            "contained_elements": ["Fan Coil", "Quadro elétrico"],
            "assets": "Fan Coil, Quadro elétrico",
            "floor": "Pavimento 3",
            "adjacent_spaces": [],
        },
    )
    sys_p, user_p = build_prompt(
        issue,
        {"building_type": "Comercial", "bioclimatic_zone": "4"},
        profile_id="fm_readiness",
    )
    assert "facilities" in user_p
    assert "Fan Coil" in user_p
    assert "{" not in user_p.replace("{{", "").replace("}}", "")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_prompt_templates.py::test_profile_template_budget_quantity tests/test_prompt_templates.py::test_profile_template_energy_thermal tests/test_prompt_templates.py::test_profile_template_fm_space -v
```

Expected: `TypeError` — `build_prompt` does not accept `profile_id`.

- [ ] **Step 3: Add `_select_profile_template` and update `build_prompt`**

Add before `build_prompt`:

```python
def _select_profile_template(profile_id: str, issue: Issue) -> str | None:
    """Retorna o template de perfil para (profile_id, issue_type) ou None se não existir."""
    return PROFILE_TEMPLATES.get((profile_id, issue.issue_type))
```

Update `build_prompt` signature and first lines:

```python
def build_prompt(
    issue: Issue,
    building_context: dict,
    profile_id: str | None = None,
) -> tuple[str, str]:
    """Monta o prompt completo para uma issue.

    Retorna (system_prompt, user_prompt).

    Se profile_id for fornecido, tenta selecionar um template de perfil em
    PROFILE_TEMPLATES antes de cair no caminho genérico de _select_template.
    Preenche os placeholders com issue.context e building_context, e
    formata listas de elementos como texto legível.
    """
    if profile_id is not None:
        template = _select_profile_template(profile_id, issue) or _select_template(issue)
    else:
        template = _select_template(issue)
    # ... rest of function unchanged from here ...
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_prompt_templates.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 5: Verify no regressions in existing suggestion tests**

```bash
pytest tests/test_suggestion.py -v
```

Expected: all existing tests `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add src/suggestion_engine/prompt_templates.py tests/test_prompt_templates.py
git commit -m "feat(templates): wire profile_id into build_prompt via PROFILE_TEMPLATES lookup"
```

---

## Task 4: Add `test_all_profile_templates_have_no_unresolved_placeholders`

**Files:**
- Modify: `tests/test_prompt_templates.py`

This test renders each profile template with a maximally-populated context and asserts no `{placeholder}` strings survive. It uses `defaultdict(lambda: "N/D")` (the same strategy as `build_prompt`) so missing keys fall back to `"N/D"` without raising.

- [ ] **Step 1: Write the test**

Add to `tests/test_prompt_templates.py`:

```python
import re
from collections import defaultdict

from src.suggestion_engine.prompt_templates import PROFILE_TEMPLATES

_FULL_CONTEXT: dict = {
    # generic build_prompt fields
    "element_class": "IfcWall",
    "guid": "AAAAAAAA",
    "element_name": "Parede 01",
    "current_name": "Room",
    "building_type": "Residencial",
    "bioclimatic_zone": "3",
    # budget_readiness / quantity_missing
    "geometry_data": "comprimento=5m, altura=2.8m",
    "material": "Bloco cerâmico",
    "thickness": "0.14",
    "quantity_name": "NetVolume",
    # budget_readiness / classification_missing
    "layers": "reboco + bloco + reboco",
    # energy_readiness / thermal_incomplete
    "zone": "3",
    "property_name": "ThermalTransmittance",
    "is_external": "True",
    # energy_readiness / space_unnamed + fm_readiness / space_unnamed
    "area_m2": "12.0",
    "contained_elements": "IfcDoor, IfcFurnishingElement",
    "adjacent_spaces": "Corredor",
    "external_wall_count": "2",
    "has_external_window": "True",
    "assets": "Fan Coil, Quadro elétrico",
    "floor": "Pavimento 1",
    # fm_readiness / asset_unidentified
    "predefined_type": "FANCOIL",
    "containing_space": "Sala de TI",
    "name": "Equipamento Genérico",
}

_PLACEHOLDER_RE = re.compile(r'\{[a-zA-Z_][a-zA-Z0-9_]*\}')


def test_all_profile_templates_have_no_unresolved_placeholders():
    safe_ctx: defaultdict = defaultdict(lambda: "N/D", _FULL_CONTEXT)
    for key, template in PROFILE_TEMPLATES.items():
        rendered = template.format_map(safe_ctx)
        unresolved = _PLACEHOLDER_RE.findall(rendered)
        assert not unresolved, (
            f"Template {key} tem placeholders não resolvidos: {unresolved}\n"
            f"Rendered:\n{rendered}"
        )
```

- [ ] **Step 2: Run test to verify it passes (or fix templates)**

```bash
pytest tests/test_prompt_templates.py::test_all_profile_templates_have_no_unresolved_placeholders -v
```

Expected: `PASSED`. If it fails, the error message shows which template and which placeholder is unresolved — fix either the template string or add the key to `_FULL_CONTEXT`.

- [ ] **Step 3: Run full test suite to confirm no regressions**

```bash
pytest tests/ -v
```

Expected: all tests `PASSED`.

- [ ] **Step 4: Commit**

```bash
git add tests/test_prompt_templates.py
git commit -m "test(templates): verify all profile templates resolve all placeholders"
```

---

## Self-Review

**Spec coverage:**
- ✅ `PROFILE_TEMPLATES` with 6 entries keyed by `(profile_id, issue_type)` — Task 1
- ✅ `("budget_readiness", "quantity_missing")` — Task 1
- ✅ `("budget_readiness", "classification_missing")` — Task 1
- ✅ `("energy_readiness", "thermal_incomplete")` — Task 1
- ✅ `("energy_readiness", "space_unnamed")` — Task 1
- ✅ `("fm_readiness", "space_unnamed")` — Task 1
- ✅ `("fm_readiness", "asset_unidentified")` — Task 1
- ✅ `_normalize_option` handles `codigo` and `nome_ativo` — Task 2
- ✅ `build_prompt` accepts `profile_id` — Task 3
- ✅ `test_profile_template_budget_quantity` — Task 3
- ✅ `test_profile_template_energy_thermal` — Task 3
- ✅ `test_profile_template_fm_space` — Task 3
- ✅ `test_all_profile_templates_have_no_unresolved_placeholders` — Task 4

**Placeholder scan:** No "TBD", "TODO", or vague steps. All code blocks are complete.

**Type consistency:**
- `build_prompt` returns `tuple[str, str]` throughout — unchanged.
- `_normalize_option` returns `Suggestion | None` — unchanged.
- `PROFILE_TEMPLATES` is `dict[tuple[str, str], str]` — consistent with dict literal.
- `_select_profile_template` returns `str | None` — matches `.get()` return type.
