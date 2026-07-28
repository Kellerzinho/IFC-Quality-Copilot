"""Duas correções medidas no run ``corrigido`` (2026-07-28).

**Idioma do vocabulário fechado.** Ao trocar a instrução negativa (``NÃO traduza
para português``) por uma afirmativa, removi junto a parte que funcionava —
*"em maiúsculas e em inglês"*. O estrato ``Category`` caiu de 0,571 para 0,208 e
as respostas derivaram para ``SALA DE ESTAR``, ``SERVIÇA_AREA``, ``quarto``.
Exigir o idioma é contrato de saída, não dica sobre a resposta: não diz qual
ambiente é, só em que forma escrever.

**Proveniência do commit.** ``RunMetadata.repo_commit`` era lido ao FINAL do
estágio, então um commit feito enquanto a medição rodava era gravado como se
fosse o código executado. Aconteceu neste run: o JSON diz ``c3bd44c``, mas o
processo tinha carregado os módulos ~40 min antes desse commit existir.
"""

from __future__ import annotations

from src.models import Issue
from src.suggestion_engine.prompt_templates import TEMPLATES, build_prompt

_BUILDING_CTX = {"building_type": "Residencial multifamiliar", "bioclimatic_zone": "3"}


def _space_issue() -> Issue:
    return Issue(
        element_guid="S" * 22,
        element_class="IfcSpace",
        element_name="43",
        issue_type="pset_missing",
        severity="medium",
        description="Category ausente",
        context={"check_property": "Category", "area_m2": 12.0, "contained_elements": []},
    )


# ---------------------------------------------------------------------------
# Idioma e forma do token
# ---------------------------------------------------------------------------


def test_category_exige_ingles_e_maiusculas():
    """Sem exigir o idioma, o modelo responde em português e perde tudo."""
    _, user = build_prompt(_space_issue(), _BUILDING_CTX)

    texto = user.lower()
    assert "inglês" in texto or "ingles" in texto, "contrato não fixa o idioma do token"
    assert "maiúscul" in texto or "maiuscul" in texto


def test_category_continua_sem_instrucao_negativa():
    """A negação foi o que induziu a tradução; ela não pode voltar."""
    _, user = build_prompt(_space_issue(), _BUILDING_CTX)

    assert "traduz" not in user.lower()


def test_category_mantem_vocabulario_completo():
    template = TEMPLATES["pset_missing_space_category"]

    for token in ("BEDROOM", "TECHNICAL_AREA", "CIRCULATION", "STORAGE"):
        assert token in template


# ---------------------------------------------------------------------------
# Proveniência
# ---------------------------------------------------------------------------


def test_commit_do_run_e_capturado_no_inicio_do_processo():
    """O metadata precisa descrever o código EXECUTADO, não o HEAD do momento.

    Sem isso, editar o repositório durante uma medição de horas grava um commit
    que nunca rodou — e o run vira irreprodutível sem que nada acuse.
    """
    from src.experiment import runner

    assert hasattr(runner, "_REPO_COMMIT_AT_IMPORT"), (
        "o commit precisa ser fixado quando o processo carrega o módulo"
    )
    assert runner._repo_commit() == runner._REPO_COMMIT_AT_IMPORT
