"""Recomputação determinística de ThermalTransmittance (condição v7).

Medido em 2026-08-02 (`docs/achado-aritmetica-termica-2026-08-02.md`): sob o
prompt v6, o modelo identificava as camadas, recuperava os λ corretos e montava
o método da NBR 15220-2 — e **errava a adição**. Nas 4 memórias parseáveis do
run, o valor devolvido era fielmente ``1/(a soma que o próprio modelo
escreveu)``, e refazer a soma reproduzia o ground truth (2,14 → 3,20 contra GT
3,2).

A conclusão operacional é que a aritmética não deve ser pedida ao LLM: ele
declara a **estrutura** (camadas, λ, resistências superficiais) e este módulo
executa a conta. Também dá um critério objetivo de inconsistência interna: se o
valor declarado não é ``1/R_total`` pelos termos que o próprio modelo escreveu,
a sugestão é inconsistente consigo mesma.

Só age sobre issues de ``ThermalTransmittance``; sem memória, não age.
"""

from __future__ import annotations

import re
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from src.models import Issue, Suggestion
from src.semantic.property_match import properties_match

__all__ = [
    "ThermalMemory",
    "ThermalTerm",
    "parse_calc_memory",
    "recompute_thermal_suggestions",
]

# Faixas físicas de sanidade. R_total de um fechamento brasileiro típico fica
# entre ~0,15 (vidro simples) e ~5 (parede com isolante espesso); fora disso a
# memória foi parseada errado ou o modelo escreveu absurdo, e recomputar seria
# trocar um erro por outro.
_R_TOTAL_MIN = 0.05
_R_TOTAL_MAX = 10.0
_U_MIN = 0.1
_U_MAX = 20.0

# Tolerância de consistência interna: a conta é aritmética, não estimativa.
# 1% separa "arredondou" de "somou errado".
_CONSISTENCY_TOLERANCE = 0.01

# O corpo da conta é só dígitos, separadores, parênteses, barras, "+" e "=".
# Delimitar por vírgula NÃO funciona: em pt-BR a vírgula é o separador decimal
# ("0,468") e cortaria a expressão no primeiro termo.
_MEMORY_RE = re.compile(r"r_?total\s*[=:]\s*(?P<body>[\d.,()/+\s=≈]+)", re.IGNORECASE)
_QUOTIENT_RE = re.compile(r"^\(?\s*([\d.,]+)\s*/\s*([\d.,]+)\s*\)?$")
_BARE_RE = re.compile(r"^\(?\s*([\d.,]+)\s*\)?$")


class ThermalTerm(BaseModel):
    """Um termo da soma de resistências: quociente e/λ ou resistência fixa."""

    resistance: float
    thickness_m: float | None = None
    lambda_w_mk: float | None = None
    material: str | None = None


class ThermalMemory(BaseModel):
    """Memória de cálculo de U reconstruída a partir do que o LLM declarou."""

    terms: list[ThermalTerm] = Field(default_factory=list)
    r_total: float
    """Soma REFEITA dos termos — não a soma que o modelo declarou."""
    declared_r_total: float | None = None
    """R_total que o modelo escreveu, quando presente (para medir a divergência)."""

    @property
    def u_value(self) -> float:
        """Transmitância térmica U = 1 / R_total, pelos termos declarados."""
        return 1.0 / self.r_total


def _to_float(raw: str) -> float | None:
    """Converte número em pt-BR ou en-US para float, ou None se inviável."""
    text = raw.strip()
    if not text:
        return None
    # "0,468" é decimal em pt-BR; separador de milhar não ocorre nestas grandezas.
    text = text.replace(",", ".")
    if text.count(".") > 1:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _split_terms(expression: str) -> list[str]:
    """Divide a expressão de R_total nos termos somados."""
    return [part for part in (chunk.strip() for chunk in expression.split("+")) if part]


def _build_memory(terms: list[ThermalTerm], declared: float | None) -> ThermalMemory | None:
    """Valida a soma refeita e monta a memória, ou None se fora de faixa física."""
    if len(terms) < 2:
        return None
    r_total = sum(term.resistance for term in terms)
    if not (_R_TOTAL_MIN <= r_total <= _R_TOTAL_MAX):
        return None
    u_value = 1.0 / r_total
    if not (_U_MIN <= u_value <= _U_MAX):
        return None
    return ThermalMemory(terms=terms, r_total=r_total, declared_r_total=declared)


def parse_calc_memory(text: str | None) -> ThermalMemory | None:
    """Extrai a memória de cálculo de uma justificativa em texto livre.

    Reconhece o formato do contrato v6 — ``R_total = Rsi + (e1/λ1) + ... + Rse
    = 0,468`` — aceitando vírgula decimal, termos entre parênteses e
    resistências fixas (câmara de ar, Rsi/Rse). Devolve None quando não há
    conta, quando há menos de 2 termos ou quando o resultado é fisicamente
    absurdo: nesses casos recomputar seria inventar.
    """
    if not text:
        return None

    match = _MEMORY_RE.search(text)
    if match is None:
        return None

    # "Rsi + (e/λ) + Rse = 0,468" → expressão dos termos e soma declarada.
    segments = [segment.strip().strip(",;") for segment in re.split(r"[=≈]", match.group("body"))]
    declared = _to_float(segments[1]) if len(segments) > 1 else None

    terms: list[ThermalTerm] = []
    for raw_term in _split_terms(segments[0]):
        quotient = _QUOTIENT_RE.match(raw_term)
        if quotient is not None:
            thickness = _to_float(quotient.group(1))
            lambda_value = _to_float(quotient.group(2))
            if thickness is None or lambda_value is None or lambda_value <= 0:
                return None
            terms.append(
                ThermalTerm(
                    resistance=thickness / lambda_value,
                    thickness_m=thickness,
                    lambda_w_mk=lambda_value,
                )
            )
            continue

        bare = _BARE_RE.match(raw_term)
        if bare is not None:
            resistance = _to_float(bare.group(1))
            if resistance is None or resistance < 0:
                return None
            terms.append(ThermalTerm(resistance=resistance))
            continue

        # Termo não reconhecido (texto no meio da conta): a memória não é
        # confiável o bastante para substituir o valor do engenheiro.
        return None

    return _build_memory(terms, declared)


def memory_from_structured(payload: Any) -> ThermalMemory | None:
    """Monta a memória a partir do campo estruturado do contrato v7.

    Formato aceito: ``{"rsi": 0.17, "rse": 0.04, "camadas": [{"espessura_m":
    0.02, "lambda": 1.05, "material": "piso"}]}``. Uma camada pode declarar
    ``resistencia`` direto (câmara de ar não ventilada), em vez de e/λ.
    """
    if not isinstance(payload, dict):
        return None

    terms: list[ThermalTerm] = []
    rsi = _coerce_number(payload.get("rsi"))
    if rsi is not None:
        terms.append(ThermalTerm(resistance=rsi, material="Rsi"))

    layers = payload.get("camadas") or payload.get("layers") or []
    if not isinstance(layers, list):
        return None
    for layer in layers:
        if not isinstance(layer, dict):
            return None
        material = layer.get("material") or layer.get("nome")
        resistance = _coerce_number(layer.get("resistencia") or layer.get("resistance"))
        if resistance is not None:
            terms.append(
                ThermalTerm(
                    resistance=resistance,
                    material=str(material) if material else None,
                )
            )
            continue
        thickness = _coerce_number(layer.get("espessura_m") or layer.get("thickness_m"))
        lambda_value = _coerce_number(layer.get("lambda") or layer.get("lambda_w_mk"))
        if thickness is None or lambda_value is None or lambda_value <= 0:
            return None
        terms.append(
            ThermalTerm(
                resistance=thickness / lambda_value,
                thickness_m=thickness,
                lambda_w_mk=lambda_value,
                material=str(material) if material else None,
            )
        )

    rse = _coerce_number(payload.get("rse"))
    if rse is not None:
        terms.append(ThermalTerm(resistance=rse, material="Rse"))

    declared = _coerce_number(payload.get("r_total") or payload.get("rtotal"))
    return _build_memory(terms, declared)


def _coerce_number(value: Any) -> float | None:
    """Converte valor arbitrário do payload em float não negativo, ou None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value >= 0 else None
    if isinstance(value, str):
        parsed = _to_float(value)
        return parsed if parsed is not None and parsed >= 0 else None
    return None


def _is_thermal_issue(issue: Issue) -> bool:
    """True quando a issue pede ThermalTransmittance."""
    target = str(issue.context.get("check_property") or "")
    return bool(target) and properties_match(target, "ThermalTransmittance")


def _declared_value(suggestion: Suggestion) -> float | None:
    """Valor numérico já sugerido pelo LLM, quando houver."""
    return _coerce_number(suggestion.value)


def recompute_thermal_suggestions(
    suggestions: list[Suggestion],
    issue: Issue,
) -> tuple[list[Suggestion], dict[str, int]]:
    """Recalcula U pelas memórias declaradas e devolve (sugestões, telemetria).

    Age apenas em issues de ThermalTransmittance e apenas onde há memória
    parseável. Quando o valor declarado já é ``1/R_total`` dentro da tolerância,
    nada muda. Quando diverge, o valor passa a ser o recomputado e a
    justificativa registra o valor original — a trilha de auditoria não pode
    perder o que o LLM havia respondido.
    """
    telemetry = {"recomputed": 0, "consistent": 0, "without_memory": 0}
    if not _is_thermal_issue(issue):
        return suggestions, telemetry

    for suggestion in suggestions:
        memory = memory_from_structured(suggestion.calc_memory) or parse_calc_memory(
            suggestion.justification
        )
        if memory is None:
            telemetry["without_memory"] += 1
            continue

        computed = round(memory.u_value, 4)
        declared = _declared_value(suggestion)
        if declared is not None and declared > 0:
            divergence = abs(computed - declared) / declared
            if divergence <= _CONSISTENCY_TOLERANCE:
                telemetry["consistent"] += 1
                continue

        suggestion.value = computed
        suggestion.label = str(computed)
        origem = f"{declared}" if declared is not None else "não numérico"
        suggestion.justification = (
            f"{suggestion.justification} "
            f"(valor recalculado deterministicamente pelos termos declarados: "
            f"R_total = {memory.r_total:.4f} → U = {computed}; o LLM havia respondido {origem})"
        ).strip()
        telemetry["recomputed"] += 1
        logger.debug(
            "Térmico recomputado na issue {}: {} → {} (R_total={:.4f})",
            issue.id,
            origem,
            computed,
            memory.r_total,
        )

    return suggestions, telemetry
