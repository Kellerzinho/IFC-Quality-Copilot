"""Recomputação determinística de U a partir da memória de cálculo (v7).

Achado de 2026-08-02 (`docs/achado-aritmetica-termica-2026-08-02.md`): o modelo
identifica as camadas, recupera os λ corretos e monta o método certo — e então
erra a **adição**. Em 4 de 4 memórias parseáveis o valor devolvido era fielmente
`1/(a soma que o próprio modelo escreveu)`, e a soma estava errada. A conta é
trabalho de código, não de LLM.

As memórias usadas aqui são **verbatim** do log DEBUG do run
`estrato-v6-pset-gemma2` (gemma2:9b, prompt v6) — não são sintéticas.
"""

from __future__ import annotations

import pytest

from src.models import Issue, Suggestion
from src.suggestion_engine.thermal_recompute import (
    ThermalMemory,
    parse_calc_memory,
    recompute_thermal_suggestions,
)

# Memória real do estímulo da laje de 15 cm (107 issues), do log do run v6.
_MEMORIA_LAJE = (
    "R_total = 0.17 + (0.02/1.05) + (0.03/1.15) + (0.10/1.75) + 0.04 = 0.468, "
    "U = 1/0.468 = 2.14 W/(m²K)"
)
# Mesmo estímulo, resposta em que o modelo declarou outra soma errada.
_MEMORIA_LAJE_USINADA = (
    "R_total = 0.17 + (0.02/1.15) + (0.03/1.75) + (0.10/1.75) + (0.04) = 0.386; "
    "U = 1 / R_total = 2.59 W/(m²K)"
)


def _thermal_issue() -> Issue:
    return Issue(
        element_guid="S" * 22,
        element_class="IfcSlab",
        element_name="Laje 15cm",
        issue_type="pset_missing",
        severity="high",
        description="ThermalTransmittance ausente",
        context={"check_pset": "Pset_SlabCommon", "check_property": "ThermalTransmittance"},
    )


def _fire_issue() -> Issue:
    return Issue(
        element_guid="W" * 22,
        element_class="IfcWall",
        element_name="Parede",
        issue_type="pset_missing",
        severity="high",
        description="FireRating ausente",
        context={"check_pset": "Pset_WallCommon", "check_property": "FireRating"},
    )


def _sug(value, justification: str = "", **kwargs) -> Suggestion:
    return Suggestion(
        label=str(value),
        value=value,
        justification=justification,
        confidence="alta",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Parse da memória
# ---------------------------------------------------------------------------


def test_parse_recovers_terms_from_real_v6_memory():
    """Os termos escritos pelo modelo são a derivação correta do GT."""
    memory = parse_calc_memory(_MEMORIA_LAJE)

    assert isinstance(memory, ThermalMemory)
    assert memory.r_total == pytest.approx(0.312277, abs=1e-5)
    assert memory.u_value == pytest.approx(3.2023, abs=1e-3)
    assert memory.declared_r_total == pytest.approx(0.468, abs=1e-6)
    assert len(memory.terms) == 5


def test_parse_accepts_parenthesized_bare_term():
    """`(0.04)` entre parênteses é termo de resistência, não quociente."""
    memory = parse_calc_memory(_MEMORIA_LAJE_USINADA)

    assert memory is not None
    assert memory.r_total == pytest.approx(0.301677, abs=1e-5)
    assert memory.u_value == pytest.approx(3.3148, abs=1e-3)


def test_parse_returns_none_without_memory():
    """Justificativa retórica sem conta (o caso do drywall no v6) não parseia."""
    texto = (
        "Parede de drywall/steel frame com espessura total de 0,1 m e ausência de "
        "camada isolante. Considerando a norma NBR 15220-2 e o montante metálico "
        "como câmara de ar não ventilada (R ≈ 0,17 m²K/W), o valor U resultante é alto."
    )

    assert parse_calc_memory(texto) is None


def test_parse_rejects_absurd_total():
    """R_total fora de faixa física não vira recomputação."""
    assert parse_calc_memory("R_total = 0.0001 + 0.0001 = 0.0002") is None


def test_parse_accepts_comma_decimal():
    """O modelo às vezes responde em pt-BR com vírgula decimal."""
    memory = parse_calc_memory("R_total = 0,17 + (0,10/1,75) + 0,04 = 0,50")

    assert memory is not None
    assert memory.r_total == pytest.approx(0.17 + 0.10 / 1.75 + 0.04, abs=1e-6)


# ---------------------------------------------------------------------------
# Aplicação sobre as sugestões
# ---------------------------------------------------------------------------


def test_recompute_replaces_value_inconsistent_with_its_own_terms():
    """O caso exemplar do achado: 2,14 declarado, 3,20 pelos próprios termos (GT 3,2)."""
    issue = _thermal_issue()
    suggestions = [_sug(2.14, _MEMORIA_LAJE)]

    result, telemetry = recompute_thermal_suggestions(suggestions, issue)

    assert result[0].value == pytest.approx(3.2023, abs=1e-3)
    assert telemetry["recomputed"] == 1
    assert "2.14" in result[0].justification  # valor original preservado na trilha
    assert "recalculado" in result[0].justification.lower()


def test_recompute_keeps_label_in_sync_with_value():
    """O label é o que a interface mostra; não pode divergir do valor escrito."""
    issue = _thermal_issue()

    result, _ = recompute_thermal_suggestions([_sug(2.14, _MEMORIA_LAJE)], issue)

    assert result[0].label == str(result[0].value)


def test_recompute_leaves_consistent_suggestion_untouched():
    """Quando o valor JÁ é 1/R_total dos termos, nada muda."""
    issue = _thermal_issue()
    memoria = "R_total = 0.17 + (0.10/1.75) + 0.04 = 0.267; U = 3.74"
    original = _sug(3.74, memoria)

    result, telemetry = recompute_thermal_suggestions([original], issue)

    assert result[0].value == 3.74
    assert result[0].justification == memoria
    assert telemetry["recomputed"] == 0


def test_recompute_ignores_non_thermal_issues():
    """FireRating tem números na justificativa e não é grandeza calculável assim."""
    issue = _fire_issue()
    original = _sug("REI 60", "R_total = 0.17 + (0.02/1.05) + 0.04 = 0.468")

    result, telemetry = recompute_thermal_suggestions([original], issue)

    assert result[0].value == "REI 60"
    assert telemetry["recomputed"] == 0


def test_recompute_without_memory_leaves_value_untouched():
    """Sem memória não há o que recomputar — o valor do LLM permanece."""
    issue = _thermal_issue()

    result, telemetry = recompute_thermal_suggestions([_sug(3.5, "Valor alto.")], issue)

    assert result[0].value == 3.5
    assert telemetry["recomputed"] == 0
    assert telemetry["without_memory"] == 1


def test_structured_memory_takes_precedence_over_free_text():
    """No v7 o modelo declara a memória em campo estruturado; texto é fallback."""
    issue = _thermal_issue()
    estruturada = {
        "rsi": 0.17,
        "rse": 0.04,
        "camadas": [
            {"material": "piso", "espessura_m": 0.02, "lambda": 1.05},
            {"material": "regularização", "espessura_m": 0.03, "lambda": 1.15},
            {"material": "concreto", "espessura_m": 0.10, "lambda": 1.75},
        ],
    }
    suggestion = _sug(2.14, "texto irrelevante", calc_memory=estruturada)

    result, telemetry = recompute_thermal_suggestions([suggestion], issue)

    assert result[0].value == pytest.approx(3.2023, abs=1e-3)
    assert telemetry["recomputed"] == 1


def test_air_cavity_resistance_is_accepted_as_bare_term():
    """Câmara de ar entra como R fixo (0,17), não como espessura/λ."""
    memory = parse_calc_memory(
        "R_total = 0.13 + (0.0125/0.35) + 0.17 + (0.0125/0.35) + 0.04 = 0.41"
    )

    assert memory is not None
    esperado = 0.13 + 0.0125 / 0.35 + 0.17 + 0.0125 / 0.35 + 0.04
    assert memory.r_total == pytest.approx(esperado, abs=1e-6)


# ---------------------------------------------------------------------------
# Integração com o gerador
# ---------------------------------------------------------------------------


def test_generator_recomputes_and_instruments_thermal_value():
    """A recomputação roda dentro de generate() e fica registrada nas métricas.

    Resposta real do run v6 (gemma2:9b): termos corretos, soma errada, valor
    2,14 — contra GT 3,2. A conta refeita devolve 3,20.
    """
    from unittest.mock import MagicMock

    from src.suggestion_engine.ollama_client import OllamaClient
    from src.suggestion_engine.suggestion import SuggestionGenerator

    client = MagicMock(spec=OllamaClient)
    client.generate.return_value = (
        '{"opcoes": [{"valor": 2.14, "justificativa": "' + _MEMORIA_LAJE.replace('"', "") + '", '
        '"confianca": "alta"}]}'
    )
    gen = SuggestionGenerator(client)

    contexto = {"building_type": "Residencial", "bioclimatic_zone": "3"}
    result = gen.generate(_thermal_issue(), contexto)

    assert float(result.suggestions[0].value) == pytest.approx(3.2023, abs=1e-3)
    assert result.metrics is not None
    assert result.metrics.thermal_recomputed is True


def test_generator_leaves_non_thermal_untouched():
    """Nenhuma issue fora de ThermalTransmittance é tocada pela camada."""
    from unittest.mock import MagicMock

    from src.suggestion_engine.ollama_client import OllamaClient
    from src.suggestion_engine.suggestion import SuggestionGenerator

    client = MagicMock(spec=OllamaClient)
    client.generate.return_value = (
        '{"opcoes": [{"valor": "REI 60", "justificativa": "Alvenaria de vedação.", '
        '"confianca": "alta"}]}'
    )
    gen = SuggestionGenerator(client)

    result = gen.generate(_fire_issue(), {"building_type": "Residencial", "bioclimatic_zone": "3"})

    assert result.suggestions[0].value == "REI 60"
    assert result.metrics is not None
    assert result.metrics.thermal_recomputed is False


def test_reused_issues_inherit_the_recomputed_flag():
    """As cópias herdam o VALOR recomputado — têm de herdar a marca também.

    Medido em 2026-08-04: sem isso o JSONL reportou 8 issues recomputadas onde
    o correto eram 423 (8 estímulos × suas cópias), subcontando por 50x a
    cobertura da camada determinística.
    """
    from unittest.mock import MagicMock

    from src.suggestion_engine.ollama_client import OllamaClient
    from src.suggestion_engine.suggestion import SuggestionGenerator

    client = MagicMock(spec=OllamaClient)
    client.generate.return_value = (
        '{"opcoes": [{"valor": 2.14, "justificativa": "' + _MEMORIA_LAJE.replace('"', "") + '", '
        '"confianca": "alta"}]}'
    )
    gen = SuggestionGenerator(client)
    primaria, copia = _thermal_issue(), _thermal_issue()

    resultados = gen.generate_batch(
        [primaria, copia],
        {"building_type": "Residencial", "bioclimatic_zone": "3"},
        reuse_map={copia.id: primaria.id},
    )

    assert resultados[0].metrics.thermal_recomputed is True
    assert resultados[1].metrics.thermal_recomputed is True
