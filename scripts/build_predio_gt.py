"""Construtor do ground truth candidato do prédio (protocolo norm-derived-draft).

Deriva o GT das 2792 issues do ``predio_v1.ifc`` **sem nenhuma participação de
LLM** (guardrail anti-circularidade C.0), a partir de quatro fontes
determinísticas, nesta ordem de preferência:

1. **Propagação por tipo** — instâncias do mesmo tipo Revit que já têm a
   propriedade preenchida no próprio modelo (autoria do projetista);
2. **Cálculo normativo** — transmitância térmica pela NBR 15220-2 (camadas
   conhecidas do tipo: λ concreto 1,75; argamassa 1,15; gesso acartonado 0,35;
   cerâmica 1,05 W/(m·K); câmara de ar não ventilada R=0,17; Rsi/Rse 0,13/0,04
   horizontal e 0,17/0,04 fluxo descendente);
3. **Tabela normativa** — TRRF pela NBR 14432 Tabela A.1: ocupação residencial
   (grupo A-2), altura do último piso habitável 12,4 m → classe P3
   (12 < h ≤ 23 m) → **TRRF 60 min**;
4. **Mapeamento fechado** — Category por LongName do espaço; LoadBearing por
   semântica da classe/tipo; sistema construtivo pelas camadas/nome do tipo.

Toda entrada sai com ``verified: false`` + justificativa e referência em
``notes``. O YAML resultante **não é padrão-ouro** até a revisão humana item a
item (C.2 passo 4). Issues sem derivação defensável ficam em ``skipped`` com
motivo — abstenção é preferível a chute também no GT.

Uso:

    python scripts/build_predio_gt.py
"""

from __future__ import annotations

import statistics
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import ifcopenshell.util.element as ue
from loguru import logger

from src.experiment.evaluator import GroundTruth, GroundTruthItem
from src.experiment.gt_extractor import (
    GTExtractionResult,
    SkippedIssue,
    write_ground_truth_yaml,
)
from src.models import Issue
from src.pipeline import QualityPipeline

IFC_PATH = PROJECT_ROOT / "data" / "evaluation" / "predio" / "predio_v1.ifc"
IDS_PATH = PROJECT_ROOT / "data" / "ids_templates" / "residencial_nbr15575.ids"
OUTPUT_YAML = PROJECT_ROOT / "data" / "evaluation" / "predio" / "ground_truth.yaml"
OUTPUT_REVIEW = PROJECT_ROOT / "data" / "evaluation" / "predio" / "REVISAO_GT.md"

BUILDING_CONTEXT = {"building_type": "Residencial multifamiliar", "bioclimatic_zone": "3"}

# TRRF do prédio: NBR 14432 Tab. A.1, grupo A-2 (residencial), último piso
# habitável a 12,4 m → classe P3 (12 < h ≤ 23 m) → 60 min. Subsolo único
# (−3,1 m) mantém 60 min para A-2.
TRRF_REF = "NBR 14432:2001 Tab. A.1 (A-2, P3: 12<h≤23 m) → TRRF 60 min"

# ---------------------------------------------------------------------------
# Regras por tipo (paredes, lajes, portas) — chave: substring do nome do tipo
# ---------------------------------------------------------------------------

# FireRating por tipo. None = sem exigência/derivação defensável → skip.
FIRE_RULES: list[tuple[str, str | None, list[str], str]] = [
    # (substring do tipo, expected, alternativas, nota)
    (
        "parede interna 20cm",
        "REI 60",
        ["REI 90", "REI 120"],
        f"Alvenaria 16 cm + revestimentos, compartimentação: {TRRF_REF}. "
        "Desempenho provável do sistema ≥ 90 min (IT-08 CBPMESP Tab. paredes).",
    ),
    (
        "Parede externa 20cm",
        "REI 60",
        ["REI 90", "REI 120"],
        f"Alvenaria de bloco de concreto 15 cm + revestimentos: {TRRF_REF}.",
    ),
    (
        "Dry-Wall 10cm",
        "EI 30",
        ["EI 30", "REI 30"],
        "Drywall chapa simples ST 15 mm cada face ≈ EI 30 (catálogos "
        "Gypsum/Knauf; IT-08). Não portante (LoadBearing=false no modelo). "
        "ATENÇÃO: tipo marcado IsExternal=true no modelo — conferir.",
    ),
    (
        "laje de concreto",
        "REI 60",
        ["REI 90"],
        f"Laje maciça ≥ 10 cm de concreto, compartimentação entre pavimentos: {TRRF_REF}.",
    ),
    ("Patamar monolítico", "REI 60", ["REI 90"], f"Patamar estrutural de escada: {TRRF_REF}."),
    (
        "Porta Corta Fogo",
        "EI 30",
        ["EI 60", "P-CF 30"],
        "Porta corta-fogo de escada (NBR 11742): P-CF 30 usual para escada "
        "protegida em residencial P3; conferir projeto de incêndio.",
    ),
    (
        "Pilar retangular - concreto",
        "R 60",
        ["REI 60", "R 90"],
        f"Pilar de concreto armado, elemento estrutural (critério R): {TRRF_REF}. "
        "Dimensionamento em incêndio pela NBR 15200.",
    ),
    (
        "Escada moldada no local",
        "REI 60",
        ["R 60", "REI 90"],
        f"Escada monolítica de concreto — estrutural e rota de fuga: {TRRF_REF}. "
        "CONFERIR exigência específica de escada no projeto de incêndio (IT-11).",
    ),
]

# Tipos sem exigência de resistência ao fogo → skip documentado.
FIRE_SKIP: list[tuple[str, str]] = [
    ("Telhado", "cobertura de fibrocimento sem função de compartimentação (NBR 14432 §isenções)"),
    ("asfalto", "pavimentação externa sem função de compartimentação"),
    ("grama", "revestimento paisagístico sem função de compartimentação"),
    ("calçada", "pavimentação externa sem função de compartimentação"),
    ("Calçada", "pavimentação externa sem função de compartimentação"),
    ("Intertravado", "pavimentação externa sem função de compartimentação"),
]

# ThermalTransmittance calculada (NBR 15220-2) quando não há propagação por tipo.
# Camadas conhecidas do tipo (inspeção de 2026-07-02) e memória de cálculo na nota.
THERMAL_CALC: list[tuple[str, float, str]] = [
    (
        "Dry-Wall 10cm",
        2.35,
        "NBR 15220-2: Rsi 0,13 + gesso 0,015/0,35 + câmara não ventilada 0,17 "
        "+ gesso 0,015/0,35 + Rse 0,04 = 0,426 m²K/W → U=2,35 W/(m²·K).",
    ),
    (
        "laje de concreto + piso genérico 20cm",
        2.93,
        "NBR 15220-2, fluxo descendente: Rsi 0,17 + piso 0,02/1,05 + regularização "
        "0,03/1,15 + concreto 0,15/1,75 + Rse 0,04 = 0,341 → U=2,93 W/(m²·K).",
    ),
    (
        "laje de concreto",
        3.20,
        "NBR 15220-2, fluxo descendente: Rsi 0,17 + piso 0,02/1,05 + regularização "
        "0,03/1,15 + concreto 0,10/1,75 + Rse 0,04 = 0,312 → U=3,20 W/(m²·K).",
    ),
    (
        "Patamar monolítico",
        3.08,
        "NBR 15220-2, fluxo descendente: Rsi 0,17 + concreto 0,20/1,75 + Rse 0,04 "
        "= 0,324 m²K/W → U=3,08 W/(m²·K).",
    ),
    (
        "Telhado",
        4.60,
        "Telha de fibrocimento sem forro: U≈4,6 W/(m²·K) (NBR 15575-5 / LabEEE, "
        "valor consagrado para cobertura leve sem forro).",
    ),
    (
        "Janela",
        5.70,
        "Esquadria com vidro simples: U≈5,7 W/(m²·K) (valor de referência "
        "NBR 15575-4 / catálogos de esquadrias) — CONFERIR tipo de vidro.",
    ),
    (
        "Vitrine",
        5.70,
        "Fachada/divisória envidraçada com vidro simples: U≈5,7 W/(m²·K) — "
        "CONFERIR composição.",
    ),
    (
        "divisória de vidro",
        5.70,
        "Divisória de vidro simples: U≈5,7 W/(m²·K) — CONFERIR composição.",
    ),
    (
        "cobertura de vidro",
        5.70,
        "Vidraça com vidro simples: U≈5,7 W/(m²·K) — CONFERIR composição.",
    ),
]

THERMAL_SKIP: list[tuple[str, str]] = [
    ("asfalto", "pavimentação externa; transmitância térmica não aplicável ao escopo NBR 15575"),
    ("grama", "revestimento paisagístico; transmitância térmica não aplicável"),
    ("calçada", "pavimentação externa; transmitância térmica não aplicável"),
    ("Calçada", "pavimentação externa; transmitância térmica não aplicável"),
    ("Intertravado", "pavimentação externa; transmitância térmica não aplicável"),
    ("Terças", "elemento estrutural de cobertura; transmitância térmica não aplicável"),
    ("Caibros", "elemento estrutural de cobertura; transmitância térmica não aplicável"),
]

# Sistema construtivo por tipo (vocabulário canônico dos templates do projeto).
SYSTEM_RULES: list[tuple[str, str, list[str], str]] = [
    (
        "parede interna 20cm",
        "Alvenaria de vedação em bloco cerâmico",
        ["Alvenaria de vedação"],
        "Camada '.alvenaria deitado 18 cm' + massa corrida; material genérico no "
        "modelo — CONFERIR se bloco cerâmico ou de concreto.",
    ),
    (
        "Parede externa 20cm",
        "Alvenaria em bloco de concreto",
        ["Alvenaria de vedação em bloco de concreto"],
        "Camada 'Unidades de alvenaria de concreto' 15 cm no modelo.",
    ),
    (
        "Dry-Wall",
        "Drywall / Steel frame",
        ["Drywall"],
        "Gesso acartonado 15 mm + montantes metálicos 70 mm (camadas do modelo).",
    ),
    (
        "laje de concreto usinado",
        "Laje maciça de concreto armado",
        ["Laje maciça de concreto usinado"],
        "Camada '.concreto usinado' 10 cm.",
    ),
    (
        "laje de concreto",
        "Laje maciça de concreto armado",
        [],
        "Camada '.concreto genérico' ≥ 10 cm moldado in loco.",
    ),
    (
        "Patamar monolítico",
        "Laje maciça de concreto armado",
        [],
        "Patamar monolítico de escada em concreto.",
    ),
    (
        "grama",
        "Grama natural ou artificial",
        [],
        "Rótulo canônico do template de lajes do projeto.",
    ),
]

SYSTEM_SKIP: list[tuple[str, str]] = [
    ("Telhado", "cobertura de fibrocimento — rótulo fora do vocabulário canônico; decisão do revisor"),
    ("asfalto", "pavimentação asfáltica — rótulo fora do vocabulário canônico; decisão do revisor"),
    ("calçada", "calçada de concreto — rótulo fora do vocabulário canônico; decisão do revisor"),
    ("Calçada", "calçada de concreto — rótulo fora do vocabulário canônico; decisão do revisor"),
    ("Intertravado", "piso intertravado — rótulo fora do vocabulário canônico; decisão do revisor"),
]

# Category (Pset_SpaceCommon) por LongName — vocabulário fechado do template
# pset_missing_space_category. Substring-match em ordem: termos mais
# específicos (banheiro/lavatório) vêm ANTES de "suíte", para que
# "Banheiro Suíte" case como BATHROOM e não como BEDROOM.
CATEGORY_MAP: list[tuple[str, str, list[str], str]] = [
    ("banheiro", "BATHROOM", ["WC"], "Banheiro."),
    ("lavatório", "WC", ["BATHROOM"], "Lavabo/lavatório."),
    ("quarto", "BEDROOM", [], "Dormitório."),
    ("suíte", "BEDROOM", [], "Dormitório (suíte)."),
    ("sala de estar", "LIVING_ROOM", [], "Estar."),
    ("sala de jantar", "LIVING_ROOM", [], "Jantar integrado; vocabulário sem DINING."),
    ("cozinha", "KITCHEN", [], "Cozinha (inclui cozinha do salão de festas)."),
    ("hall de circulação", "CIRCULATION", [], "Circulação."),
    ("corredor", "CIRCULATION", [], "Circulação."),
    ("escadas de incêndio", "CIRCULATION", [], "Circulação vertical de emergência."),
    ("hall de entrada", "LOBBY", ["CIRCULATION"], "Acesso principal."),
    ("área de serviço", "SERVICE_AREA", [], "Serviço."),
    ("sacada", "BALCONY", [], "Sacada."),
    ("despensa", "STORAGE", [], "Armazenamento."),
    ("depósito geral", "STORAGE", [], "Armazenamento."),
    ("depósito de lixo", "STORAGE", ["TECHNICAL_AREA"], "Depósito condominial."),
    ("depósito de gás", "TECHNICAL_AREA", ["STORAGE"], "Central de GLP — área técnica."),
    ("medidores de luz", "TECHNICAL_AREA", [], "Área técnica."),
    ("casa de hidrômeros", "TECHNICAL_AREA", [], "Área técnica (hidrômetros)."),
    ("cisternas e casa de maquinas", "TECHNICAL_AREA", [], "Área técnica."),
    ("guarita", "OFFICE", ["LOBBY"], "Posto de trabalho da portaria — CONFERIR."),
    ("salão de festas", "MEETING_ROOM", ["LIVING_ROOM"], "Uso coletivo — CONFERIR."),
]

CATEGORY_SKIP_NOTE = "sem mapeamento inequívoco no vocabulário fechado; decisão do revisor"


# ---------------------------------------------------------------------------
# Motor de derivação
# ---------------------------------------------------------------------------


def _type_name_of(element) -> str:
    """Nome do tipo Revit do elemento (sem o sufixo numérico de instância)."""
    el_type = ue.get_type(element)
    name = (el_type.Name if el_type is not None else None) or element.ObjectType or element.Name or "?"
    parts = str(name).split(":")
    if len(parts) >= 2 and parts[-1].strip().isdigit():
        name = ":".join(parts[:-1])
    return str(name)


def _match(rules: list[tuple], type_name: str):
    """Primeira regra cujo substring casa com o nome do tipo (casefold)."""
    lowered = type_name.casefold()
    for rule in rules:
        if rule[0].casefold() in lowered:
            return rule
    return None


def _collect_type_thermal(model) -> dict[str, float]:
    """Mediana de ThermalTransmittance já preenchida por tipo (propagação)."""
    by_type: dict[str, list[float]] = {}
    for ifc_class in ("IfcWall", "IfcSlab"):
        for el in model.by_type(ifc_class):
            psets = ue.get_psets(el)
            common = psets.get(f"Pset_{ifc_class[3:]}Common") or {}
            value = common.get("ThermalTransmittance")
            if isinstance(value, (int, float)) and value > 0:
                by_type.setdefault(_type_name_of(el), []).append(float(value))
    return {t: round(statistics.median(vals), 4) for t, vals in by_type.items()}


def derive_item(
    issue: Issue,
    type_name: str,
    long_name: str | None,
    thermal_by_type: dict[str, float],
) -> GroundTruthItem | str:
    """Deriva o item de GT para a issue, ou retorna o motivo do skip (str)."""
    check_property = str(issue.context.get("check_property") or "")

    def item(expected, alternatives: list, note: str) -> GroundTruthItem:
        return GroundTruthItem(
            element_guid=issue.element_guid,
            issue_type=issue.issue_type,
            check_property=check_property,
            issue_id=issue.id,
            expected_value=expected,
            accepted_alternatives=alternatives,
            verified=False,
            notes=f"[{type_name}] {note}",
        )

    if issue.issue_type == "pset_missing" and check_property == "FireRating":
        skip = _match(FIRE_SKIP, type_name)
        if skip:
            return skip[1]
        rule = _match(FIRE_RULES, type_name)
        if rule:
            return item(rule[1], rule[2], rule[3])
        if issue.element_class.startswith(("IfcDoor", "IfcWindow")):
            return "porta/janela comum sem exigência de resistência ao fogo (NBR 14432); GT omitido"
        return "sem exigência de resistência ao fogo derivável para o tipo; decisão do revisor"

    if issue.issue_type == "pset_missing" and check_property == "ThermalTransmittance":
        skip = _match(THERMAL_SKIP, type_name)
        if skip:
            return skip[1]
        if type_name in thermal_by_type:
            return item(
                thermal_by_type[type_name],
                [],
                "Propagado de instâncias do mesmo tipo já preenchidas no modelo "
                "(mediana; autoria do projetista).",
            )
        rule = _match(THERMAL_CALC, type_name)
        if rule:
            return item(rule[1], [], rule[2])
        return "sem valor no modelo e sem memória de cálculo para o tipo; decisão do revisor"

    if issue.issue_type == "pset_missing" and check_property in ("LoadBearing", "IsLoadBearing"):
        if issue.element_class.startswith(("IfcColumn", "IfcBeam")):
            return item(True, [], "Elemento estrutural portante por definição (ISO 16739-1).")
        if "Patamar" in type_name:
            return item(True, [], "Patamar monolítico de escada é estrutural.")
        if "Telhado" in type_name:
            return item(False, [], "Telha de fibrocimento apoiada — não portante.")
        return "função estrutural ambígua para o tipo; decisão do revisor"

    if issue.issue_type == "pset_missing" and check_property == "Category":
        if not long_name:
            return "espaço sem LongName; decisão do revisor"
        rule = _match(CATEGORY_MAP, long_name)
        if rule:
            return item(rule[1], rule[2], f"LongName '{long_name}': {rule[3]}")
        return f"LongName '{long_name}' {CATEGORY_SKIP_NOTE}"

    if issue.issue_type == "system_unclassified":
        skip = _match(SYSTEM_SKIP, type_name)
        if skip:
            return skip[1]
        rule = _match(SYSTEM_RULES, type_name)
        if rule:
            return item(rule[1], rule[2], rule[3])
        return "tipo sem regra de sistema construtivo; decisão do revisor"

    return f"issue_type/propriedade fora do protocolo norm-derived ({issue.issue_type}/{check_property})"


def main() -> int:
    """Gera ground_truth.yaml (verified: false) + REVISAO_GT.md."""
    logger.info("build_predio_gt: abrindo modelo e diagnosticando…")
    pipeline = QualityPipeline(str(IFC_PATH), BUILDING_CONTEXT, ids_path=str(IDS_PATH))
    report = pipeline.diagnose()
    model = pipeline.ifc_file
    logger.info("build_predio_gt: {} issues", len(report.issues))

    thermal_by_type = _collect_type_thermal(model)
    logger.info("build_predio_gt: propagação térmica por tipo: {}", thermal_by_type)

    items: list[GroundTruthItem] = []
    skipped: list[SkippedIssue] = []
    element_cache: dict[str, tuple[str, str | None]] = {}

    for issue in report.issues:
        cached = element_cache.get(issue.element_guid)
        if cached is None:
            try:
                el = model.by_guid(issue.element_guid)
                cached = (_type_name_of(el), getattr(el, "LongName", None))
            except RuntimeError:
                cached = ("?", None)
            element_cache[issue.element_guid] = cached
        type_name, long_name = cached

        result = derive_item(issue, type_name, long_name, thermal_by_type)
        if isinstance(result, GroundTruthItem):
            items.append(result)
        else:
            skipped.append(
                SkippedIssue(
                    issue_id=issue.id,
                    element_guid=issue.element_guid,
                    issue_type=issue.issue_type,
                    check_property=str(issue.context.get("check_property") or ""),
                    reason=f"[{type_name}] {result}",
                )
            )

    ground_truth = GroundTruth(
        items=items,
        metadata={
            "protocol": "norm-derived-draft",
            "method": (
                "Derivação determinística sem LLM: propagação por tipo (valores já "
                "preenchidos pelo projetista no modelo), cálculo NBR 15220-2, TRRF "
                "NBR 14432 Tab. A.1 (A-2/P3 → 60 min), mapeamentos fechados. "
                "Guardrail C.0 preservado: a LLM avaliada não participou."
            ),
            "requires_human_review": True,
        },
    )
    result = GTExtractionResult(ground_truth=ground_truth, skipped=skipped)
    write_ground_truth_yaml(
        result, OUTPUT_YAML, input_ifc_path=IFC_PATH, ids_path=IDS_PATH
    )

    _write_review_doc(result)
    logger.info(
        "build_predio_gt: {} itens (verified:false), {} skips → {}",
        len(items),
        len(skipped),
        OUTPUT_YAML,
    )
    return 0


def _write_review_doc(result: GTExtractionResult) -> None:
    """Resumo agrupado por (tarefa, valor, nota) para revisão humana eficiente."""
    groups: Counter = Counter()
    for it in result.ground_truth.items:
        note = (it.notes or "").split("] ", 1)[-1]
        type_prefix = (it.notes or "").split("] ", 1)[0].lstrip("[")
        groups[(it.issue_type, it.check_property, str(it.expected_value), type_prefix, note)] += 1
    skips: Counter = Counter()
    for sk in result.skipped:
        reason = sk.reason.split("] ", 1)[-1]
        type_prefix = sk.reason.split("] ", 1)[0].lstrip("[")
        skips[(sk.issue_type, sk.check_property, type_prefix, reason)] += 1

    lines = [
        "# Revisão do Ground Truth candidato — prédio (norm-derived-draft)",
        "",
        "Gerado por `scripts/build_predio_gt.py` **sem participação de LLM**",
        "(propagação por tipo + NBR 15220-2 + NBR 14432 + mapeamentos fechados).",
        "",
        "**Como revisar:** cada linha abaixo agrupa itens idênticos (mesmo tipo,",
        "mesmo valor, mesma justificativa). Aprovar uma linha = aprovar todos os",
        "seus itens no `ground_truth.yaml` (trocar `verified: false` → `true`).",
        "Linhas marcadas com CONFERIR pedem atenção especial.",
        "",
        f"**Itens propostos:** {result.extracted_count} | **Skips:** {len(result.skipped)}",
        "",
        "## Itens propostos (agrupados)",
        "",
        "| Tarefa | Propriedade | Tipo/origem | Valor proposto | Qtde | Justificativa |",
        "|---|---|---|---|---|---|",
    ]
    for (task, prop, value, type_prefix, note), n in sorted(groups.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {task} | {prop or '—'} | {type_prefix} | `{value}` | {n} | {note} |")
    lines += [
        "",
        "## Issues sem GT (abstenção documentada)",
        "",
        "| Tarefa | Propriedade | Tipo/origem | Qtde | Motivo |",
        "|---|---|---|---|---|",
    ]
    for (task, prop, type_prefix, reason), n in sorted(skips.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {task} | {prop or '—'} | {type_prefix} | {n} | {reason} |")
    lines += [
        "",
        "## Referências",
        "",
        "- NBR 14432:2001 — Tab. A.1 (TRRF por ocupação/altura); prédio A-2, P3 → 60 min",
        "- NBR 15220-2 — propriedades térmicas e método de cálculo de U",
        "- NBR 15575-4/5:2021 — requisitos de desempenho (contexto dos limites)",
        "- IT-08 (CBPMESP) — resistência ao fogo de elementos construtivos",
        "- NBR 11742 — portas corta-fogo",
        "",
    ]
    OUTPUT_REVIEW.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
