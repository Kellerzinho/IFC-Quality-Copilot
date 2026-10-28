"""Dicionário provisório de conceitos estruturais (fck, cobrimento nominal, CAA).

PROVISÓRIO — aguardando o dicionário da Juliana / M1. O arquivo
``data/dicionario_provisorio/conceitos-estruturais.json`` aproxima o pacote
``ifcqc-catalog-package`` v1 do catálogo do Felipe (branch ``codex/m1-domain-catalog``):
mesmas chaves e campos em ``concepts``, ``units``, ``value_sets``, ``applicability_rules``,
``bindings``, ``aliases``, ``source_artifacts`` e ``source_assertions``. O que o formato
não representa (conversões, faixas plausíveis, tabela de cobrimento por CAA, não-sinônimos)
fica em ``x_extensoes_provisorias``; campos de binding fora do formato começam com ``x_``.

Aqui só se valida o subconjunto que o estudo M7-08 usa e se deriva o ``Vocabulary``
consumido pelo gerador e pelo harness (``context_format.py``). Isto não é o leitor do
catálogo nem aplica as regras de resolução do M1.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

REPO_ROOT: Final = Path(__file__).resolve().parents[3]
DEFAULT_DICTIONARY_PATH: Final = (
    REPO_ROOT / "data" / "dicionario_provisorio" / "conceitos-estruturais.json"
)
STUDY_KEY_QUALIFIER: Final = "chave_estudo"
STANDARD_NAME_QUALIFIER: Final = "nome_padronizado"

AliasPurpose = Literal[
    "search",
    "label_translation",
    "historical_spelling",
    "representation_match",
    "approved_equivalence",
]
Relation = Literal["portador_padronizado", "derivacao", "relacionado_nao_equivalente"]


class _Entry(BaseModel):
    """Entrada do pacote: campos do catálogo que não usamos são aceitos e ignorados."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class LocalizedText(_Entry):
    lang: str
    text: str


class Qualifier(_Entry):
    name: str
    value: str


class Concept(_Entry):
    id: str
    code: str
    labels: tuple[LocalizedText, ...] = Field(min_length=1)
    definition: tuple[LocalizedText, ...] = ()
    logical_type: str
    dimension: str | None = None
    unit_id: str | None = None
    value_set_id: str | None = None
    qualifiers: tuple[Qualifier, ...] = ()
    source_assertion_ids: tuple[str, ...] = ()
    lifecycle: str

    def qualifier(self, name: str) -> str | None:
        """Valor de um qualificador, se houver."""
        return next((q.value for q in self.qualifiers if q.name == name), None)


class Unit(_Entry):
    id: str
    symbol: str
    dimension: str


class AllowedValue(_Entry):
    code: str | int | bool
    labels: tuple[LocalizedText, ...] = ()


class ValueSet(_Entry):
    id: str
    value_type: str
    values: tuple[AllowedValue, ...] = Field(min_length=1)


class Binding(_Entry):
    id: str
    concept_id: str
    carrier_kind: str
    set_name: str | None = None
    set_kind: str | None = None
    field_name: str
    ifc_type: str | None = None
    value_set_id: str | None = None
    write_enabled: bool = False
    x_relacao: Relation


class AliasScope(_Entry):
    set_names: tuple[str, ...] | None = None
    entity_classes: tuple[str, ...] | None = None
    schemas: tuple[str, ...] | None = None


class Alias(_Entry):
    id: str
    term: str
    lang: str | None = None
    purpose: AliasPurpose
    scope: AliasScope
    target_concept_id: str | None = None
    target_binding_id: str | None = None


class NonSynonym(_Entry):
    termo: str
    conceito: str
    motivo: str
    fonte: str | None = None


class Extensions(_Entry):
    conversoes_para_unidade_do_conceito: dict[str, dict[str, float]]
    faixas_plausiveis: dict[str, dict[str, Any]]
    cobrimento_nominal_por_caa_mm: dict[str, Any]
    classe_por_fck_cubo_eurocodigo: dict[str, int]
    grafias_da_caa: dict[str, list[str]]
    nao_sinonimos: tuple[NonSynonym, ...]
    exportadores: dict[str, str]


class ProvisionalDictionary(_Entry):
    """Arquivo inteiro (subconjunto validado)."""

    x_status: str
    concepts: tuple[Concept, ...]
    units: tuple[Unit, ...]
    value_sets: tuple[ValueSet, ...]
    bindings: tuple[Binding, ...]
    aliases: tuple[Alias, ...]
    x_extensoes_provisorias: Extensions


def load_dictionary(path: Path = DEFAULT_DICTIONARY_PATH) -> ProvisionalDictionary:
    """Lê e valida o arquivo do dicionário provisório."""
    return ProvisionalDictionary.model_validate(json.loads(path.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class Vocabulary:
    """Vocabulário do estudo derivado do dicionário (nada de termos fixos no código)."""

    concepts: tuple[str, ...]
    target_unit: dict[str, str | None]
    standard_name: dict[str, str]
    exporters: dict[str, dict[str, Any]]
    class_terms: frozenset[str]
    search_terms: dict[str, tuple[str, ...]]
    conversions: dict[str, dict[str, float]]
    fck_classes: tuple[int, ...]
    cube_of: dict[int, int]
    cover_by_caa: dict[str, dict[str, int]]
    caa_written: dict[str, list[str]]
    non_synonyms: dict[str, tuple[str, ...]]
    plausible: dict[str, dict[str, Any]]
    labels: dict[str, dict[str, str]]
    codes: dict[str, tuple[str, ...]]
    source: str = field(default="")


def build_vocabulary(d: ProvisionalDictionary, source: str = "") -> Vocabulary:
    """Deriva o vocabulário: grafias por exportador vêm dos aliases ``representation_match``
    com escopo no conjunto do exportador; termos de busca, dos aliases ``search``."""
    key_of = {c.id: c.qualifier(STUDY_KEY_QUALIFIER) or c.code for c in d.concepts}
    key_by_code = {c.code: key_of[c.id] for c in d.concepts}
    units = {u.id: u.symbol for u in d.units}
    binding_concept = {b.id: key_of[b.concept_id] for b in d.bindings}
    derivation = {b.id for b in d.bindings if b.x_relacao == "derivacao"}
    ext = d.x_extensoes_provisorias
    exporter_of_set = {set_name: exp for exp, set_name in ext.exportadores.items()}

    exporters: dict[str, dict[str, Any]] = {
        exp: {"pset": set_name, **{key_of[c.id]: [] for c in d.concepts}}
        for exp, set_name in ext.exportadores.items()
    }
    class_terms: set[str] = set()
    search: dict[str, list[str]] = defaultdict(list)
    for alias in d.aliases:
        if alias.purpose == "representation_match" and alias.target_binding_id:
            concept = binding_concept[alias.target_binding_id]
            for set_name in alias.scope.set_names or ():
                if set_name in exporter_of_set:
                    exporters[exporter_of_set[set_name]][concept].append(alias.term)
            if alias.target_binding_id in derivation:
                class_terms.add(alias.term)
        elif alias.purpose == "search" and alias.target_concept_id:
            search[key_of[alias.target_concept_id]].append(alias.term.lower())

    # Classes de resistência: conjunto de valores do binding de derivação do fck (StrengthClass).
    value_sets = {vs.id: vs for vs in d.value_sets}
    fck_classes: list[int] = []
    for b in d.bindings:
        if b.id in derivation and binding_concept[b.id] == "fck" and b.value_set_id:
            fck_classes = sorted(
                int(str(v.code).lstrip("C")) for v in value_sets[b.value_set_id].values
            )

    non_syn: dict[str, list[str]] = defaultdict(list)
    for ns in ext.nao_sinonimos:
        non_syn[key_by_code[ns.conceito]].append(ns.termo)

    return Vocabulary(
        concepts=tuple(key_of[c.id] for c in d.concepts),
        target_unit={key_of[c.id]: units.get(c.unit_id) if c.unit_id else None for c in d.concepts},
        standard_name={
            key_of[c.id]: c.qualifier(STANDARD_NAME_QUALIFIER) or c.code for c in d.concepts
        },
        exporters=exporters,
        class_terms=frozenset(class_terms),
        search_terms={k: tuple(v) for k, v in search.items()},
        conversions=ext.conversoes_para_unidade_do_conceito,
        fck_classes=tuple(fck_classes),
        cube_of={int(k): v for k, v in ext.classe_por_fck_cubo_eurocodigo.items()},
        cover_by_caa=ext.cobrimento_nominal_por_caa_mm["valores"],
        caa_written=ext.grafias_da_caa,
        non_synonyms={k: tuple(v) for k, v in non_syn.items()},
        plausible=ext.faixas_plausiveis,
        labels={key_of[c.id]: {t.lang.split("-")[0]: t.text for t in c.labels} for c in d.concepts},
        codes={
            key_of[c.id]: tuple(str(v.code) for v in value_sets[c.value_set_id].values)
            for c in d.concepts
            if c.value_set_id
        },
        source=source,
    )


@lru_cache(maxsize=4)
def load_vocabulary(path: Path = DEFAULT_DICTIONARY_PATH) -> Vocabulary:
    """Vocabulário do arquivo (com cache por caminho)."""
    return build_vocabulary(load_dictionary(path), source=str(path))
