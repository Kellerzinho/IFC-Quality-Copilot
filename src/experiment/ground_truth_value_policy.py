"""Resolvedor determinístico dos valores do ground truth de cobertura integral."""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from src.experiment.evaluator import GroundTruthItem
from src.experiment.ground_truth_policy import GroundTruthDecision
from src.models import Issue

THERMAL_FALLBACK = {
    "IfcWall": 2.48,
    "IfcWallStandardCase": 2.48,
    "IfcSlab": 3.20,
    "IfcSlabStandardCase": 3.20,
    "IfcRoof": 2.00,
    "IfcDoor": 3.00,
    "IfcWindow": 5.70,
    "IfcCurtainWall": 5.70,
}
# Referências térmicas específicas por material, dentro de uma classe IFC.
# A constante única de THERMAL_FALLBACK vale para o caso usual da classe; quando
# o arquivo declara uma construção de comportamento térmico distinto, a
# referência dessa construção prevalece. Registrado em docs/pontos-de-calculo.md.
_THERMAL_FALLBACK_BY_MATERIAL: dict[str, dict[str, float]] = {
    # Telha de fibrocimento sem forro: valor consagrado da revisão autoral
    # (REVISAO_GT.md). O genérico 2,00 descreve laje de cobertura, não telha.
    "IfcRoof": {"fibrocimento": 4.60},
}
ACOUSTIC_FALLBACK_DB = {
    "IfcWall": 40,
    "IfcWallStandardCase": 40,
    "IfcSlab": 45,
    "IfcSlabStandardCase": 45,
    "IfcRoof": 40,
    "IfcDoor": 25,
    "IfcWindow": 30,
}
FIRE_FALLBACK = {"IfcDoor": "EI 60", "IfcWindow": "EI 60"}
FIRE_FALLBACK_DEFAULT = "REI 60"
SHGC_GENERIC_CLEAR_GLASS = 0.87

# ---------------------------------------------------------------------------
# Equivalências de decisão — critério de avaliação declarado (2026-08-10)
# ---------------------------------------------------------------------------
# O comparador trata classe de fogo e rótulo acústico como TEXTO de propósito
# (``evaluator._as_scalar_number``): "EI 60" não pode casar com "REI 60" por
# acidente numérico. Toda equivalência entre respostas que representam a MESMA
# decisão técnica entra aqui, como ``accepted_alternatives`` por item — dado
# declarado e auditável, nunca regra embutida no comparador.
#
# Princípio: **a severidade da equivalência acompanha a confiança da
# referência.** Onde o GT é hipótese congelada (`low`/`probable`), ele não tem
# autoridade para discriminar a duração — o TRRF depende de altura e ocupação,
# que o IFC não carrega; mede-se a classe (estanqueidade + isolamento) e a
# plausibilidade da duração. Onde a referência foi verificada pelo autor
# (`high`), vale a tabela ratificada em 2026-08-04
# (``data/evaluation/predio/REVISAO_GT.md``, "Emendas pós-aprovação").
_FIRE_DURATIONS = ("30", "60", "90", "120")
_FIRE_PROTECTIVE_PREFIXES = ("EI", "REI")
# Emenda ratificada em 2026-08-04: em vedação que o IFC declara não portante,
# EI de duração ≥ à exigida é alternativa aceita ao REI da compartimentação —
# "um modelo que responde EI está seguindo a evidência dada pelo arquivo e não
# deve ser penalizado".
_FIRE_RATIFIED_NON_LOAD_BEARING = ("REI 90", "REI 120", "EI 60", "EI 90", "EI 120")

# Emenda de 2026-08-12 (decisão editorial após o benchmark v7.5). A base autoral
# registrou "EI 30" para as 222 paredes de drywall do prédio
# (``REVISAO_GT.md``), mas a nota terminava em "ATENÇÃO ... conferir": o
# protocolo de 2026-08-08 leu o marcador de incerteza, descartou o item legado e
# caiu no genérico "REI 60"/low, cujas alternativas cortam duração < 60 min. O
# resultado é que a resposta MAIS aderente ao estímulo era contada como erro —
# o próprio template ensina "EI = não portante, só compartimenta (ex.: divisória
# leve, drywall)" e autoriza 30 minutos.
#
# A emenda não muda o valor esperado (segue REI 60, hipótese congelada): amplia
# o conjunto aceito para incluir a duração autoral em vedação leve. Fora desse
# recorte o piso de 60 min continua valendo — aceitar 30 min em qualquer vedação
# faria o estrato parar de discriminar (medido em 2026-08-10).
_FIRE_LIGHT_PARTITION_MIN_DURATION = "EI 30"
_LIGHT_PARTITION_TOKENS = (
    "drywall",
    "dry wall",
    "dry-wall",
    "gesso acartonado",
    "steel frame",
    "placa cimenticia",
    "divisoria leve",
)

# A referência acústica é uma constante tipológica por classe de elemento, não
# um ensaio (a própria nota do item diz isso). Exigir 2% dela mede notação, não
# decisão — mesmo motivo pelo qual o térmico ganhou banda de 10%. O passo entre
# classes de desempenho é ~5 dB, então a concordância é medida nessa
# granularidade.
_ACOUSTIC_BAND_DB = 5

_CATEGORY_ALIASES = {
    "quarto": "BEDROOM",
    "dormitorio": "BEDROOM",
    "sala de estar": "LIVING_ROOM",
    "sala": "LIVING_ROOM",
    "cozinha": "KITCHEN",
    "banheiro": "BATHROOM",
    "lavabo": "WC",
    "wc": "WC",
    "circulacao": "CIRCULATION",
    "corredor": "CIRCULATION",
    "area de servico": "SERVICE_AREA",
    "escritorio": "OFFICE",
    "sala de reuniao": "MEETING_ROOM",
    "recepcao": "LOBBY",
    "deposito": "STORAGE",
    "varanda": "BALCONY",
    "sacada": "BALCONY",
    "garagem": "GARAGE",
    "area tecnica": "TECHNICAL_AREA",
}
_LAMBDA_BY_TOKEN = {
    "concreto": 1.75,
    "argamassa": 1.15,
    "revestimento cimenticio": 1.15,
    "ceramica": 0.90,
    "ceramico": 0.90,
    "gesso": 0.35,
    "eps": 0.04,
    "madeira": 0.15,
    "vidro": 1.00,
}
# Em laje e cobertura, "ceramica/ceramico" designa piso ceramico ou porcelanato
# (1,05), nao bloco ceramico de vedacao (0,90). docs/pontos-de-calculo.md trata
# as duas tabelas como complementares e os templates de prompt ja declaram os
# dois valores separadamente; so este resolvedor as havia achatado numa unica.
_LAMBDA_BY_TOKEN_HORIZONTAL = {
    "ceramica": 1.05,
    "ceramico": 1.05,
}
_HORIZONTAL_CLASSES = frozenset({"IfcRoof", "IfcSlab", "IfcSlabStandardCase"})


class UnsupportedGroundTruthFamily(ValueError):
    """Indica uma família sem regra concreta aprovada."""


class LayerEvidence(BaseModel):
    """Camada material normalizada para cálculo térmico."""

    model_config = ConfigDict(extra="forbid")

    material: str
    thickness_m: float | None = None


class ElementEvidence(BaseModel):
    """Evidência IFC necessária para decidir sem abrir o modelo no resolvedor."""

    model_config = ConfigDict(extra="forbid")

    element_class: str
    element_type_name: str = ""
    element_long_name: str = ""
    material_name: str = ""
    layers: tuple[LayerEvidence, ...] = ()
    total_thickness_m: float | None = None
    is_external: bool | None = None
    load_bearing_alias: bool | None = None
    expected_relation: str | None = None


def _element_hint(issue: Issue | None, evidence: ElementEvidence | None) -> str:
    """Texto normalizado com o que o arquivo diz sobre a construção do elemento."""
    partes = [
        (issue.element_name if issue else "") or "",
        evidence.material_name if evidence else "",
        evidence.element_type_name if evidence else "",
        evidence.element_long_name if evidence else "",
    ]
    if evidence is not None:
        partes.extend(layer.material for layer in evidence.layers)
    return _normalise(" ".join(partes))


def _is_light_partition(issue: Issue | None, evidence: ElementEvidence | None) -> bool:
    """True para vedação leve (drywall/steel frame) declarada no arquivo."""
    if evidence is not None and evidence.load_bearing_alias is True:
        return False
    hint = _element_hint(issue, evidence)
    return any(token in hint for token in _LIGHT_PARTITION_TOKENS)


def _fire_alternatives(
    expected: str, *, ratified: bool, light_partition: bool = False
) -> list[str]:
    """Classes de fogo que representam a mesma decisão do ``expected``.

    ``ratified=True`` aplica exatamente a tabela que o autor ratificou em
    2026-08-04 para vedação não portante.

    ``ratified=False`` vale onde a referência é hipótese congelada. Aceita a
    família estanqueidade+isolamento — porque a referência não tem autoridade
    para exigir a capacidade estrutural (R) que o IFC não declara — **mas só em
    duração igual ou superior à exigida**. Aceitar duração inferior seria dar
    por boa uma decisão menos segura que a referência, o que contraria o
    precedente do projeto de aceitar apenas classes superiores (REI 90/120
    acima de REI 60). Medido em 2026-08-10: sem essa restrição o estrato de
    fogo ia a 40/40 no gemma2 e parava de discriminar qualquer modelo.
    """
    if ratified:
        aceitos = list(_FIRE_RATIFIED_NON_LOAD_BEARING)
        if light_partition:
            aceitos.append(_FIRE_LIGHT_PARTITION_MIN_DURATION)
        return [alt for alt in aceitos if alt != expected]
    match = re.search(r"(\d+)", expected)
    minimo = int(match.group(1)) if match else 0
    duracoes = [d for d in _FIRE_DURATIONS if int(d) >= minimo]
    aceitos = [
        f"{prefixo} {duracao}" for prefixo in _FIRE_PROTECTIVE_PREFIXES for duracao in duracoes
    ]
    if expected.startswith("EI"):
        # Porta e janela corta-fogo também são especificadas como P-CF.
        aceitos.extend(f"P-CF {duracao}" for duracao in duracoes)
    if light_partition:
        # Emenda 2026-08-12: restaura a duração autoral da vedação leve, que o
        # piso genérico de 60 min havia descartado junto com o item legado.
        aceitos.append(_FIRE_LIGHT_PARTITION_MIN_DURATION)
    return [alt for alt in aceitos if alt != expected]


def _acoustic_alternatives(reference_db: int) -> list[object]:
    """Valores de Rw que representam a mesma decisão de isolamento acústico.

    Só a notação canônica ``"Rw NN dB"``: o schema do próprio ground truth a
    exige (``ground_truth_validation.ACOUSTIC_RATING_PATTERN``), e vocabulário
    de referência normalizado é o que torna a comparação auditável. O que
    precisou mudar do outro lado foi o **prompt**, que ensinava a letra da
    classe e cobrava um formato que o GT não pontuava — corrigido no v7.5.
    """
    return [
        f"Rw {valor} dB"
        for valor in range(
            reference_db - _ACOUSTIC_BAND_DB, reference_db + _ACOUSTIC_BAND_DB + 1
        )
        if valor != reference_db and 10 <= valor <= 99
    ]


def _normalise(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    without_accents = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(without_accents.casefold().replace("_", " ").split())


def _decision(
    expected_value: object,
    confidence: str,
    source_kind: str,
    notes: str,
    *,
    alternatives: list[object] | None = None,
    legacy_reference: bool = False,
) -> GroundTruthDecision:
    return GroundTruthDecision(
        expected_value=expected_value,
        accepted_alternatives=list(alternatives or []),
        confidence=confidence,
        source_kind=source_kind,
        notes=notes,
        legacy_reference=legacy_reference,
    )


def _frozen_item_decision(
    item: GroundTruthItem,
    *,
    source_kind: str,
    legacy_reference: bool,
    issue: Issue | None = None,
    evidence: ElementEvidence | None = None,
) -> GroundTruthDecision:
    if not item.verified or item.expected_value is None:
        raise ValueError("frozen donor must be verified and concrete")
    alternativas = list(item.accepted_alternatives)
    alternativas.extend(
        alt
        for alt in _ratified_fire_amendment(item, issue, evidence)
        if alt not in alternativas
    )
    return _decision(
        item.expected_value,
        "high",
        source_kind,
        item.notes or "Referência congelada e identificada pela mesma equivalência.",
        alternatives=alternativas,
        legacy_reference=legacy_reference,
    )


def _ratified_fire_amendment(
    item: GroundTruthItem,
    issue: Issue | None,
    evidence: ElementEvidence | None,
) -> list[str]:
    """Emenda EI/REI ratificada pelo autor em 2026-08-04, restaurada em 2026-08-10.

    O protocolo de cobertura integral de 2026-08-08 tratou a emenda como pendente
    e a removeu dos itens legados, contra o registro autoral. O escopo é o
    declarado na ratificação: vedação cujo IFC declara ``LoadBearing = false``,
    com ``REI`` como valor esperado.
    """
    if issue is None or evidence is None:
        return []
    if str(issue.context.get("check_property") or "") != "FireRating":
        return []
    if evidence.load_bearing_alias is not False:
        return []
    expected = str(item.expected_value or "")
    if not expected.upper().startswith("REI"):
        return []
    return _fire_alternatives(
        expected, ratified=True, light_partition=_is_light_partition(issue, evidence)
    )


def amended_value_for_frozen_item(
    issue: Issue,
    evidence: ElementEvidence,
    expected_value: object,
    confidence: str,
    notes: str,
) -> tuple[object, str, str] | None:
    """Emenda de VALOR sobre item já congelado; ``None`` quando nada muda.

    O protocolo de cobertura integral preserva ``expected_value`` byte a byte, o
    que é o certo por padrão: o GT não deve mudar de valor a cada rodada. Mas ele
    também torna irreversível, por construção, qualquer inversão que o próprio
    protocolo tenha introduzido — foi o caso da telha de fibrocimento, cuja
    referência autoral (4,6) o filtro de 2026-08-08 substituiu pelo genérico de
    cobertura (2,00), −56% no sentido oposto ao da revisão do autor.

    Cada emenda aqui é um recorte nominal, com a decisão editorial registrada em
    doc datado — nunca uma regra que reabre o valor de famílias inteiras.
    Devolve ``(valor, confiança, nota)``.
    """
    if str(issue.context.get("check_property") or "") != "ThermalTransmittance":
        return None
    if issue.element_class != "IfcRoof" or expected_value != 2.00:
        return None
    especifico = _THERMAL_FALLBACK_BY_MATERIAL.get("IfcRoof", {})
    hint = _element_hint(issue, evidence)
    for token, valor in especifico.items():
        if token in hint:
            return (
                valor,
                confidence,
                (
                    "Referência tipológica congelada por classe/material; composição "
                    f"insuficiente para cálculo integral; U={valor:.2f} W/(m²·K): {hint}. "
                    "Emenda de 2026-08-12: telha fina sem forro não se comporta como laje "
                    "de cobertura; restaurado o valor da revisão autoral."
                ),
            )
    return None


def accepted_alternatives_for_frozen_value(
    issue: Issue,
    evidence: ElementEvidence,
    expected_value: object,
    confidence: str,
    current: Sequence[object] = (),
) -> list[object]:
    """Conjunto **completo** de respostas aceitas para um valor já congelado.

    Serve à emenda de 2026-08-10: o valor esperado, a confiança e a proveniência
    do GT integral são preservados byte a byte, e só o conjunto de respostas
    aceitas é recalculado pela política vigente. É o mesmo movimento da emenda
    EI/REI de 2026-08-04 — critério de avaliação declarado, recalculável sobre
    coletas já gravadas, sem exigir nova anotação.

    Devolve o conjunto **inteiro**, nunca um acréscimo: o chamador substitui. Se
    fosse aditivo, a política só saberia alargar — um estreitamento como o de
    2026-08-10 no fogo jamais teria efeito sobre um GT já emitido. Para as
    famílias que a emenda não governa, devolve ``current`` inalterado.
    """
    property_name = str(issue.context.get("check_property") or "")
    expected = str(expected_value or "")

    if property_name == "FireRating":
        leve = _is_light_partition(issue, evidence)
        if confidence == "high":
            # Referência verificada pelo autor: as alternativas dela mandam, e a
            # emenda ratificada só acrescenta onde o escopo aprovado alcança.
            aceitos = list(current)
            if evidence.load_bearing_alias is False and expected.upper().startswith("REI"):
                aceitos.extend(
                    alt
                    for alt in _fire_alternatives(expected, ratified=True, light_partition=leve)
                    if alt not in aceitos
                )
            return aceitos
        return list(_fire_alternatives(expected, ratified=False, light_partition=leve))

    if property_name == "AcousticRating":
        match = re.search(r"(\d+)", expected)
        if match is None:
            return list(current)
        return list(_acoustic_alternatives(int(match.group(1))))

    return list(current)


def _thermal_surface_resistance(element_class: str) -> tuple[float, float, str]:
    if element_class in {"IfcRoof"}:
        return 0.10, 0.04, "fluxo ascendente"
    if element_class in {"IfcSlab", "IfcSlabStandardCase"}:
        return 0.17, 0.04, "fluxo descendente"
    return 0.13, 0.04, "fluxo horizontal"


def _lambda_for(material: str, element_class: str) -> float | None:
    """Condutividade da camada, com a tabela da familia do elemento.

    ``element_class`` decide entre a tabela de parede e a de laje/cobertura nos
    materiais cujo termo designa produtos diferentes em cada familia.
    """
    normalised = _normalise(material)
    overrides = (
        _LAMBDA_BY_TOKEN_HORIZONTAL if element_class in _HORIZONTAL_CLASSES else {}
    )
    for token, value in _LAMBDA_BY_TOKEN.items():
        if token in normalised:
            return overrides.get(token, value)
    return None


def _thermal_decision(issue: Issue, evidence: ElementEvidence) -> GroundTruthDecision:
    layer_terms: list[tuple[LayerEvidence, float]] = []
    for layer in evidence.layers:
        conductivity = _lambda_for(layer.material, issue.element_class)
        if (
            conductivity is None
            or layer.thickness_m is None
            or isinstance(layer.thickness_m, bool)
            or not math.isfinite(layer.thickness_m)
            or layer.thickness_m <= 0
        ):
            layer_terms = []
            break
        layer_terms.append((layer, conductivity))

    if layer_terms:
        rsi, rse, flow = _thermal_surface_resistance(issue.element_class)
        layer_resistance = 0.0
        for layer, conductivity in layer_terms:
            thickness = layer.thickness_m
            if thickness is None:
                raise AssertionError("validated thermal layer lost its thickness")
            layer_resistance += thickness / conductivity
        r_total = rsi + layer_resistance + rse
        value = round(1.0 / r_total, 2)
        layer_note = "; ".join(
            f"{layer.material}={layer.thickness_m:.4f}/{conductivity:.2f}"
            for layer, conductivity in layer_terms
            if layer.thickness_m is not None
        )
        return _decision(
            value,
            "medium",
            "calculation",
            (
                f"Cálculo U=1/Rt={value:.2f} W/(m²·K) ({flow}); "
                f"Rsi={rsi:.2f}; {layer_note}; "
                f"Rse={rse:.2f}; Rt={r_total:.4f} m²·K/W."
            ),
        )

    fallback = THERMAL_FALLBACK.get(issue.element_class)
    if fallback is None:
        raise UnsupportedGroundTruthFamily(
            f"ThermalTransmittance sem regra para {issue.element_class}"
        )
    material_hint = _normalise(
        " ".join(
            [
                evidence.material_name,
                evidence.element_type_name,
                *(layer.material for layer in evidence.layers),
            ]
        )
    )
    # Emenda de 2026-08-12: a constante única por classe tratava toda cobertura
    # como laje de terraço. Telha fina sem forro nem câmara é outro elemento
    # térmico — a referência autoral (4,6) está registrada em REVISAO_GT.md e é
    # a que a casa também precisa, por não ter base autoral própria. O cálculo
    # por camadas não alcança este caso: fibrocimento não está em _LAMBDA_BY_TOKEN.
    especifico = _THERMAL_FALLBACK_BY_MATERIAL.get(issue.element_class, {})
    for token, valor in especifico.items():
        if token in material_hint:
            fallback = valor
            break
    if material_hint:
        return _decision(
            fallback,
            "medium",
            "typology",
            (
                "Referência tipológica congelada por classe/material; composição "
                f"insuficiente para cálculo integral; U={fallback:.2f} W/(m²·K): "
                f"{material_hint}."
            ),
        )
    return _decision(
        fallback,
        "low",
        "probable",
        (
            f"Hipótese congelada: U={fallback:.2f} W/(m²·K), "
            "transmitância mais provável para "
            f"{issue.element_class}; camadas, espessuras ou λ não foram declarados no IFC."
        ),
    )


def _category_decision(evidence: ElementEvidence) -> GroundTruthDecision:
    hint = _normalise(evidence.element_long_name or evidence.element_type_name)
    if hint:
        for alias, category in sorted(_CATEGORY_ALIASES.items(), key=lambda item: -len(item[0])):
            if alias in hint:
                return _decision(
                    category,
                    "high",
                    "ifc_alias",
                    f"Category derivada do nome IFC: {hint}.",
                )
    return _decision(
        "TECHNICAL_AREA",
        "low",
        "probable",
        (
            "Hipótese congelada: espaço sem nome funcional inequívoco; "
            "TECHNICAL_AREA é o rótulo conservador adotado para o benchmark."
        ),
    )


def _system_decision(issue: Issue, evidence: ElementEvidence) -> GroundTruthDecision:
    hint = _normalise(
        " ".join(
            [
                evidence.material_name,
                evidence.element_type_name,
                evidence.element_long_name,
                *(layer.material for layer in evidence.layers),
            ]
        )
    )
    if issue.element_class in {"IfcWall", "IfcWallStandardCase"}:
        if "drywall" in hint or "chapa de gesso" in hint or "steel frame" in hint:
            value = "Drywall / Steel frame"
        elif "concreto pre" in hint:
            value = "Concreto pré-moldado"
        elif "concreto" in hint and "bloco" in hint:
            value = "Alvenaria em bloco de concreto"
        elif "concreto armado" in hint:
            value = "Concreto armado moldado in loco"
        elif "eps" in hint:
            value = "Painel de EPS"
        elif "bloco ceram" in hint or "alvenaria" in hint:
            value = "Alvenaria de vedação em bloco cerâmico"
        else:
            return _decision(
                "Alvenaria de vedação em bloco cerâmico",
                "low",
                "probable",
                (
                    "Hipótese congelada: parede sem sistema inequívoco; foi adotada a "
                    "tipologia residencial mais provável em Deodoro/RJ."
                ),
            )
    elif issue.element_class in {"IfcSlab", "IfcSlabStandardCase"}:
        if any(token in hint for token in ("porcelanato", "ceramic")):
            value = "Piso cerâmico / porcelanato"
        elif "madeira" in hint:
            value = "Piso de madeira (parquet / taco / deck)"
        elif "grama" in hint:
            value = "Grama natural ou artificial"
        else:
            value = "Laje maciça de concreto armado"
    else:
        raise UnsupportedGroundTruthFamily(
            f"system_unclassified sem vocabulário para {issue.element_class}"
        )
    return _decision(
        value,
        "medium",
        "typology",
        f"Sistema classificado por classe e evidência material congelada: {hint or 'classe IFC'}.",
    )


def _relation_decision(issue: Issue, evidence: ElementEvidence) -> GroundTruthDecision:
    if evidence.expected_relation:
        return _decision(
            evidence.expected_relation,
            "high",
            "ifc_literal",
            "Relação esperada declarada literalmente no diagnóstico IFC.",
        )
    if issue.element_class in {"IfcDoor", "IfcWindow"}:
        relation = "IfcRelFillsElement"
    elif issue.element_class == "IfcSpace":
        relation = "IfcRelSpaceBoundary"
    else:
        raise UnsupportedGroundTruthFamily(f"relation_broken sem regra para {issue.element_class}")
    return _decision(
        relation,
        "medium",
        "typology",
        f"Relação IFC esperada pela função de {issue.element_class}.",
    )


def resolve_ground_truth_decision(
    issue: Issue,
    evidence: ElementEvidence,
    *,
    prior_item: GroundTruthItem | None,
    equivalent_donor: GroundTruthItem | None,
    building_context: Mapping[str, str],
) -> GroundTruthDecision:
    """Aplica a hierarquia aprovada e sempre retorna um valor concreto."""
    del building_context  # o contexto fica explícito na API e nas futuras regras normativas.
    if evidence.element_class != issue.element_class:
        raise ValueError("element evidence class diverges from issue")
    if prior_item is not None and prior_item.legacy_reference:
        return _frozen_item_decision(
            prior_item,
            source_kind="existing_gt",
            legacy_reference=True,
            issue=issue,
            evidence=evidence,
        )
    if equivalent_donor is not None:
        return _frozen_item_decision(
            equivalent_donor,
            source_kind="equivalent_donor",
            legacy_reference=False,
            issue=issue,
            evidence=evidence,
        )
    if issue.issue_type == "relation_broken":
        return _relation_decision(issue, evidence)

    property_name = issue.context.get("check_property")
    if not isinstance(property_name, str):
        raise UnsupportedGroundTruthFamily("check_property ausente ou não textual")

    if property_name in {"LoadBearing", "IsLoadBearing"}:
        if evidence.load_bearing_alias is not None:
            return _decision(
                evidence.load_bearing_alias,
                "high",
                "ifc_alias",
                f"Alias IFC LoadBearing={str(evidence.load_bearing_alias).lower()}.",
            )
        structural = issue.element_class in {"IfcBeam", "IfcColumn", "IfcFooting", "IfcPile"}
        return _decision(
            structural,
            "low",
            "probable",
            (
                "Hipótese congelada: função portante inferida apenas da classe IFC; "
                "não há alias LoadBearing declarado."
            ),
        )
    if property_name == "IsExternal":
        if evidence.is_external is not None:
            return _decision(
                evidence.is_external,
                "high",
                "ifc_alias",
                f"Alias IFC IsExternal={str(evidence.is_external).lower()}.",
            )
        return _decision(
            False,
            "low",
            "probable",
            "Hipótese congelada: elemento tratado como interno sem indicador IFC de exterioridade.",
        )
    if property_name == "Category" and issue.element_class == "IfcSpace":
        return _category_decision(evidence)
    if issue.issue_type == "system_unclassified" and property_name == "":
        return _system_decision(issue, evidence)
    if property_name == "ThermalTransmittance":
        return _thermal_decision(issue, evidence)
    if property_name == "FireRating":
        value = FIRE_FALLBACK.get(issue.element_class, FIRE_FALLBACK_DEFAULT)
        leve = _is_light_partition(issue, evidence)
        nota_leve = (
            " Vedação leve declarada no arquivo: a duração de 30 min registrada na "
            "revisão autoral entra no conjunto aceito (emenda de 2026-08-12)."
            if leve
            else ""
        )
        return _decision(
            value,
            "low",
            "probable",
            (
                "Hipótese congelada: classe de resistência ao fogo mais provável para "
                f"{issue.element_class} residencial; função, ensaio e especificação "
                "completos ausentes. A referência não fixa o TRRF: a avaliação aceita "
                "a família estanqueidade+isolamento em duração normalizada." + nota_leve
            ),
            alternatives=list(
                _fire_alternatives(str(value), ratified=False, light_partition=leve)
            ),
        )
    if property_name == "AcousticRating":
        rating = ACOUSTIC_FALLBACK_DB.get(issue.element_class)
        if rating is None:
            raise UnsupportedGroundTruthFamily(
                f"AcousticRating sem regra para {issue.element_class}"
            )
        return _decision(
            f"Rw {rating} dB",
            "medium",
            "typology",
            (
                "Referência tipológica congelada de isolamento aéreo por classe de elemento; "
                "não representa ensaio do sistema construído. Concordância medida na "
                f"granularidade da classe de desempenho (±{_ACOUSTIC_BAND_DB} dB), aceitando "
                "a letra da classe que o template autoriza."
            ),
            alternatives=list(_acoustic_alternatives(int(rating))),
        )
    if property_name == "SolarHeatGainCoefficient":
        hint = _normalise(
            " ".join([evidence.material_name, evidence.element_type_name, issue.element_name or ""])
        )
        if "vidro" in hint or "glass" in hint:
            return _decision(
                SHGC_GENERIC_CLEAR_GLASS,
                "medium",
                "typology",
                "Referência tipológica congelada para vidro incolor comum.",
            )
        return _decision(
            SHGC_GENERIC_CLEAR_GLASS,
            "low",
            "probable",
            (
                "Hipótese congelada: adotado vidro incolor comum (SHGC=0.87); "
                "produto, película e composição não foram declarados no IFC."
            ),
        )
    if property_name == "HasNonSkidSurface":
        hint = _normalise(
            " ".join(
                [
                    issue.element_name or "",
                    evidence.element_type_name,
                    evidence.element_long_name,
                    evidence.material_name,
                ]
            )
        )
        positive = bool(evidence.is_external) or any(
            token in hint
            for token in ("escada", "stair", "patamar", "molhad", "banheiro", "extern")
        )
        return _decision(
            positive,
            "medium",
            "typology",
            (
                "Hipótese funcional congelada a partir de localização/material: "
                f"{hint or 'sem pista'}."
            ),
        )

    raise UnsupportedGroundTruthFamily(
        f"{issue.issue_type}/{property_name or '<empty>'}/{issue.element_class}"
    )
