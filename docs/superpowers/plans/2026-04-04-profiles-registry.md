# Profiles Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar `src/profiles/registry.py` com `create_default_registry()` e `load_custom_profile_from_ids()`, mais `tests/test_profiles.py` com 4 testes.

**Architecture:** `create_default_registry()` instancia os 4 perfis padrão hard-coded. `load_custom_profile_from_ids()` delega para `parse_ids()` (já existente em `src/translator/ids_parser.py`) e usa lookup tables para inferir `issue_types` e `required_extractors` a partir das `IDSSpecification` retornadas. Perfis custom têm `ids_filename=None` → `is_custom == True`.

**Tech Stack:** Python 3.11+, Pydantic v2, `lxml` (via `parse_ids`), pytest

---

## Arquivos

- Criar: `src/profiles/__init__.py` — módulo vazio
- Criar: `src/profiles/registry.py` — `create_default_registry` + `load_custom_profile_from_ids`
- Criar: `tests/test_profiles.py` — 4 testes

---

### Task 1: Escrever os 4 testes (TDD — falham antes da implementação)

**Files:**
- Create: `tests/test_profiles.py`

- [ ] **Step 1: Criar `tests/test_profiles.py`**

```python
"""Testes para src/profiles/registry.py."""

from pathlib import Path

import pytest

from src.profiles.registry import create_default_registry, load_custom_profile_from_ids

IDS_PATH = str(Path(__file__).parent.parent / "data" / "ids_templates" / "residencial_nbr15575.ids")


class TestDefaultRegistry:
    def test_default_registry_has_4_profiles(self):
        """create_default_registry deve retornar registro com exatamente 4 perfis."""
        registry = create_default_registry()

        assert len(registry.list_profiles()) == 4

    def test_default_registry_get_budget(self):
        """Perfil budget_readiness deve estar registrado com nome correto."""
        registry = create_default_registry()

        profile = registry.get("budget_readiness")

        assert profile is not None
        assert profile.id == "budget_readiness"
        assert profile.name == "Orçamento-readiness"
        assert "quantities" in profile.required_extractors
        assert "pset_missing" in profile.issue_types
        assert profile.blocking_severities == ["high"]
        assert profile.is_custom is False  # ids_filename definido


class TestLoadCustomProfile:
    def test_load_custom_profile_from_ids(self):
        """Deve criar ReadinessProfile a partir do IDS residencial_nbr15575.ids."""
        profile = load_custom_profile_from_ids(IDS_PATH)

        assert profile.id == "residencial_nbr15575"
        assert profile.name == "residencial_nbr15575"
        assert "pset_missing" in profile.issue_types
        assert "space_unnamed" in profile.issue_types
        assert "quantities" in profile.required_extractors
        assert "materials" in profile.required_extractors
        assert "spaces" in profile.required_extractors
        assert "thermal" in profile.required_extractors

    def test_load_custom_profile_accepts_custom_name(self):
        """profile_name fornecido deve sobrescrever o nome inferido do filename."""
        profile = load_custom_profile_from_ids(IDS_PATH, profile_name="Meu Perfil Custom")

        assert profile.name == "Meu Perfil Custom"
        assert profile.id == "residencial_nbr15575"  # id vem sempre do filename

    def test_custom_profile_is_custom_true(self):
        """Perfil carregado de IDS externo deve ter is_custom == True."""
        profile = load_custom_profile_from_ids(IDS_PATH)

        assert profile.ids_filename is None
        assert profile.is_custom is True
```

- [ ] **Step 2: Rodar para confirmar falha com ImportError**

```
pytest tests/test_profiles.py -v
```

Expected: `ERROR` com `ModuleNotFoundError: No module named 'src.profiles'`

---

### Task 2: Criar `src/profiles/__init__.py` e `src/profiles/registry.py`

**Files:**
- Create: `src/profiles/__init__.py`
- Create: `src/profiles/registry.py`

- [ ] **Step 3: Criar `src/profiles/__init__.py` (vazio)**

```python
```

(arquivo vazio — apenas torna `src/profiles` um pacote Python)

- [ ] **Step 4: Criar `src/profiles/registry.py`**

```python
"""Registro de perfis de readiness e carregamento de perfis customizados via IDS."""

from pathlib import Path

from src.models import ProfileRegistry, ReadinessProfile
from src.translator.ids_parser import parse_ids

# ---------------------------------------------------------------------------
# Lookup tables para inferência de issue_types e extractors
# ---------------------------------------------------------------------------

_ENTITY_TO_EXTRACTORS: dict[str, list[str]] = {
    "IFCWALL": ["quantities", "materials"],
    "IFCSLAB": ["quantities", "materials"],
    "IFCSPACE": ["spaces"],
    "IFCDOOR": ["quantities"],
    "IFCWINDOW": ["quantities"],
}

_THERMAL_PROPS: set[str] = {"ThermalTransmittance", "ThermalConductivity", "HeatCapacity"}

_SPACE_NAME_PROPS: set[str] = {"LongName", "Name"}


def _infer_issue_type(req: dict[str, str]) -> str:
    """Infere o issue_type a partir de um requirement de IDSSpecification."""
    pset = req.get("pset", "")
    prop = req.get("prop", "")
    if pset == "IFC_RELATION":
        return "relation_broken"
    if pset == "" and prop in _SPACE_NAME_PROPS:
        return "space_unnamed"
    return "pset_missing"


def _infer_extractors(entity: str, requirements: list[dict[str, str]]) -> list[str]:
    """Infere os extractors necessários a partir da entidade e dos requirements."""
    extractors: list[str] = list(_ENTITY_TO_EXTRACTORS.get(entity, []))
    for req in requirements:
        if req.get("prop") in _THERMAL_PROPS and "thermal" not in extractors:
            extractors.append("thermal")
        if req.get("pset") == "IFC_RELATION" and "relations" not in extractors:
            extractors.append("relations")
    return extractors


# ---------------------------------------------------------------------------
# Perfis padrão
# ---------------------------------------------------------------------------

def create_default_registry() -> ProfileRegistry:
    """Cria registro com os 4 perfis padrão do sistema."""
    registry = ProfileRegistry()

    registry.register(ReadinessProfile(
        id="budget_readiness",
        name="Orçamento-readiness",
        description="Verifica se o modelo possui informação mínima para levantamento quantitativo e vinculação orçamentária.",
        ids_filename="budget_readiness.ids",
        required_extractors=["quantities", "materials", "classifications"],
        rule_pack="budget_rules",
        prompt_pack="budget_prompts",
        issue_types=["pset_missing", "system_unclassified", "quantity_missing", "classification_missing"],
        blocking_severities=["high"],
    ))

    registry.register(ReadinessProfile(
        id="energy_readiness",
        name="Energy/HVAC-readiness",
        description="Verifica se o IFC está apto para simulação energética e verificações de envoltória.",
        ids_filename="energy_readiness.ids",
        required_extractors=["thermal", "materials", "spaces", "external_elements"],
        rule_pack="energy_rules",
        prompt_pack="energy_prompts",
        issue_types=["pset_missing", "space_unnamed", "relation_broken"],
        blocking_severities=["high"],
    ))

    registry.register(ReadinessProfile(
        id="fm_readiness",
        name="Facility Management-readiness",
        description="Verifica se o modelo pode sustentar operação e manutenção do edifício.",
        ids_filename="fm_readiness.ids",
        required_extractors=["spaces", "assets", "locations"],
        rule_pack="fm_rules",
        prompt_pack="fm_prompts",
        issue_types=["space_unnamed", "asset_unidentified", "location_missing"],
        blocking_severities=["high", "medium"],
    ))

    registry.register(ReadinessProfile(
        id="compliance_readiness",
        name="Code-compliance readiness",
        description="Verifica se o IFC contém os dados mínimos para checagem normativa posterior (NBR 15575).",
        ids_filename="compliance_readiness.ids",
        required_extractors=["thermal", "materials", "spaces", "relations"],
        rule_pack="compliance_rules",
        prompt_pack="compliance_prompts",
        issue_types=["pset_missing", "space_unnamed", "relation_broken", "system_unclassified"],
        blocking_severities=["high"],
    ))

    return registry


# ---------------------------------------------------------------------------
# Carregamento de perfil customizado via IDS
# ---------------------------------------------------------------------------

def load_custom_profile_from_ids(ids_path: str, profile_name: str | None = None) -> ReadinessProfile:
    """Cria um ReadinessProfile a partir de um arquivo IDS uploadado pelo usuário.

    Parseia o IDS para extrair specs, infere issue_types e extractors necessários
    a partir das specs usando lookup tables, e gera um profile_id baseado no filename.
    Se profile_name não fornecido, usa o filename sem extensão.
    """
    specs = parse_ids(ids_path)
    stem = Path(ids_path).stem

    issue_types: list[str] = []
    required_extractors: list[str] = []

    for spec in specs:
        for ext in _infer_extractors(spec.applicability_entity, spec.requirements):
            if ext not in required_extractors:
                required_extractors.append(ext)
        for req in spec.requirements:
            issue_type = _infer_issue_type(req)
            if issue_type not in issue_types:
                issue_types.append(issue_type)

    return ReadinessProfile(
        id=stem,
        name=profile_name or stem,
        description=f"Perfil gerado a partir de {Path(ids_path).name}.",
        ids_filename=None,
        required_extractors=required_extractors,
        issue_types=issue_types,
        blocking_severities=["high"],
    )
```

- [ ] **Step 5: Rodar os 4 testes para confirmar que passam**

```
pytest tests/test_profiles.py -v
```

Expected:
```
tests/test_profiles.py::TestDefaultRegistry::test_default_registry_has_4_profiles PASSED
tests/test_profiles.py::TestDefaultRegistry::test_default_registry_get_budget PASSED
tests/test_profiles.py::TestLoadCustomProfile::test_load_custom_profile_from_ids PASSED
tests/test_profiles.py::TestLoadCustomProfile::test_load_custom_profile_accepts_custom_name PASSED
tests/test_profiles.py::TestLoadCustomProfile::test_custom_profile_is_custom_true PASSED
```

- [ ] **Step 6: Rodar suite completa para confirmar sem regressões**

```
pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: todos os testes anteriores ainda PASS.

- [ ] **Step 7: Commit**

```bash
git add src/profiles/__init__.py src/profiles/registry.py tests/test_profiles.py
git commit -m "feat(profiles): cria módulo profiles com registry padrão e load_custom_profile_from_ids"
```

---

## Verificação

```
pytest tests/test_profiles.py -v
```

Confirmar que os 5 testes aparecem no output (4 especificados + 1 extra `test_load_custom_profile_accepts_custom_name` que garante o `profile_name` opcional):
- `TestDefaultRegistry::test_default_registry_has_4_profiles`
- `TestDefaultRegistry::test_default_registry_get_budget`
- `TestLoadCustomProfile::test_load_custom_profile_from_ids`
- `TestLoadCustomProfile::test_load_custom_profile_accepts_custom_name`
- `TestLoadCustomProfile::test_custom_profile_is_custom_true`
