"""Estudo de formato de contexto: casos sintéticos, prompts e harness em dry-run.

Pergunta do estudo (protocolo em
``docs/planejamento/apoios-modulo-07/estudo-formato-contexto.md``): qual modelo ×
quantização × formato de contexto acha, entre as propriedades nativas de um elemento
estrutural, a que é sinônima do conceito pedido (fck, cobrimento nominal, CAA) e
devolve valor + unidade padronizada — ou se abstém quando deve.

Três partes, todas SEM inferência:

1. **Gerador determinístico** de casos sintéticos com gabarito: nomes de propriedade
   variados por "exportador", unidades variadas (Pa, MPa, kN/cm², kgf/cm², classe
   C25/30, sem unidade), distratores (fcd, fct, volume), casos de abstenção e de
   conflito. Mesma semente → mesmos bytes.
2. **Montagem de prompt** em quatro formatos (JSON indentado, JSON compacto, Markdown,
   tabela), com contexto inteiro ou recuperado e instrução em PT ou EN; contagem
   APROXIMADA de tokens (caracteres ÷ 4; não é o tokenizer do modelo).
3. **Harness**: valida a resposta contra o JSON Schema de saída e pontua contra o
   gabarito. Em ``dry_run`` a resposta é simulada (oráculo ou perturbação
   determinística) só para exercitar o código. O modo real fica BLOQUEADO
   (``RealModeBlocked``) até autorização explícita (M7-10); este módulo não
   importa cliente de LLM nem abre conexão.

Os valores de referência dos conceitos (classes C20–C50, cobrimentos por CAA) seguem a
NBR 6118/NBR 8953 como vocabulário de domínio; os casos são fixtures de software, não
casos científicos reais (plano M7 §4).
"""

from __future__ import annotations

import json
import random
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from statistics import mean
from typing import Any, Final, Literal

import jsonschema  # travado no uv.lock via mcp/streamlit
from pydantic import BaseModel, ConfigDict, Field

from src.experiment.budget_v1.provisional_dictionary import Vocabulary, load_vocabulary

GENERATOR_VERSION: Final = "formato-contexto-gerador/2"  # /2: vocabulário lido do dicionário
HARNESS_VERSION: Final = "formato-contexto-harness/1"
# Saída padrão: ignorada pelo git (.gitignore). Base provisória até a área operacional M6.
DEFAULT_OUT: Final = Path("research") / "M7" / "estudo-formato-contexto"

Concept = Literal["fck", "cobrimento", "caa"]
CaseKind = Literal[
    "direto",  # valor já na unidade padrão
    "conversao",  # unidade diferente da padrão
    "unidade_no_nome",  # unidade só no nome da propriedade ("FCK (MPa)")
    "classe",  # classe de resistência (C25, C25/30) → fck
    "abstencao_ausente",  # conceito ausente (só distratores, inclusive fcd)
    "abstencao_sem_unidade",  # número sem unidade declarada
    "conflito",  # duas propriedades do conceito com valores diferentes
]
ContextFormat = Literal["json_indentado", "json_compacto", "markdown", "tabela"]
ContextScope = Literal["inteiro", "recuperado"]
Language = Literal["pt", "en"]

# Vocabulário (grafias, unidades, conversões, classes, tabelas) vem do dicionário provisório
# data/dicionario_provisorio/conceitos-estruturais.json; nada disso fica fixo no código.
VOCAB: Final[Vocabulary] = load_vocabulary()
CONCEPTS: Final[tuple[Concept, ...]] = ("fck", "cobrimento", "caa")
if set(VOCAB.concepts) != set(CONCEPTS):  # o estudo cobre exatamente estes três conceitos
    raise ValueError(f"dicionário com conceitos inesperados: {VOCAB.concepts}")
FORMATS: Final[tuple[ContextFormat, ...]] = (
    "json_indentado",
    "json_compacto",
    "markdown",
    "tabela",
)
SCOPES: Final[tuple[ContextScope, ...]] = ("inteiro", "recuperado")
LANGUAGES: Final[tuple[Language, ...]] = ("pt", "en")
TARGET_UNIT: Final[dict[str, str | None]] = VOCAB.target_unit
KGF_CM2_IN_MPA: Final = VOCAB.conversions["MPa"]["kgf/cm²"]
COVER_BY_CAA: Final[dict[str, dict[str, int]]] = VOCAB.cover_by_caa
VALUE_TOLERANCE: Final = 0.01  # relativa, para comparar números convertidos


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NativeProperty(_Model):
    """Propriedade como o exportador a escreveu (nome, Pset, valor, unidade declarada)."""

    pset: str
    name: str
    value: float | int | str
    unit: str | None = None


class GoldAnswer(_Model):
    """Gabarito: valor padronizado e a propriedade de origem, ou abstenção com motivo."""

    outcome: Literal["valor", "abstencao"]
    source: str | None = None  # "Pset.Nome" da propriedade nativa sinônima
    value: float | str | None = None
    unit: str | None = None
    reason: Literal["ausente", "unidade_desconhecida", "conflito"] | None = None


class SyntheticCase(_Model):
    """Elemento estrutural sintético com propriedades nativas e gabarito."""

    case_id: str
    generator: str = GENERATOR_VERSION
    seed: int
    exporter: str
    ifc_class: str
    element_name: str
    concept: Concept
    kind: CaseKind
    properties: list[NativeProperty]
    gold: GoldAnswer


class ModelOutput(_Model):
    """Saída esperada do modelo (fonte do JSON Schema enviado no prompt)."""

    resultado: Literal["valor", "abstencao"]
    propriedade_origem: str | None = Field(description="Pset.Nome da propriedade usada")
    valor: float | str | None
    unidade: Literal["MPa", "mm"] | None
    motivo: Literal["ausente", "unidade_desconhecida", "conflito"] | None


def output_json_schema() -> dict[str, Any]:
    """JSON Schema (2020-12) da saída, gerado do modelo pydantic."""
    schema = ModelOutput.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return schema


# --- distratores e armadilhas -------------------------------------------------------

# Propriedades sem relação com os conceitos (ruído do exportador).
DISTRACTORS: Final[list[tuple[str, Any, str | None]]] = [
    ("Volume", 0.36, "m3"),
    ("Peso específico", 25.0, "kN/m3"),
    ("Aço", "CA-50", None),
    ("Comprimento", 3.0, "m"),
    ("Módulo de elasticidade", 28000.0, "MPa"),
]
ELEMENTS: Final[list[tuple[str, str]]] = [
    ("IfcColumn", "P{n}"),
    ("IfcBeam", "V{n}"),
    ("IfcSlab", "L{n}"),
    ("IfcFooting", "S{n}"),
]


def _trap_value(term: str, fck: int) -> tuple[Any, str | None]:
    """Valor plausível de um não-sinônimo do dicionário (fcd, fct,m, ExposureClass)."""
    if term == "fcd":
        return _round(fck / 1.4, 2), "MPa"  # fcd = fck / γc, γc = 1,4
    if term.startswith("fct"):
        return _round(0.3 * fck ** (2 / 3), 2), "MPa"
    return "XC2", None  # classe de exposição EN 206


def _round(value: float, digits: int = 4) -> float:
    return float(round(value, digits))


def _fck_written(
    rng: random.Random, fck: int, kind: CaseKind, vocab: Vocabulary
) -> tuple[Any, str | None]:
    """Valor e unidade do fck como o exportador escreveria, para o tipo de caso.

    Conflito usa a unidade padrão: o único motivo de abstenção deve ser o conflito.
    """
    target = vocab.target_unit["fck"]
    if kind in ("direto", "conflito"):
        return float(fck), target
    if kind == "conversao":
        factors = vocab.conversions[str(target)]
        unit = rng.choice(sorted(u for u in factors if u != target))
        return _round(fck / factors[unit], 2), unit
    if kind == "classe":
        # NBR (C25), Eurocódigo (C25/30) e a grafia da fonte Daiane (C-25, A8-013).
        return rng.choice([f"C{fck}", f"C{fck}/{vocab.cube_of[fck]}", f"C-{fck}"]), None
    return float(fck), None  # unidade_no_nome / abstencao_sem_unidade


def _cover_written(
    rng: random.Random, cover_mm: int, kind: CaseKind, vocab: Vocabulary
) -> tuple[Any, str | None]:
    target = vocab.target_unit["cobrimento"]
    if kind in ("direto", "conflito"):
        return cover_mm, target
    if kind == "conversao":
        factors = vocab.conversions[str(target)]
        unit = rng.choice(sorted(u for u in factors if u != target))
        return _round(cover_mm / factors[unit], 4), unit
    return cover_mm, None


def _kinds_for(concept: Concept) -> list[CaseKind]:
    common: list[CaseKind] = ["direto", "abstencao_ausente", "conflito"]
    if concept == "fck":
        return [*common, "conversao", "unidade_no_nome", "classe", "abstencao_sem_unidade"]
    if concept == "cobrimento":
        return [*common, "conversao", "unidade_no_nome", "abstencao_sem_unidade"]
    return common  # CAA é categórica: sem unidade por natureza


def _pick_name(
    rng: random.Random, names: list[str], kind: CaseKind, unit: str | None, vocab: Vocabulary
) -> str:
    """Nome do portador coerente com o tipo: classe só para aliases do binding de derivação
    (StrengthClass); unidade no nome só quando o caso pede."""
    with_unit = [n for n in names if "(" in n]
    without = [n for n in names if "(" not in n and n not in vocab.class_terms]
    if kind == "unidade_no_nome":
        return rng.choice(with_unit) if with_unit else f"{rng.choice(without or names)} ({unit})"
    if kind == "classe":
        classy = [n for n in names if n in vocab.class_terms]
        return rng.choice(classy or names)
    return rng.choice(without or names)


def generate_case(
    seed: int, index: int, concept: Concept, kind: CaseKind, vocab: Vocabulary = VOCAB
) -> SyntheticCase:
    """Um caso determinístico (mesmos argumentos e dicionário → mesmo caso)."""
    rng = random.Random(f"{seed}:{index}:{concept}:{kind}")
    exporter = rng.choice(sorted(vocab.exporters))
    terms = vocab.exporters[exporter]
    ifc_class, pattern = rng.choice(ELEMENTS)
    element_name = pattern.format(n=rng.randint(1, 40))
    pset = terms["pset"]
    caa = rng.choice(sorted(vocab.cover_by_caa))
    cover = vocab.cover_by_caa[caa]["laje" if ifc_class == "IfcSlab" else "viga_pilar"]
    fck = rng.choice(vocab.fck_classes)

    props: list[NativeProperty] = [
        NativeProperty(pset=pset, name=n, value=v, unit=u) for n, v, u in rng.sample(DISTRACTORS, 3)
    ]
    gold: GoldAnswer
    target_unit = vocab.target_unit[concept]

    if kind == "abstencao_ausente":
        # Não-sinônimo do dicionário (fcd para fck, ExposureClass para CAA) como armadilha.
        for term in vocab.non_synonyms.get(concept, ())[:1]:
            trap, trap_unit = _trap_value(term, fck)
            props.append(NativeProperty(pset=pset, name=term, value=trap, unit=trap_unit))
        gold = GoldAnswer(outcome="abstencao", reason="ausente")
    else:
        name = _pick_name(rng, terms[concept], kind, target_unit, vocab)
        if concept == "fck":
            value, unit = _fck_written(rng, fck, kind, vocab)
            gold_value: float | str = float(fck)
        elif concept == "cobrimento":
            value, unit = _cover_written(rng, cover, kind, vocab)
            gold_value = float(cover)
        else:
            value, unit = rng.choice(vocab.caa_written[caa]), None
            gold_value = caa
        props.append(NativeProperty(pset=pset, name=name, value=value, unit=unit))
        source = f"{pset}.{name}"
        if kind == "abstencao_sem_unidade":
            gold = GoldAnswer(outcome="abstencao", reason="unidade_desconhecida")
        elif kind == "conflito":
            other_pset = f"{pset} (tipo)"
            if concept == "fck":
                other: Any = float(rng.choice([c for c in vocab.fck_classes if c != fck]))
            elif concept == "cobrimento":
                other = float(cover) + 10
            else:
                other = rng.choice([k for k in vocab.caa_written if k != caa])
            props.append(NativeProperty(pset=other_pset, name=name, value=other, unit=unit))
            gold = GoldAnswer(outcome="abstencao", reason="conflito")
        else:
            gold = GoldAnswer(outcome="valor", source=source, value=gold_value, unit=target_unit)

    rng.shuffle(props)
    return SyntheticCase(
        case_id=f"{concept}-{kind}-{index:04d}",
        seed=seed,
        exporter=exporter,
        ifc_class=ifc_class,
        element_name=element_name,
        concept=concept,
        kind=kind,
        properties=props,
        gold=gold,
    )


def generate_cases(
    seed: int = 20261028, per_kind: int = 4, vocab: Vocabulary = VOCAB
) -> list[SyntheticCase]:
    """Conjunto balanceado: ``per_kind`` casos para cada (conceito, tipo) admissível."""
    cases: list[SyntheticCase] = []
    index = 0
    for concept in CONCEPTS:
        for kind in _kinds_for(concept):
            for _ in range(per_kind):
                cases.append(generate_case(seed, index, concept, kind, vocab))
                index += 1
    return cases


def write_jsonl(cases: Iterable[BaseModel], path: Path) -> Path:
    """Grava um objeto por linha (UTF-8, LF, chaves ordenadas pelo modelo)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for case in cases:
            handle.write(case.model_dump_json() + "\n")
    return path


def read_jsonl(path: Path) -> list[SyntheticCase]:
    """Lê casos gravados por ``write_jsonl``."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [SyntheticCase.model_validate_json(line) for line in lines if line.strip()]


# --- recuperação e formatos ----------------------------------------------------------

# Termos genéricos do conceito = aliases ``search`` do dicionário (natureza legítima de
# estímulo: tipologia/schema), usados só pela recuperação lexical.
RETRIEVE_TOP_K: Final = 3


def _norm(text: str) -> str:
    ascii_text = unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()


def retrieve(
    case: SyntheticCase, k: int = RETRIEVE_TOP_K, vocab: Vocabulary = VOCAB
) -> list[NativeProperty]:
    """Recuperação lexical determinística: termos do conceito no nome/Pset; empate pela ordem."""
    terms = vocab.search_terms[case.concept]

    def score(prop: NativeProperty) -> int:
        words = set(_norm(f"{prop.pset} {prop.name}").split())
        return sum(1 for t in terms if t in words)

    ranked = sorted(enumerate(case.properties), key=lambda ip: (-score(ip[1]), ip[0]))
    return [p for _, p in ranked[:k]]


def _rows(props: Sequence[NativeProperty]) -> list[dict[str, Any]]:
    return [{"pset": p.pset, "nome": p.name, "valor": p.value, "unidade": p.unit} for p in props]


def render_context(case: SyntheticCase, fmt: ContextFormat, scope: ContextScope) -> str:
    """Bloco de contexto do elemento no formato pedido."""
    props = case.properties if scope == "inteiro" else retrieve(case)
    head = {"classe": case.ifc_class, "nome": case.element_name}
    rows = _rows(props)
    if fmt == "json_indentado":
        return json.dumps({"elemento": head, "propriedades": rows}, ensure_ascii=False, indent=2)
    if fmt == "json_compacto":
        return json.dumps(
            {"elemento": head, "propriedades": rows}, ensure_ascii=False, separators=(",", ":")
        )
    unit = lambda r: r["unidade"] if r["unidade"] is not None else "—"  # noqa: E731
    if fmt == "markdown":
        lines = [f"## {case.ifc_class} {case.element_name}", ""]
        lines += [f"- **{r['pset']}.{r['nome']}**: {r['valor']} ({unit(r)})" for r in rows]
        return "\n".join(lines)
    lines = [
        f"{case.ifc_class} {case.element_name}",
        "| Pset | Nome | Valor | Unidade |",
        "|---|---|---|---|",
    ]
    lines += [f"| {r['pset']} | {r['nome']} | {r['valor']} | {unit(r)} |" for r in rows]
    return "\n".join(lines)


_UNIT_WORDS: Final[dict[Language, tuple[str, str]]] = {
    "pt": ("em", "um dos códigos"),
    "en": ("in", "one of the codes"),
}


def concept_label(concept: Concept, language: Language, vocab: Vocabulary = VOCAB) -> str:
    """Rótulo do conceito no prompt, montado do dicionário: label + unidade ou códigos."""
    label = vocab.labels[concept].get(language) or vocab.labels[concept]["pt"]
    unit_word, codes_word = _UNIT_WORDS[language]
    unit = vocab.target_unit[concept]
    if unit:
        return f"{label}, {unit_word} {unit}"
    return f"{label}, {codes_word} {', '.join(vocab.codes.get(concept, ()))}"


_INSTRUCTION: Final[dict[Language, str]] = {
    "pt": (
        "Entre as propriedades do elemento abaixo, encontre a que corresponde a: {label}. "
        "Devolva o valor convertido para a unidade pedida e a propriedade de origem (Pset.Nome). "
        "Abstenha-se se nenhuma propriedade corresponder, se a unidade não estiver declarada "
        "ou se houver valores conflitantes. Responda só com JSON válido neste schema:\n{schema}"
    ),
    "en": (
        "Among the element properties below, find the one that corresponds to: {label}. "
        "Return the value converted to the requested unit and the source property (Pset.Name). "
        "Abstain if no property matches, if the unit is not declared, or if values conflict. "
        "Reply only with valid JSON in this schema:\n{schema}"
    ),
}


def build_prompt(
    case: SyntheticCase, fmt: ContextFormat, scope: ContextScope, language: Language
) -> str:
    """Prompt completo: instrução + schema compacto + contexto. Nunca contém o gabarito."""
    schema = json.dumps(output_json_schema(), ensure_ascii=False, separators=(",", ":"))
    instruction = _INSTRUCTION[language].format(
        label=concept_label(case.concept, language), schema=schema
    )
    return f"{instruction}\n\n{render_context(case, fmt, scope)}"


def approx_tokens(text: str) -> int:
    """Tokens APROXIMADOS (caracteres ÷ 4, arredondado para cima); não é o tokenizer real."""
    return -(-len(text) // 4)


# --- validação e pontuação -----------------------------------------------------------

_VALIDATOR = jsonschema.Draft202012Validator(output_json_schema())


def parse_output(raw: str) -> tuple[ModelOutput | None, str | None]:
    """JSON da resposta → saída validada pelo JSON Schema, ou o motivo da recusa."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"json_invalido: {exc.msg}"
    errors = sorted(_VALIDATOR.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        return None, f"schema: {errors[0].message}"
    return ModelOutput.model_validate(data), None


def _same_value(got: float | str | None, want: float | str | None) -> bool:
    if isinstance(want, str) or isinstance(got, str):
        return str(got).strip().upper() == str(want).strip().upper()
    if got is None or want is None:
        return False
    return abs(float(got) - float(want)) <= VALUE_TOLERANCE * max(1.0, abs(float(want)))


class Score(_Model):
    """Pontuação de uma resposta contra o gabarito."""

    json_valido: bool
    erro_schema: str | None = None
    acerto_top1: bool = False  # valor + unidade + origem corretos (casos com valor)
    abstencao_correta: bool = False  # abstenção pedida e dada (o motivo é informativo)
    abstencao_indevida: bool = False
    proposta_indevida: bool = False  # valor quando o gabarito pede abstenção
    erro_unidade: bool = False  # origem certa, unidade errada ou valor fora por fator de unidade
    motivo_abstencao_correto: bool | None = None


def score(case: SyntheticCase, raw: str) -> Score:
    """Compara uma resposta bruta ao gabarito do caso."""
    out, error = parse_output(raw)
    if out is None:
        return Score(json_valido=False, erro_schema=error)
    gold = case.gold
    if gold.outcome == "abstencao":
        if out.resultado == "abstencao":
            return Score(
                json_valido=True,
                abstencao_correta=True,
                motivo_abstencao_correto=out.motivo == gold.reason,
            )
        return Score(json_valido=True, proposta_indevida=True)
    if out.resultado == "abstencao":
        return Score(json_valido=True, abstencao_indevida=True)
    source_ok = out.propriedade_origem == gold.source
    value_ok = _same_value(out.valor, gold.value)
    unit_ok = out.unidade == gold.unit
    return Score(
        json_valido=True,
        acerto_top1=source_ok and value_ok and unit_ok,
        erro_unidade=source_ok and not (value_ok and unit_ok),
    )


# --- respostas simuladas e harness ---------------------------------------------------

Simulator = Literal["oraculo", "ruidoso"]


def simulated_response(case: SyntheticCase, simulator: Simulator, salt: str = "") -> str:
    """Resposta simulada para o dry-run. ``oraculo`` repete o gabarito; ``ruidoso`` erra de
    forma determinística (JSON quebrado, unidade errada, abstenção/proposta indevida)."""
    gold = case.gold
    perfect = {
        "resultado": gold.outcome,
        "propriedade_origem": gold.source,
        "valor": gold.value,
        "unidade": gold.unit,
        "motivo": gold.reason,
    }
    if simulator == "oraculo":
        return json.dumps(perfect, ensure_ascii=False)
    roll = random.Random(f"{case.case_id}:{salt}").random()
    if roll < 0.10:
        return '{"resultado": "valor", "valor": '  # truncado
    if roll < 0.20 and gold.outcome == "valor" and isinstance(gold.value, float):
        return json.dumps({**perfect, "valor": gold.value * 1000})  # fator de unidade
    if roll < 0.30:
        flipped = (
            {
                **perfect,
                "resultado": "abstencao",
                "valor": None,
                "unidade": None,
                "motivo": "ausente",
            }
            if gold.outcome == "valor"
            else {
                **perfect,
                "resultado": "valor",
                "propriedade_origem": "X.Y",
                "valor": 1.0,
                "unidade": "MPa",
                "motivo": None,
            }
        )
        return json.dumps(flipped)
    return json.dumps(perfect, ensure_ascii=False)


class RealModeBlocked(RuntimeError):
    """O modo real (inferência) não está autorizado nesta etapa."""


REAL_MODE_AUTHORIZED: Final = False
"""Só muda por decisão registrada (M7-10, autorização de ensaio). Não há cliente de LLM aqui."""


def require_dry_run(mode: str) -> None:
    """Recusa qualquer modo diferente de ``dry_run`` enquanto não houver autorização."""
    if mode != "dry_run" or REAL_MODE_AUTHORIZED:
        raise RealModeBlocked(
            "modo real bloqueado: inferência exige autorização registrada (plano M7-10); "
            "este harness só roda em --dry-run"
        )


class CellReport(_Model):
    """Agregado de uma célula formato × escopo × idioma × simulador."""

    formato: ContextFormat
    escopo: ContextScope
    idioma: Language
    simulador: Simulator
    casos: int
    tokens_medio: float
    tokens_max: int
    json_valido: float
    acerto_top1: float | None  # sobre casos com valor
    abstencao_correta: float | None  # sobre casos de abstenção
    proposta_indevida: int
    erro_unidade: int
    recuperacao_cobre_gabarito: float | None  # escopo recuperado: origem do gabarito entre os k
    latencia_ms: None = None  # só no modo real
    vram_mib: None = None  # só no modo real


def _ratio(hits: int, total: int) -> float | None:
    return None if total == 0 else round(hits / total, 4)


def run_dry(
    cases: Sequence[SyntheticCase],
    formats: Sequence[ContextFormat] = FORMATS,
    scopes: Sequence[ContextScope] = SCOPES,
    languages: Sequence[Language] = LANGUAGES,
    simulators: Sequence[Simulator] = ("oraculo", "ruidoso"),
) -> list[CellReport]:
    """Monta todos os prompts, conta tokens e pontua respostas simuladas por célula."""
    require_dry_run("dry_run")
    reports: list[CellReport] = []
    for fmt in formats:
        for scope in scopes:
            for language in languages:
                tokens = [approx_tokens(build_prompt(c, fmt, scope, language)) for c in cases]
                with_value = [c for c in cases if c.gold.outcome == "valor"]
                covered = sum(
                    1
                    for c in with_value
                    if c.gold.source in {f"{p.pset}.{p.name}" for p in retrieve(c)}
                )
                for simulator in simulators:
                    salt = f"{fmt}:{scope}:{language}"
                    scores = [score(c, simulated_response(c, simulator, salt)) for c in cases]
                    by_case = list(zip(cases, scores, strict=True))
                    reports.append(
                        CellReport(
                            formato=fmt,
                            escopo=scope,
                            idioma=language,
                            simulador=simulator,
                            casos=len(cases),
                            tokens_medio=round(mean(tokens), 1) if tokens else 0.0,
                            tokens_max=max(tokens, default=0),
                            json_valido=_ratio(sum(s.json_valido for s in scores), len(scores))
                            or 0.0,
                            acerto_top1=_ratio(
                                sum(s.acerto_top1 for c, s in by_case if c.gold.outcome == "valor"),
                                len(with_value),
                            ),
                            abstencao_correta=_ratio(
                                sum(
                                    s.abstencao_correta
                                    for c, s in by_case
                                    if c.gold.outcome == "abstencao"
                                ),
                                len(cases) - len(with_value),
                            ),
                            proposta_indevida=sum(s.proposta_indevida for s in scores),
                            erro_unidade=sum(s.erro_unidade for s in scores),
                            recuperacao_cobre_gabarito=_ratio(covered, len(with_value))
                            if scope == "recuperado"
                            else None,
                        )
                    )
    return reports


def summarize_cases(cases: Sequence[SyntheticCase]) -> dict[str, dict[str, int]]:
    """Contagem de casos por conceito × tipo (para o relatório)."""
    table: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for c in cases:
        table[c.concept][c.kind] += 1
    return {k: dict(v) for k, v in table.items()}


_REPORT_COLUMNS: Final = (
    "Formato", "Escopo", "Idioma", "Simulador", "Tokens médio", "Tokens máx", "JSON válido",
    "Top-1", "Abstenção correta", "Proposta indevida", "Erro de unidade", "Recuperação cobre",
)  # fmt: skip


def write_report(
    cases: Sequence[SyntheticCase], reports: Sequence[CellReport], out_dir: Path
) -> tuple[Path, Path]:
    """Relatório JSON (máquina) e Markdown (leitura) do dry-run."""
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "harness": HARNESS_VERSION,
        "generator": GENERATOR_VERSION,
        "mode": "dry_run",
        "aviso": "respostas SIMULADAS; números servem para testar o código, não medem modelos",
        "tokens": "aproximados (caracteres / 4)",
        "casos": summarize_cases(cases),
        "schema_saida": output_json_schema(),
        "celulas": [r.model_dump() for r in reports],
    }
    json_path = out_dir / "relatorio-dry-run.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Estudo de formato de contexto — relatório do dry-run",
        "",
        "> Respostas **simuladas** (oráculo e perturbação determinística). Os números testam o",
        "> harness; não medem nenhum modelo. Tokens aproximados (caracteres ÷ 4).",
        "",
        f"Casos: {len(cases)} — "
        + "; ".join(f"{k}: {sum(v.values())}" for k, v in summarize_cases(cases).items()),
        "",
        "| " + " | ".join(_REPORT_COLUMNS) + " |",
        "|" + "---|" * len(_REPORT_COLUMNS),
    ]
    fmt = lambda v: "—" if v is None else str(v)  # noqa: E731
    for r in reports:
        cells = [
            r.formato, r.escopo, r.idioma, r.simulador, r.tokens_medio, r.tokens_max, r.json_valido,
            fmt(r.acerto_top1), fmt(r.abstencao_correta), r.proposta_indevida, r.erro_unidade,
            fmt(r.recuperacao_cobre_gabarito),
        ]  # fmt: skip
        lines.append("| " + " | ".join(str(c) for c in cells) + " |")
    md_path = out_dir / "relatorio-dry-run.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path
