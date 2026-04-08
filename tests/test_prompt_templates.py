"""Testes para prompt_templates — templates de prompt e parser de resposta LLM."""

import re

import pytest

from src.models import Issue, Suggestion
from collections import defaultdict

from src.suggestion_engine.prompt_templates import (
    PROFILE_TEMPLATES,
    SYSTEM_PROMPT,
    TEMPLATES,
    _normalize_option,
    build_prompt,
    parse_llm_response,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BUILDING_CTX = {
    "building_type": "Residencial unifamiliar",
    "bioclimatic_zone": "3",
}


def _space_issue(**ctx_overrides) -> Issue:
    ctx = {
        "area_m2": 4.2,
        "height_m": 2.6,
        "contained_elements": ["IfcDoor", "IfcSanitaryTerminal"],
        "adjacent_spaces": ["Corredor"],
        "floor": "Pavimento 1",
        **ctx_overrides,
    }
    return Issue(
        element_guid="S" * 22,
        element_class="IfcSpace",
        element_name="Room 1",
        issue_type="space_unnamed",
        severity="low",
        description="Espaço sem classificação funcional",
        context=ctx,
    )


def _pset_issue(check_property: str = "ThermalTransmittance", **ctx_overrides) -> Issue:
    ctx = {
        "check_property": check_property,
        "material_name": "Bloco cerâmico 14cm",
        "thickness_m": 0.14,
        "has_plaster": True,
        "is_structural": False,
        **ctx_overrides,
    }
    return Issue(
        element_guid="W" * 22,
        element_class="IfcWall",
        element_name="Wall 1",
        issue_type="pset_missing",
        severity="high",
        description=f"Propriedade {check_property} ausente",
        context=ctx,
    )


# ---------------------------------------------------------------------------
# TEMPLATES dict
# ---------------------------------------------------------------------------

def test_templates_has_all_required_keys():
    """TEMPLATES contém todas as chaves esperadas."""
    required = {
        "space_unnamed",
        "pset_missing_thermal",
        "pset_missing_fire",
        "pset_missing_generic",
        "system_unclassified",
    }
    assert required.issubset(TEMPLATES.keys())


# ---------------------------------------------------------------------------
# build_prompt — space_unnamed
# ---------------------------------------------------------------------------

def test_build_prompt_space_unnamed():
    """build_prompt para space_unnamed retorna SYSTEM_PROMPT e user_prompt com dados do contexto."""
    issue = _space_issue()
    system, user = build_prompt(issue, _BUILDING_CTX)

    assert system == SYSTEM_PROMPT
    assert "Residencial unifamiliar" in user
    assert "4.2" in user
    assert "IfcDoor" in user
    assert "Corredor" in user
    assert "Pavimento 1" in user


def test_build_prompt_space_unnamed_current_name_filled():
    """build_prompt preenche current_name com element_name do issue."""
    issue = _space_issue()
    _, user = build_prompt(issue, _BUILDING_CTX)

    assert "Room 1" in user


# ---------------------------------------------------------------------------
# build_prompt — pset_missing sub-tipos
# ---------------------------------------------------------------------------

def test_build_prompt_pset_thermal():
    """build_prompt seleciona template térmico para ThermalTransmittance."""
    issue = _pset_issue("ThermalTransmittance")
    _, user = build_prompt(issue, _BUILDING_CTX)

    assert "ThermalTransmittance" in user
    assert "NBR 15575-4" in user
    assert "Bloco cerâmico 14cm" in user


def test_build_prompt_pset_fire():
    """build_prompt seleciona template de incêndio para FireRating."""
    issue = _pset_issue("FireRating")
    _, user = build_prompt(issue, _BUILDING_CTX)

    assert "FireRating" in user


def test_build_prompt_pset_generic():
    """build_prompt seleciona template genérico para propriedades não especializadas."""
    issue = _pset_issue("IsExternal")
    _, user = build_prompt(issue, _BUILDING_CTX)

    assert "IsExternal" in user


# ---------------------------------------------------------------------------
# build_prompt — sem placeholders literais no output
# ---------------------------------------------------------------------------

def test_build_prompt_fills_all_placeholders():
    """Nenhum placeholder {palavra} permanece literal no user_prompt final."""
    issue = _space_issue()
    _, user = build_prompt(issue, _BUILDING_CTX)

    # Chaves literais restantes seriam algo como {alguma_palavra}
    leftovers = re.findall(r'\{[a-z_]+\}', user)
    assert leftovers == [], f"Placeholders não preenchidos: {leftovers}"


def test_build_prompt_missing_context_key_uses_default():
    """Placeholder sem chave correspondente no contexto usa 'N/D' (sem exceção)."""
    issue = Issue(
        element_guid="X" * 22,
        element_class="IfcSpace",
        element_name="Room 2",
        issue_type="space_unnamed",
        severity="low",
        description="...",
        context={},  # contexto vazio — todos os campos específicos estarão ausentes
    )
    # Não deve lançar KeyError
    system, user = build_prompt(issue, _BUILDING_CTX)
    assert system == SYSTEM_PROMPT
    assert "N/D" in user


# ---------------------------------------------------------------------------
# parse_llm_response — JSON válido direto
# ---------------------------------------------------------------------------

def test_parse_llm_response_valid_json():
    """parse_llm_response parseia JSON limpo e retorna lista de Suggestions."""
    raw = (
        '{"opcoes": ['
        '{"nome": "Sala de Estar", "justificativa": "25m² sem WC", "confianca": "alta"},'
        '{"nome": "Escritório", "justificativa": "mesa e cadeira presentes", "confianca": "media"}'
        "]}"
    )
    suggestions = parse_llm_response(raw, "space_unnamed")

    assert len(suggestions) == 2
    assert all(isinstance(s, Suggestion) for s in suggestions)
    assert suggestions[0].label == "Sala de Estar"
    assert suggestions[0].confidence == "alta"
    assert suggestions[0].source == "llm"
    assert suggestions[1].label == "Escritório"
    assert suggestions[1].confidence == "media"


def test_parse_llm_response_pset_thermal_returns_float_value():
    """parse_llm_response para pset_missing_thermal retorna valor numérico como label/value."""
    raw = (
        '{"opcoes": ['
        '{"valor": 2.48, "justificativa": "bloco 14cm", "ref": "NBR 15575-4 Tab. C.2", "confianca": "alta"}'
        "]}"
    )
    suggestions = parse_llm_response(raw, "pset_missing")

    assert len(suggestions) == 1
    assert suggestions[0].label == "2.48"
    assert suggestions[0].normative_ref == "NBR 15575-4 Tab. C.2"
    assert suggestions[0].source == "llm"


# ---------------------------------------------------------------------------
# parse_llm_response — markdown wrapper
# ---------------------------------------------------------------------------

def test_parse_llm_response_with_markdown_wrapper():
    """parse_llm_response extrai JSON de dentro de bloco markdown ```json...```."""
    raw = (
        "```json\n"
        '{"opcoes": [{"nome": "Banheiro", "justificativa": "WC presente", "confianca": "alta"}]}'
        "\n```"
    )
    suggestions = parse_llm_response(raw, "space_unnamed")

    assert len(suggestions) == 1
    assert suggestions[0].label == "Banheiro"
    assert suggestions[0].source == "llm"


def test_parse_llm_response_with_text_before_json():
    """parse_llm_response ignora texto antes do JSON e extrai o objeto."""
    raw = (
        "Aqui está minha resposta:\n"
        '{"opcoes": [{"nome": "Lavabo", "justificativa": "pequeno WC", "confianca": "media"}]}'
    )
    suggestions = parse_llm_response(raw, "space_unnamed")

    assert len(suggestions) == 1
    assert suggestions[0].label == "Lavabo"


# ---------------------------------------------------------------------------
# parse_llm_response — inválido
# ---------------------------------------------------------------------------

def test_parse_llm_response_invalid_returns_empty():
    """parse_llm_response retorna lista vazia para string sem JSON válido."""
    suggestions = parse_llm_response("Não consigo processar isso.", "space_unnamed")
    assert suggestions == []


def test_parse_llm_response_empty_string_returns_empty():
    """parse_llm_response retorna lista vazia para string vazia."""
    suggestions = parse_llm_response("", "space_unnamed")
    assert suggestions == []


def test_parse_llm_response_invalid_confidence_defaults_to_baixa():
    """Confiança desconhecida no JSON é normalizada para 'baixa'."""
    raw = '{"opcoes": [{"nome": "Quarto", "justificativa": "cama presente", "confianca": "unknown"}]}'
    suggestions = parse_llm_response(raw, "space_unnamed")

    assert len(suggestions) == 1
    assert suggestions[0].confidence == "baixa"


def test_parse_llm_response_system_unclassified():
    """parse_llm_response para system_unclassified usa campo 'sistema' como label."""
    raw = (
        '{"opcoes": ['
        '{"sistema": "Alvenaria cerâmica", "justificativa": "bloco aparente", "confianca": "alta"}'
        "]}"
    )
    suggestions = parse_llm_response(raw, "system_unclassified")

    assert len(suggestions) == 1
    assert suggestions[0].label == "Alvenaria cerâmica"
    assert suggestions[0].value == "Alvenaria cerâmica"


# ---------------------------------------------------------------------------
# Task 1: PROFILE_TEMPLATES keys
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Task 2: _normalize_option — novos tipos
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Task 3: build_prompt com profile_id
# ---------------------------------------------------------------------------


def _make_profile_issue(issue_type: str, context: dict) -> Issue:
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
    issue = _make_profile_issue(
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
    assert not _PLACEHOLDER_RE.search(user_p)


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
    assert not _PLACEHOLDER_RE.search(user_p)


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
    assert not _PLACEHOLDER_RE.search(user_p)


# ---------------------------------------------------------------------------
# Task 4: sem placeholders não resolvidos em nenhum template de perfil
# ---------------------------------------------------------------------------

_FULL_PROFILE_CONTEXT: dict = {
    "element_class": "IfcWall",
    "guid": "AAAAAAAA",
    "element_name": "Parede 01",
    "current_name": "Room",
    "building_type": "Residencial",
    "bioclimatic_zone": "3",
    "geometry_data": "comprimento=5m, altura=2.8m",
    "material": "Bloco cerâmico",
    "thickness": "0.14",
    "quantity_name": "NetVolume",
    "layers": "reboco + bloco + reboco",
    "zone": "3",
    "property_name": "ThermalTransmittance",
    "is_external": "True",
    "area_m2": "12.0",
    "contained_elements": "IfcDoor, IfcFurnishingElement",
    "adjacent_spaces": "Corredor",
    "external_wall_count": "2",
    "has_external_window": "True",
    "assets": "Fan Coil, Quadro elétrico",
    "floor": "Pavimento 1",
    "predefined_type": "FANCOIL",
    "containing_space": "Sala de TI",
    "name": "Equipamento Genérico",
}

_PLACEHOLDER_RE = re.compile(r'\{[a-zA-Z_][a-zA-Z0-9_]*\}')


def test_all_profile_templates_have_no_unresolved_placeholders():
    safe_ctx: defaultdict = defaultdict(lambda: "N/D", _FULL_PROFILE_CONTEXT)
    for key, template in PROFILE_TEMPLATES.items():
        rendered = template.format_map(safe_ctx)
        unresolved = _PLACEHOLDER_RE.findall(rendered)
        assert not unresolved, (
            f"Template {key} tem placeholders não resolvidos: {unresolved}\n"
            f"Rendered:\n{rendered}"
        )
