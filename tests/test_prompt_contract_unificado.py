"""Contrato de saída unificado: a mesma invariante em todo caminho de prompt.

Existem quatro construtores de prompt (legacy, compacto, pset grounded e router).
O contrato de saída de cada issue_type precisa valer em todos eles: um caminho que
peça um contrato diferente muda o comportamento do LLM sem que nada acuse.

O caso que motivou este arquivo: `space_unnamed` deve pedir o nome funcional do
ambiente em português. Quando recebia por cima o contrato genérico
(`canonical_term`/`semantic_hint`), o LLM respondia pseudo-classes IFC
("IfcKitchen") e a acurácia top-1 da tarefa de nomeação caiu a zero no benchmark.
A correção original (v4) cobriu apenas o caminho legacy.
"""

from src.models import Issue
from src.suggestion_engine.grounding import prepare_llm_grounding
from src.suggestion_engine.prompt_templates import (
    build_compact_prompt,
    build_prompt,
)


def _space_issue() -> Issue:
    return Issue(
        element_guid="S" * 22,
        element_class="IfcSpace",
        element_name="Room 101",
        issue_type="space_unnamed",
        severity="low",
        description="Espaço sem nome funcional",
        context={"current_name": "Room 101", "area_m2": 12.5, "floor": "Térreo"},
    )


_BUILDING_CTX = {
    "building_type": "Residencial unifamiliar",
    "bioclimatic_zone": "3",
    "city": "São Paulo",
    "state": "SP",
}


def _prompt_legacy(issue: Issue) -> str:
    _, user = build_prompt(issue, _BUILDING_CTX)
    return user


def _prompt_compacto(issue: Issue) -> str:
    grounded = prepare_llm_grounding(issue)
    _, user = build_compact_prompt(grounded)
    return user


def _todos_os_prompts(issue: Issue) -> dict[str, str]:
    return {
        "legacy": _prompt_legacy(issue),
        "compacto": _prompt_compacto(issue),
    }


def test_space_unnamed_nunca_pede_canonical_term():
    """Nenhum caminho de prompt pede vocabulário canônico para nomear espaço."""
    issue = _space_issue()

    for caminho, prompt in _todos_os_prompts(issue).items():
        assert "canonical_term" not in prompt, f"caminho {caminho} pede canonical_term"
        assert "semantic_hint" not in prompt, f"caminho {caminho} pede semantic_hint"


def test_space_unnamed_sempre_exige_nome_funcional_em_portugues():
    """Todo caminho de prompt instrui explicitamente o formato do nome."""
    issue = _space_issue()

    for caminho, prompt in _todos_os_prompts(issue).items():
        assert "nome funcional" in prompt.lower(), f"caminho {caminho} sem a instrução"
        assert "nunca classe IFC" in prompt, f"caminho {caminho} sem a proibição"


def test_pset_missing_mantem_contrato_com_vocabulario_canonico():
    """A restrição vale para nomeação; pset_missing continua pedindo o termo canônico."""
    issue = Issue(
        element_guid="W" * 22,
        element_class="IfcWall",
        element_name="Parede Externa 01",
        issue_type="pset_missing",
        severity="high",
        description="FireRating ausente",
        context={"check_property": "FireRating", "pset_name": "Pset_WallCommon"},
    )

    grounded = prepare_llm_grounding(issue)
    _, compacto = build_compact_prompt(grounded)

    assert "canonical_term" in compacto


def test_prompt_compacto_menciona_a_classe_oficial_do_bsdd():
    """O vocabulário oficial resolvido é comunicado ao LLM, não só registrado."""
    from src.models import BSDDContext

    issue = _space_issue()
    bsdd_context = BSDDContext(
        issue_id=issue.id,
        element_class="IfcSpace",
        class_name="IfcSpace",
        class_uri="https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/class/IfcSpace",
        source_status="live",
    )
    grounded = prepare_llm_grounding(issue, bsdd_context=bsdd_context)

    _, user = build_compact_prompt(grounded)

    assert "IfcSpace" in user
    assert "bsdd" in user.lower()
