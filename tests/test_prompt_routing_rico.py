"""Roteamento de prompts P0: issues com template rico nunca caem no compacto pobre.

Regressão do benchmark de 2026-07-27: com o bSDD resolvendo todas as classes,
``is_grounded=True`` passou a rotear ``space_unnamed`` e ``system_unclassified``
para ``build_compact_prompt``, que não injeta o contexto que a issue carrega
(área, mobiliário, adjacências, camadas de material) nem o vocabulário canônico
dos templates — o masked caiu de 34–56% para 0–5% de top-1 e o qwen3.5 devolveu
79/79 respostas vazias. Estes testes fixam o desenho correto:

1. ``space_unnamed`` e ``system_unclassified`` grounded usam o template rico.
2. ``space_unnamed`` não recebe bloco bSDD (classes IFC não nomeiam ambientes).
3. Candidatos oficiais nunca são nomes de classe IFC (``IfcWall`` não é valor).
4. Contratos pedem 3 opções e proíbem opção vazia/placeholder.
5. O retry corretivo repete o contrato do issue_type, não o genérico.
"""

from src.models import BSDDClassification, BSDDContext, Issue
from src.suggestion_engine.grounding import prepare_llm_grounding
from src.suggestion_engine.prompt_templates import (
    PROMPT_VERSION,
    has_rich_template,
    output_contract_for,
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


def _space_issue() -> Issue:
    return Issue(
        element_guid="S" * 22,
        element_class="IfcSpace",
        element_name="43",
        issue_type="space_unnamed",
        severity="low",
        description="Espaço sem nome funcional",
        context={
            "current_name": "43",
            "area_m2": 12.5,
            "height_m": 2.7,
            "perimeter_m": 14.2,
            "floor": "Pavimento 2",
            "is_on_exterior": False,
            "contained_elements": ["cama de casal", "guarda-roupa"],
            "adjacent_spaces": ["Banheiro Suíte", "Corredor"],
        },
    )


def _system_issue() -> Issue:
    return Issue(
        element_guid="W" * 22,
        element_class="IfcWall",
        element_name="Parede básica:parede interna 20cm:764933",
        issue_type="system_unclassified",
        severity="medium",
        description="Parede sem classificação de sistema construtivo",
        context={
            "materials": [{"name": ".alvenaria deitado 18 cm", "thickness": 0.18}],
            "total_thickness": 0.20,
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
# 1. Roteamento: template rico mesmo com grounding
# ---------------------------------------------------------------------------


def test_space_unnamed_grounded_recebe_contexto_do_espaco():
    """Com bSDD resolvido, o prompt de nomeação mantém área, mobiliário e adjacências."""
    issue = _space_issue()
    spy = _SpyOllama(
        '{"opcoes":[{"issue_id":"x","nome":"Dormitório","confidence":"alta",'
        '"justification":"cama de casal presente","review_required":false}]}'
    )
    gen = SuggestionGenerator(spy)

    gen.generate(issue, _BUILDING_CTX, bsdd_context=_bsdd_for(issue, "IfcSpace"))

    _, user = spy.calls[0]
    assert "12.5" in user, "área do espaço ausente do prompt"
    assert "cama de casal" in user, "elementos contidos ausentes do prompt"
    assert "Banheiro Suíte" in user, "espaços adjacentes ausentes do prompt"
    assert "INTERPRETAÇÃO DOS ELEMENTOS" in user, "tabela de interpretação ausente"
    assert "candidatos: (nenhum oficial" not in user, "prompt compacto pobre foi usado"


def test_space_unnamed_grounded_nao_recebe_bloco_bsdd():
    """Classes IFC não ajudam a nomear ambiente; o bloco bSDD fica de fora."""
    issue = _space_issue()
    spy = _SpyOllama(
        '{"opcoes":[{"issue_id":"x","nome":"Dormitório","confidence":"alta",'
        '"justification":"cama","review_required":false}]}'
    )
    gen = SuggestionGenerator(spy)

    gen.generate(issue, _BUILDING_CTX, bsdd_context=_bsdd_for(issue, "IfcSpace"))

    _, user = spy.calls[0]
    assert "BSDD_CONTEXT" not in user
    assert "IfcSpace | URI" not in user


def test_system_unclassified_grounded_recebe_camadas_e_vocabulario_canonico():
    """Com bSDD resolvido, a classificação mantém camadas e o vocabulário canônico PT."""
    issue = _system_issue()
    spy = _SpyOllama(
        '{"opcoes":[{"issue_id":"x","sistema":"Alvenaria de vedação em bloco cerâmico",'
        '"confidence":"alta","justification":"camada de alvenaria 18cm"}]}'
    )
    gen = SuggestionGenerator(spy)

    gen.generate(issue, _BUILDING_CTX, bsdd_context=_bsdd_for(issue, "IfcWall"))

    _, user = spy.calls[0]
    assert "alvenaria deitado 18 cm" in user, "camadas de material ausentes do prompt"
    assert "Alvenaria de vedação em bloco cerâmico" in user, "vocabulário canônico ausente"
    assert "candidatos: IfcWall" not in user, "classe IFC oferecida como valor de sistema"


def test_has_rich_template_cobre_os_tipos_com_template_proprio():
    """space_unnamed e system_unclassified têm template rico; pset genérico não."""
    assert has_rich_template(_space_issue())
    assert has_rich_template(_system_issue())

    generic = Issue(
        element_guid="G" * 22,
        element_class="IfcWall",
        element_name="Parede",
        issue_type="pset_missing",
        severity="medium",
        description="Propriedade ausente",
        context={"check_property": "Reference", "pset_name": "Pset_WallCommon"},
    )
    assert not has_rich_template(generic)


# ---------------------------------------------------------------------------
# 2. Candidatos oficiais nunca são classes IFC
# ---------------------------------------------------------------------------


def test_official_candidates_excluem_nomes_de_classe_ifc():
    """``IfcWall`` é a entidade, não um valor de sistema construtivo."""
    issue = _system_issue()
    grounded = prepare_llm_grounding(issue, bsdd_context=_bsdd_for(issue, "IfcWall"))

    assert grounded.official_candidates == []
    # A classe oficial continua registrada como informação de grounding.
    assert grounded.official_class == "IfcWall"


def test_official_candidates_preservam_termos_de_dominio():
    """Termos que não são classes IFC continuam entrando como candidatos."""
    issue = _system_issue()
    ctx = _bsdd_for(issue, "IfcWall")
    ctx.classification_suggestions.append(
        BSDDClassification(name="Alvenaria estrutural", uri="https://example.org/alv")
    )
    grounded = prepare_llm_grounding(issue, bsdd_context=ctx)

    assert grounded.official_candidates == ["Alvenaria estrutural"]


def test_sistema_construtivo_nao_e_rebaixado_por_nao_ser_classe_ifc():
    """O vocabulário de sistemas é o canônico PT; classes IFC não rebaixam confiança."""
    issue = _system_issue()
    spy = _SpyOllama(
        '{"opcoes":[{"issue_id":"x","sistema":"Alvenaria de vedação em bloco cerâmico",'
        '"confidence":"alta","justification":"camada de alvenaria 18cm"}]}'
    )
    gen = SuggestionGenerator(spy)

    result = gen.generate(issue, _BUILDING_CTX, bsdd_context=_bsdd_for(issue, "IfcWall"))

    assert result.suggestions, "sugestão válida foi descartada"
    top = result.suggestions[0]
    assert top.confidence == "alta", "confiança rebaixada por vocabulário inaplicável"
    assert "fora do vocabulário bSDD" not in top.justification


# ---------------------------------------------------------------------------
# 3. Contratos: 3 opções, nunca opção vazia/placeholder
# ---------------------------------------------------------------------------


def test_contrato_space_pede_3_opcoes_e_proibe_nome_vazio():
    contract = output_contract_for("space_unnamed")

    assert "exatamente 3" in contract.lower()
    assert "vazio" in contract.lower(), "contrato não proíbe nome vazio"
    assert "Review Required" in contract, "contrato não proíbe o placeholder observado"
    assert "review_required=true" in contract, "abstenção via flag precisa continuar"


def test_contrato_compacto_pede_3_opcoes_e_valor_preenchido():
    contract = output_contract_for("pset_missing")

    assert "Maximo 3 opcoes." not in contract, "teto frouxo permite resposta com 1 opção"
    assert "3 opcoes" in contract
    assert "vazi" in contract.lower(), "contrato não proíbe lista/valor vazio"


# ---------------------------------------------------------------------------
# 4. Retry corretivo respeita o contrato do issue_type
# ---------------------------------------------------------------------------


def test_retry_de_space_unnamed_repete_contrato_de_nomeacao():
    gen = SuggestionGenerator(_SpyOllama("{}"))

    retry = gen._build_retry_prompt(_space_issue(), "PROMPT ORIGINAL")

    assert '"nome"' in retry, "retry deve pedir o campo nome"
    assert '"suggested_value"' not in retry, "retry vazou o contrato genérico"


def test_retry_de_fire_rating_mantem_instrucao_de_formato():
    issue = Issue(
        element_guid="F" * 22,
        element_class="IfcWall",
        element_name="Parede",
        issue_type="pset_missing",
        severity="high",
        description="FireRating ausente",
        context={"check_property": "FireRating", "pset_name": "Pset_WallCommon"},
    )
    gen = SuggestionGenerator(_SpyOllama("{}"))

    retry = gen._build_retry_prompt(issue, "PROMPT ORIGINAL")

    assert "REI 30" in retry
    assert '"suggested_value"' in retry


# ---------------------------------------------------------------------------
# 5. Fronteira de desenho de prompt registrada no cache
# ---------------------------------------------------------------------------


def test_prompt_version_avancou_para_v5():
    """O redesenho P0 muda o comportamento do LLM; caches v4 não podem ser reusados."""
    assert PROMPT_VERSION == "v5"
