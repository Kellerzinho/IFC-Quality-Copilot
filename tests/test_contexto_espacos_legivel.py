"""Contexto de espaços: legibilidade dos contidos e geometria em planta.

Auditoria de 2026-07-27, prompt real de um espaço do prédio:

    - Contém: IfcBuildingElementProxy: Blocks_Caixa de Luz_F05770PT:Único:1178721,
      IfcBuildingElementProxy: Blocks_Caixa de Luz_F05770PT:Único:1178758, ... (16×)

Dezesseis repetições do mesmo objeto, cada uma com o ID interno do Revit. Um
espaço do modelo chega a 84 elementos contidos e 43 rótulos distintos: o sinal
("é uma central de medidores") fica soterrado no ruído.

Além disso o template pede largura para decidir corredor — "circulação é estreita
(< 1,5 m)" — mas ``Perímetro`` vem ``None`` em 82 de 82 espaços. O ``bounding_box``
está presente em 82/82 e nunca era usado.
"""

from __future__ import annotations

from src.models import Issue
from src.suggestion_engine.prompt_templates import _format_elements, build_prompt

_BUILDING_CTX = {"building_type": "Residencial multifamiliar", "bioclimatic_zone": "3"}


def _contido(label: str, nome: str = "") -> dict:
    return {"guid": "x", "ifc_class": "IfcBuildingElementProxy", "functional_label": label, "name": nome}


def _space_issue(**context) -> Issue:
    base = {
        "current_name": "43",
        "area_m2": 3.0,
        "height_m": 4.0,
        "contained_elements": [],
        "adjacent_spaces": [],
        "is_on_exterior": False,
    }
    base.update(context)
    return Issue(
        element_guid="S" * 22,
        element_class="IfcSpace",
        element_name="43",
        issue_type="space_unnamed",
        severity="low",
        description="Espaço sem nome",
        context=base,
    )


# ---------------------------------------------------------------------------
# 1. Agrupamento de elementos repetidos
# ---------------------------------------------------------------------------


def test_elementos_repetidos_viram_contagem():
    elementos = [_contido("IfcBuildingElementProxy: Caixa de Luz")] * 16

    texto = _format_elements(elementos)

    assert "16x Caixa de Luz" in texto or "16× Caixa de Luz" in texto
    assert texto.count("Caixa de Luz") == 1, "repetição não foi agrupada"


def test_identificador_interno_do_revit_e_removido():
    """':Único:1178721' é ruído: não distingue nada e ocupa o contexto."""
    elementos = [_contido("IfcBuildingElementProxy: Blocks_Caixa de Luz_F05770PT:Único:1178721")]

    texto = _format_elements(elementos)

    assert "1178721" not in texto
    assert "Caixa de Luz" in texto


def test_elemento_unico_nao_ganha_contador():
    texto = _format_elements([_contido("cama de casal")])

    assert texto == "cama de casal"


def test_lista_longa_e_truncada_com_aviso():
    """84 elementos não cabem no prompt; truncar em silêncio esconderia evidência."""
    elementos = [_contido(f"objeto {i}") for i in range(40)]

    texto = _format_elements(elementos)

    assert "mais" in texto, "truncou sem avisar quantos ficaram de fora"
    assert len(texto) < 700


def test_ordena_do_mais_frequente_para_o_menos():
    elementos = [_contido("cadeira")] * 5 + [_contido("mesa de jantar")]

    texto = _format_elements(elementos)

    assert texto.index("cadeira") < texto.index("mesa de jantar")


# ---------------------------------------------------------------------------
# 2. Geometria em planta a partir do bounding box
# ---------------------------------------------------------------------------


def test_prompt_de_espaco_mostra_dimensoes_em_planta():
    issue = _space_issue(
        bounding_box={"min_x": 0.0, "max_x": 1.0, "min_y": 0.0, "max_y": 8.0,
                      "min_z": 0.0, "max_z": 2.6},
    )

    _, user = build_prompt(issue, _BUILDING_CTX)

    assert "1.0" in user and "8.0" in user, "dimensões em planta ausentes"
    assert "menor dimensão" in user.lower()


def test_espaco_estreito_e_sinalizado_como_pista_de_circulacao():
    """A regra 'circulação é estreita' só serve se a largura chegar ao prompt."""
    issue = _space_issue(
        area_m2=8.0,
        bounding_box={"min_x": 0.0, "max_x": 1.1, "min_y": 0.0, "max_y": 7.3,
                      "min_z": 0.0, "max_z": 2.6},
    )

    _, user = build_prompt(issue, _BUILDING_CTX)

    assert "1.1" in user
    assert "estreit" in user.lower()


def test_sem_bounding_box_nao_inventa_dimensao():
    issue = _space_issue(bounding_box=None)

    _, user = build_prompt(issue, _BUILDING_CTX)

    assert "menor dimensão" not in user.lower() or "N/D" in user


# ---------------------------------------------------------------------------
# 3. Ambientes condominiais na tabela de interpretação
# ---------------------------------------------------------------------------


def test_tabela_cobre_ambientes_de_condominio():
    """O prédio é multifamiliar: metade dos espaços é área comum, não apartamento.

    Sem essas linhas o modelo respondeu 'Sala de Estar'/'Dormitório' para
    medidores, hidrômetros, central de gás, lixo e cisterna.
    """
    issue = _space_issue()

    _, user = build_prompt(issue, _BUILDING_CTX)

    texto = user.lower()
    for pista in ("medidor", "hidrômetro", "gás", "lixo", "cisterna"):
        assert pista in texto, f"tabela de interpretação não cobre '{pista}'"


def test_tabela_cobre_lazer_e_circulacao_vertical():
    issue = _space_issue()

    _, user = build_prompt(issue, _BUILDING_CTX)

    texto = user.lower()
    for pista in ("churrasqueira", "playground", "escada"):
        assert pista in texto, f"tabela de interpretação não cobre '{pista}'"
