"""Condição v7.8: o bloco de grounding não pode ocupar o lugar da tarefa.

As três correções aqui travadas saem da ablação-bSDD de 2026-08-18
(``docs/resultado-ablacao-bsdd-2026-08-19.md``), que mediu **−2,34 pp por
classe** a favor do braço sem bSDD e um estrato inteiro perdido por
empacotamento de contexto:

1. **Bloco sem escopo.** ``relation_broken`` não tem ``check_property``, então o
   construtor de contexto despejava o catálogo inteiro de propriedades do
   ``IfcDoor`` no IFC 4.3: **42.473 chars** (o bloco mediano da rodada tem 434).
   O prompt ia a 44,8 KB ≈ 20,7 mil tokens estimados contra um teto de janela de
   8192 — o servidor cortava o início, que é onde mora a pergunta. Os dez
   modelos respondiam tokens colhidos do próprio bloco (``BARREL``, ``TEU``,
   ``PASSENGER`` — a única enumeração fechada que o bSDD entregou no
   experimento, herdada de propriedades de logística). Sem o bloco, 8/10
   acertam ``IfcRelFillsElement``: eles sempre souberam a resposta.

2. **Instrução de obediência sem vocabulário.** O system prompt mandava "use
   apenas o vocabulário e os requisitos fornecidos" mesmo quando o bloco não
   trazia valor algum — ``allowed_values`` é nulo em 100% das propriedades do
   experimento e o bloco imprime literalmente ``livre``. A instrução só é
   legítima quando existe vocabulário fechado a seguir.

3. **Guarda de janela que mentia.** ``resolve_num_ctx`` logava "usando 8192 para
   nao truncar" e devolvia 8192 para um prompt que precisava de 20,7 mil tokens.
   Truncar em silêncio foi o que deixou o defeito 1 invisível por quatro
   rodadas.
"""

from __future__ import annotations

from src.models import BSDDClassification, BSDDContext, BSDDProperty, IDSContext, Issue
from src.suggestion_engine.ollama_client import OllamaClient
from src.suggestion_engine.prompt_templates import (
    PROMPT_VERSION,
    build_prompt,
)

_BUILDING_CTX = {"building_type": "Residencial unifamiliar", "bioclimatic_zone": "4A"}

_PORTA_DEF = (
    "The door is a built element that is predominately used to provide controlled "
    "access for people, goods, animals and vehicles."
)

# Os valores reais que os modelos copiaram do bloco truncado, em 2026-08-18.
_PROCESS_ITEM = [
    "BARREL", "CGT", "NOTKNOWN", "OTHER", "PASSENGER", "TEU", "TONNE", "UNSET", "VEHICLE",
]


def _catalogo_do_ifcdoor(n: int = 40) -> list[BSDDProperty]:
    """Reproduz o catálogo não escopado: muitas propriedades, quase todas 'livre'."""
    props = [
        BSDDProperty(
            name=f"Propriedade {i}",
            code=f"Prop{i}",
            uri=f"https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/prop/Prop{i}",
            data_type="String",
            description="Optional description, provided for exchanging informative comments.",
        )
        for i in range(n - 1)
    ]
    props.append(
        BSDDProperty(
            name="Process Item",
            code="ProcessItem",
            uri="https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/prop/ProcessItem",
            data_type="String",
            allowed_values=list(_PROCESS_ITEM),
        )
    )
    return props


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


def _pset_issue(check_property: str = "FireRating") -> Issue:
    return Issue(
        element_guid="W" * 22,
        element_class="IfcWall",
        element_name="Alvenaria 14 cm",
        issue_type="pset_missing",
        severity="high",
        description=f"{check_property} ausente",
        context={
            "check_property": check_property,
            "check_pset": "Pset_WallCommon",
            "layers": [{"material": "Bloco cerâmico", "thickness_m": 0.14}],
        },
    )


def _bsdd(
    *,
    class_name: str = "IfcDoor",
    properties: list[BSDDProperty] | None = None,
    classifications: list[BSDDClassification] | None = None,
    class_description: str | None = _PORTA_DEF,
) -> BSDDContext:
    return BSDDContext(
        element_class=class_name,
        class_name=class_name,
        class_uri=f"https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/class/{class_name}",
        class_description=class_description,
        related_properties=properties or [],
        classification_suggestions=classifications or [],
        source_status="live",
    )


# ---------------------------------------------------------------------------
# 1. Escopo: sem check_property, o catálogo de propriedades não entra no bloco
# ---------------------------------------------------------------------------


def test_relation_broken_nao_recebe_catalogo_de_propriedades():
    """Sem propriedade pedida, a lista de propriedades da classe é ruído puro."""
    _, user = build_prompt(
        _relation_issue(), _BUILDING_CTX, bsdd_context=_bsdd(properties=_catalogo_do_ifcdoor())
    )

    assert "Propriedade 7" not in user
    assert "Propriedades e valores permitidos" not in user
    for token in _PROCESS_ITEM:
        assert token not in user, f"token do catálogo vazou para o prompt: {token}"


def test_relation_broken_mantem_a_ancora_de_classe():
    """O que o bSDD tem de legítimo a dar aqui — definição e URI — permanece."""
    _, user = build_prompt(
        _relation_issue(), _BUILDING_CTX, bsdd_context=_bsdd(properties=_catalogo_do_ifcdoor())
    )

    assert "BSDD_CONTEXT:" in user
    assert "The door is a built element" in user


def test_prompt_de_relation_broken_cabe_na_janela_sem_truncar():
    """A regressão que custou o estrato: prompt maior que a janela é prompt cortado."""
    system, user = build_prompt(
        _relation_issue(), _BUILDING_CTX, bsdd_context=_bsdd(properties=_catalogo_do_ifcdoor())
    )

    assert not OllamaClient.exceeds_context_ceiling(user, system, num_predict=768, ceiling=8192)


def test_pset_missing_continua_recebendo_a_propriedade_pedida():
    """O escopo novo não pode apagar o grounding legítimo do preenchimento."""
    fire = BSDDProperty(
        name="Fire Rating",
        code="FireRating",
        uri="https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/prop/FireRating",
        data_type="String",
    )
    _, user = build_prompt(
        _pset_issue(), _BUILDING_CTX, bsdd_context=_bsdd(class_name="IfcWall", properties=[fire])
    )

    assert "Fire Rating" in user


# ---------------------------------------------------------------------------
# 2. A instrução de obediência exige vocabulário fechado
# ---------------------------------------------------------------------------

_OBEDIENCIA = "use apenas o vocabulário"


def test_sem_valores_permitidos_nao_ha_instrucao_de_obediencia():
    """'Use apenas o vocabulário fornecido' quando não há vocabulário é armadilha."""
    livre = BSDDProperty(name="Fire Rating", code="FireRating", data_type="String")
    system, _ = build_prompt(
        _pset_issue(), _BUILDING_CTX, bsdd_context=_bsdd(class_name="IfcWall", properties=[livre])
    )

    assert _OBEDIENCIA not in system


def test_com_valores_permitidos_a_instrucao_volta():
    """Onde o dicionário enumera valores, obedecer ao vocabulário é o correto."""
    enumerada = BSDDProperty(
        name="Status",
        code="Status",
        data_type="String",
        allowed_values=["NEW", "EXISTING", "DEMOLISH", "TEMPORARY"],
    )
    system, _ = build_prompt(
        _pset_issue("Status"),
        _BUILDING_CTX,
        bsdd_context=_bsdd(class_name="IfcWall", properties=[enumerada]),
    )

    assert _OBEDIENCIA in system


def test_ids_mantem_a_instrucao_de_obediencia():
    """O IDS carrega requisito computável; a instrução continua legítima com ele."""
    ids = IDSContext(
        spec_name="NBR 15575 — resistência ao fogo",
        requirement_description="Paredes devem declarar FireRating",
        check_type="property",
        expected_pset="Pset_WallCommon",
        expected_property="FireRating",
        severity="high",
    )
    system, _ = build_prompt(_pset_issue(), _BUILDING_CTX, ids_context=ids)

    assert _OBEDIENCIA in system


def test_classificacao_de_dominio_conta_como_vocabulario():
    """Classes de dicionário não-IFC são vocabulário fechado de fato."""
    dominio = BSDDClassification(
        name="Parede de alvenaria de vedação",
        code="21.22.16.11",
        uri="https://identifier.buildingsmart.org/uri/buildingsmart/uniclass2015/class/EF_25_10",
        system_name="Uniclass 2015",
    )
    contexto = _bsdd(class_name="IfcWall", classifications=[dominio])
    system, _ = build_prompt(_pset_issue(), _BUILDING_CTX, bsdd_context=contexto)

    assert _OBEDIENCIA in system


# ---------------------------------------------------------------------------
# 3. Teto do bloco e guarda de janela honesta
# ---------------------------------------------------------------------------


def test_bloco_bsdd_limita_o_numero_de_propriedades():
    """Defesa em profundidade: nenhum bloco pode crescer sem limite declarado."""
    bloco = _bsdd(properties=_catalogo_do_ifcdoor(40)).as_prompt_block()

    linhas_de_propriedade = [ln for ln in bloco.splitlines() if ln.startswith("- ")]
    assert len(linhas_de_propriedade) <= 12
    assert "omitidas" in bloco


def test_guarda_de_janela_denuncia_prompt_maior_que_o_teto():
    """O defeito ficou invisível por quatro rodadas porque a guarda mentia."""
    gigante = "x" * 45_000

    assert OllamaClient.exceeds_context_ceiling(gigante, "sys", num_predict=768, ceiling=8192)
    assert not OllamaClient.exceeds_context_ceiling(
        "prompt curto", "sys", num_predict=768, ceiling=8192
    )


# ---------------------------------------------------------------------------
# 4. Mudança de prompt é mudança de instrumento
# ---------------------------------------------------------------------------


def test_prompt_version_bumpada():
    """v7.7 é o instrumento das rodadas publicadas; estas correções são v7.8."""
    assert PROMPT_VERSION == "v7.8"
