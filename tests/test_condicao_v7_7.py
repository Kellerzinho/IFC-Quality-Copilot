"""Condição v7.7: o estímulo declarado é o estímulo enviado, sem roteiro de raciocínio.

A rodada v7.6 de 2026-08-12 (RTX 4060) mediu três defeitos que o v7.7 corrige:

1. **relation_broken nunca recebeu o template v7.6.** Com o bSDD resolvendo a
   classe do elemento, ``is_grounded=True`` roteava a issue para
   ``build_compact_prompt`` — o template ``relation_missing``, com o vocabulário
   de subtipos de ``IfcRelationship``, existia no dicionário mas não chegava ao
   fio. 0,00 em 20/20 estágios nas duas rodadas, com respostas que ecoam o nome
   do elemento. Mesma regressão de roteamento do benchmark de 2026-07-27
   (``tests/test_prompt_routing_rico.py``), num terceiro issue_type.

2. **Roteiro de raciocínio reintroduzido junto com a evidência.** O v7.6 somou
   ao inventário estrutural (evidência legítima) parágrafos que instruem a
   conclusão ("quando o modelo declara pórtico ... a alvenaria entre eles é de
   vedação"; "Decida pelo inventário acima"; "Decida pelo acabamento
   declarado"). Procedimento mediu −12,5 pp na matriz v6, e a rodada v7.6
   repetiu o padrão: system_unclassified −16,0 pp e "Alvenaria estrutural"
   saltando de 953 para 2145 itens por eco lexical. A evidência FICA; o roteiro
   SAI.

3. **O comparador presumia a função da parede.** "Alvenaria em bloco cerâmico"
   (sem função declarada) era promovida por alias a "Alvenaria de vedação em
   bloco cerâmico" — o valor esperado da maior classe do gabarito. Presumir a
   parte difícil é vazamento (princípio declarado no v7.6 §7 para o REI).

Ver ``docs/condicao-v7-7-2026-08-13.md``.
"""

from __future__ import annotations

from src.models import BSDDClassification, BSDDContext, Issue
from src.suggestion_engine.normalization import canonicalize_system_label
from src.suggestion_engine.prompt_templates import (
    PROMPT_VERSION,
    TEMPLATES,
    has_rich_template,
)
from src.suggestion_engine.suggestion import SuggestionGenerator

_BUILDING_CTX = {"building_type": "Residencial multifamiliar", "bioclimatic_zone": "3"}


class _SpyOllama:
    """Captura (system, user) enviados ao LLM e devolve JSON parseável."""

    model = "spy-model"

    def __init__(self, canned: str) -> None:
        self.canned = canned
        self.calls: list[tuple[str, str]] = []

    def generate(self, prompt: str, system: str | None = None) -> tuple[str, dict]:
        self.calls.append((system or "", prompt))
        return self.canned, {}


def _relation_issue() -> Issue:
    return Issue(
        element_guid="D" * 22,
        element_class="IfcDoor",
        element_name="porta de correr de vidro 76 cm",
        issue_type="relation_broken",
        severity="high",
        description="Porta sem IfcRelFillsElement",
        context={
            "expected_relation": "IfcRelFillsElement",
            "nearby_spaces": [{"guid": "S" * 22, "name": "Sala de Estar"}],
        },
    )


def _bsdd_for(issue: Issue, class_name: str) -> BSDDContext:
    return BSDDContext(
        issue_id=issue.id,
        element_class=issue.element_class,
        class_name=class_name,
        class_uri=f"https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/class/{class_name}",
        classification_suggestions=[
            BSDDClassification(
                name=class_name,
                uri=f"https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/class/{class_name}",
            )
        ],
        source_status="cache",
    )


# ---------------------------------------------------------------------------
# 1. relation_broken chega ao fio com o template rico, mesmo grounded
# ---------------------------------------------------------------------------


def test_relation_broken_tem_template_rico():
    """O template v7.6 existe; o roteamento precisa reconhecê-lo."""
    assert has_rich_template(_relation_issue())


def test_relation_grounded_recebe_vocabulario_de_schema_no_fio():
    """O prompt REAL (não o do dicionário) contém a pergunta e o vocabulário.

    Na rodada v7.6, com ``is_grounded=True``, a issue caía no prompt compacto:
    nenhum dos 10 modelos viu ``IfcRelFillsElement`` como opção — e nenhum o
    respondeu, em 40 estímulos.
    """
    issue = _relation_issue()
    spy = _SpyOllama(
        '{"opcoes":[{"valor":"IfcRelFillsElement","justificativa":"componente de '
        'esquadria sem vínculo com abertura","ref":"ISO 16739-1","confianca":"alta"}]}'
    )
    gen = SuggestionGenerator(spy)

    gen.generate(issue, _BUILDING_CTX, bsdd_context=_bsdd_for(issue, "IfcDoor"))

    _, user = spy.calls[0]
    assert "CLASSES DE RELACIONAMENTO DO SCHEMA" in user, "template rico não chegou ao fio"
    assert "IfcRelFillsElement" in user
    assert "IfcRelSpaceBoundary" in user
    assert "componente de esquadria" in user, "sintoma do ramo não foi montado"
    assert "candidatos:" not in user, "prompt compacto foi usado"


def test_relation_resposta_do_vocabulario_sobrevive_a_normalizacao():
    """A classe respondida atravessa o pipeline até a sugestão final."""
    issue = _relation_issue()
    spy = _SpyOllama(
        '{"opcoes":[{"valor":"IfcRelFillsElement","justificativa":"esquadria sem '
        'abertura","ref":"ISO 16739-1","confianca":"alta"}]}'
    )
    gen = SuggestionGenerator(spy)

    result = gen.generate(issue, _BUILDING_CTX, bsdd_context=_bsdd_for(issue, "IfcDoor"))

    values = [s.value for s in result.suggestions]
    assert "IfcRelFillsElement" in values


# ---------------------------------------------------------------------------
# 2. Evidência fica, roteiro sai
# ---------------------------------------------------------------------------


def test_system_template_mantem_evidencia_e_perde_o_roteiro():
    """O inventário estrutural e o LoadBearing ficam; a regra de inferência sai."""
    template = TEMPLATES["system_unclassified"]

    assert "{structural_inventory}" in template
    assert "{load_bearing}" in template
    assert "a alvenaria entre eles é de vedação" not in template
    assert "sustenta a edificação" not in template


def test_structural_template_mantem_evidencia_e_perde_o_roteiro():
    template = TEMPLATES["pset_missing_structural"]

    assert "{structural_inventory}" in template
    assert "PAREDE EM EDIFICAÇÃO COM PÓRTICO" not in template
    assert "Decida pelo inventário" not in template


def test_nonskid_template_perde_a_diretiva_e_mantem_o_conhecimento():
    """Tipologia de acabamento e escopo normativo ficam; a instrução de decidir
    por um único eixo sai — junto dela, o viés a False num gabarito True."""
    template = TEMPLATES["pset_missing_nonskid"]

    assert "NBR 9050" in template
    assert "concreto desempenado" in template, "tipologia de literatura removida por engano"
    assert "rampa e degrau" in template, "escopo normativo removido por engano"
    assert "Decida pelo acabamento" not in template
    assert "justificando pelo acabamento" not in template
    # Locks do v7.6 permanecem: nada de mapa classe→valor.
    assert "escada" not in template.casefold()
    assert "portante" not in template


# ---------------------------------------------------------------------------
# 3. Comparador: alias não presume a função da parede
# ---------------------------------------------------------------------------


def test_alias_nao_presume_funcao_de_alvenaria():
    """Rótulo sem função declarada não vira "de vedação" por decreto.

    A função (vedação × estrutural) é a substância do estrato — o gabarito da
    maior classe aceita apenas o rótulo com função. Promover o ambíguo dava a
    parte difícil de graça, como o REI presumido no FireRating.
    """
    assert canonicalize_system_label("Alvenaria em bloco cerâmico", "IfcWall") == (
        "Alvenaria em bloco cerâmico"
    )
    assert canonicalize_system_label("alvenaria cerâmica", "IfcWall") == "alvenaria cerâmica"
    assert canonicalize_system_label("bloco cerâmico", "IfcWall") == "bloco cerâmico"


def test_alias_continua_normalizando_notacao_com_funcao_declarada():
    """Notação não é decisão: com a função no texto, a grafia canônica vale."""
    assert canonicalize_system_label("alvenaria de vedacao em bloco ceramico", "IfcWall") == (
        "Alvenaria de vedação em bloco cerâmico"
    )
    assert canonicalize_system_label("alvenaria estrutural em bloco ceramico", "IfcWall") == (
        "Alvenaria estrutural em bloco cerâmico"
    )
    assert canonicalize_system_label("drywall", "IfcWall") == "Drywall / Steel frame"


# ---------------------------------------------------------------------------
# 4. Identidade do instrumento
# ---------------------------------------------------------------------------


def test_prompt_version_avancou_alem_do_v7_7():
    """O instrumento das rodadas publicadas é o v7.7; ele nunca volta atrás.

    O pino literal migrou para ``tests/test_grounding_escopado_v78.py`` quando o
    v7.8 corrigiu o empacotamento de grounding. O que este arquivo trava são os
    **comportamentos** do v7.7 (roteamento do relation_broken, ausência de
    roteiro de raciocínio, comparador sem presunção) — todos testados acima e
    preservados pelo v7.8, que não tocou em nenhum template.
    """
    versao = tuple(int(parte) for parte in PROMPT_VERSION.lstrip("v").split("."))
    assert versao >= (7, 7)
