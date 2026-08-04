"""Condição v7 declarada: evidência fica, procedimento sai (2026-08-04).

A matriz v6 (`docs/resultado-matriz-v6-2026-08-03.md`) atribuiu por estrato os
efeitos das três mudanças que o v6 fez no mesmo commit:

| estrato | o que o v6 mudou | efeito médio |
|---|---|---|
| Category | LongName chega ao prompt (**evidência**) | **+31,2 pp** |
| FireRating | PROCEDIMENTO TRRF → letra → hipóteses (**instrução**) | **−12,5 pp** |
| ThermalTransmittance | memória de cálculo obrigatória (**instrução**) | **−8,4 pp** |

O v7 mantém a evidência e desfaz os dois blocos de procedimento — no térmico,
substituindo "calcule e devolva o número" por "declare os termos; o sistema
calcula" (`src/suggestion_engine/thermal_recompute.py`).

Estes testes travam a fronteira da condição para que ela não se desfaça por
edição acidental, e existem porque a lição metodológica do projeto é que
mudanças de instrumento precisam ser **declaradas e isoladas**.
"""

from __future__ import annotations

from src.suggestion_engine.prompt_templates import PROMPT_VERSION, TEMPLATES


def test_prompt_version_is_v7_2():
    """v7.2: v7.1 + restrição de fogo desambiguada."""
    assert PROMPT_VERSION == "v7.2"


# ---------------------------------------------------------------------------
# Fogo: o bloco de procedimento sai; critérios e evidência ficam
# ---------------------------------------------------------------------------


def test_fire_template_has_no_procedure_block():
    """O bloco PROCEDIMENTO (TRRF → letra → hipóteses) custou −12,5 pp."""
    fire = TEMPLATES["pset_missing_fire"]

    assert "PROCEDIMENTO:" not in fire
    assert "TRRF" not in fire


def test_fire_template_keeps_criteria_and_evidence():
    """O que sai é o procedimento, não os critérios nem a evidência do arquivo."""
    fire = TEMPLATES["pset_missing_fire"]

    assert "NBR 14432" in fire
    assert "REI" in fire
    assert "EI" in fire
    assert "{load_bearing}" in fire
    assert "{material_layers}" in fire
    # A leitura de que a flag é indício, não veredito, é evidência interpretada
    # do arquivo e já existia no v5.
    assert "indício, não veredito" in fire


# ---------------------------------------------------------------------------
# Térmico: a cobrança de aritmética sai; a estrutura entra
# ---------------------------------------------------------------------------


def test_thermal_templates_do_not_demand_the_arithmetic():
    """A "VERIFICAÇÃO OBRIGATÓRIA" pedia a conta ao LLM e custou −8,4 pp."""
    for chave in ("pset_missing_thermal", "pset_missing_u_value_slab"):
        template = TEMPLATES[chave]
        assert "VERIFICAÇÃO OBRIGATÓRIA" not in template, chave
        assert "o campo valor é exatamente" not in template, chave


def test_thermal_templates_request_structured_memory():
    """O contrato v7 pede a estrutura; a soma é feita por código."""
    for chave in ("pset_missing_thermal", "pset_missing_u_value_slab"):
        template = TEMPLATES[chave]
        assert "memoria_calculo" in template, chave
        assert "espessura_m" in template, chave
        assert "lambda" in template, chave


def test_thermal_templates_keep_the_lambda_table_and_method():
    """O conhecimento normativo (λ, Rsi/Rse, câmara de ar) permanece."""
    thermal = TEMPLATES["pset_missing_thermal"]

    assert "NBR 15220-2" in thermal
    assert "concreto 1,75" in thermal
    assert "CÂMARA DE AR" in thermal


def test_category_template_keeps_the_evidence_that_paid_off():
    """LongName no Category valeu +31,2 pp — é o que o v7 preserva."""
    category = TEMPLATES["pset_missing_space_category"]

    assert "{long_name}" in category
    assert "EVIDÊNCIA PRIMÁRIA" in category


# ---------------------------------------------------------------------------
# Contrato de saída: o pedido da memória não pode ser desfeito no fim do prompt
# ---------------------------------------------------------------------------


def test_output_contract_asks_for_the_memory_when_requested():
    """O contrato genérico é anexado DEPOIS do template e é o que o LLM lê por
    último: sem citar memoria_calculo ali, o campo tende a não voltar."""
    from src.suggestion_engine.prompt_templates import output_contract_for

    contrato = output_contract_for("pset_missing", include_calc_memory=True)

    assert "memoria_calculo" in contrato


def test_output_contract_unchanged_by_default():
    """A condição v7 é escopada: nenhum outro estrato vê o campo de memória."""
    from src.suggestion_engine.prompt_templates import output_contract_for

    assert "memoria_calculo" not in output_contract_for("pset_missing")
    assert "memoria_calculo" not in output_contract_for("space_unnamed")


def test_window_thermal_task_does_not_get_the_memory_contract():
    """Esquadria calcula U por valor de REFERÊNCIA, não somando camadas.

    Pedir memória ali alargaria a condição v7 para uma tarefa que ela não mira
    — e que no run v6 já acertava dentro de 3,5%.
    """
    from src.models import Issue
    from src.suggestion_engine.prompt_templates import uses_layered_thermal_template

    janela = Issue(
        element_guid="J" * 22,
        element_class="IfcWindow",
        element_name="Janela 120x100",
        issue_type="pset_missing",
        severity="high",
        description="ThermalTransmittance ausente",
        context={"check_pset": "Pset_WindowCommon", "check_property": "ThermalTransmittance"},
    )
    laje = Issue(
        element_guid="S" * 22,
        element_class="IfcSlab",
        element_name="Laje",
        issue_type="pset_missing",
        severity="high",
        description="ThermalTransmittance ausente",
        context={"check_pset": "Pset_SlabCommon", "check_property": "ThermalTransmittance"},
    )

    assert uses_layered_thermal_template(janela) is False
    assert uses_layered_thermal_template(laje) is True


def test_rendered_thermal_prompt_carries_the_memory_contract_to_the_end():
    """Prompt completo (template rico + contrato): o pedido sobrevive até o fim."""
    from src.models import Issue
    from src.suggestion_engine.prompt_templates import build_prompt

    issue = Issue(
        element_guid="S" * 22,
        element_class="IfcSlab",
        element_name="Laje 15cm",
        issue_type="pset_missing",
        severity="high",
        description="ThermalTransmittance ausente",
        context={
            "check_pset": "Pset_SlabCommon",
            "check_property": "ThermalTransmittance",
            "materials": [{"name": "concreto", "thickness": 0.10}],
        },
    )

    _, user = build_prompt(issue, {"building_type": "Residencial", "bioclimatic_zone": "3"})

    cauda = user.split("REGRAS DE SAIDA:")
    assert len(cauda) == 2, "o bloco de regras tem de existir e ser único"
    assert "memoria_calculo" in cauda[-1]


# ---------------------------------------------------------------------------
# Fogo: a restrição de formato não pode induzir classe de uma letra
# ---------------------------------------------------------------------------


def test_fire_restriction_enumerates_valid_class_combinations():
    """Medido no smoke do v7.1: "letras R/E/I seguidas do tempo" foi lido como
    "escolha UMA destas" e o gemma2 colapsou em `E 30`/`E 60` — classe de uma
    letra, que nunca é aceita. A ambiguidade sempre existiu; estava mascarada
    pelo ruído do schema duplicado, e o P0 a destapou.

    Correção de FORMATO (não de raciocínio): enunciar as combinações válidas.
    """
    fire = TEMPLATES["pset_missing_fire"]

    assert "R/E/I" not in fire, "listar com barras convida a escolher uma letra"
    for classe in ("REI", "EI", "RE"):
        assert classe in fire, classe
    assert "JUNTAS" in fire


def test_fire_template_does_not_gain_reasoning_guidance():
    """A correção é de formato: o raciocínio continua só no bloco CRITÉRIOS.

    Sem esta trava, "desambiguar o formato" vira porta de entrada para
    procedimento — exatamente o que o v7 removeu por custar −12,5 pp.
    """
    fire = TEMPLATES["pset_missing_fire"]

    assert "PROCEDIMENTO" not in fire
    assert "TRRF" not in fire
    assert "Tab. A.1" not in fire
