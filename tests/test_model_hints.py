"""Testes do direcionamento por família de modelo (model_hints, v6)."""

from __future__ import annotations

from src.models import Issue
from src.suggestion_engine.model_hints import _HINT_HEADER, all_hint_texts, hints_for
from src.suggestion_engine.suggestion import SuggestionGenerator

GUID = "3nJOFsJsX8QO2odKZbQnBj"  # 22 chars


def make_issue(issue_type: str = "pset_missing", check_property: str | None = "FireRating") -> Issue:
    context = {"check_property": check_property} if check_property else {}
    return Issue(
        element_guid=GUID,
        element_class="IfcWall" if issue_type == "pset_missing" else "IfcSpace",
        issue_type=issue_type,
        severity="high",
        description="Teste de hints",
        context=context,
    )


# ---------------------------------------------------------------------------
# hints_for — resolução de família e estrato
# ---------------------------------------------------------------------------


def test_modelo_desconhecido_nao_recebe_hint():
    assert hints_for("modelo-inedito:1b", make_issue()) is None


def test_familia_sem_hint_para_o_estrato_retorna_none():
    """gemma2 tem hints, mas não para space_unnamed — prompt fica intocado."""
    issue = make_issue(issue_type="space_unnamed", check_property=None)
    assert hints_for("gemma2:9b", issue) is None


def test_tag_exata_tem_precedencia_sobre_familia():
    """qwen3.5:9b colapsa em EI no fogo; o 4b é o melhor do estrato e fica sem hint."""
    fire = make_issue()
    assert hints_for("qwen3.5:9b", fire) is not None
    assert hints_for("qwen3.5:4b", fire) is None


def test_familia_cobre_estrato_compartilhado():
    """A patologia de nome hiperespecífico vale para toda a família qwen3.5."""
    space = make_issue(issue_type="space_unnamed", check_property=None)
    bloco_4b = hints_for("qwen3.5:4b", space)
    bloco_9b = hints_for("qwen3.5:9b", space)
    assert bloco_4b is not None and "nome usual de projeto" in bloco_4b
    assert bloco_9b is not None and "nome usual de projeto" in bloco_9b


def test_bloco_tem_cabecalho_e_marcadores():
    bloco = hints_for("mistral:7b", make_issue())
    assert bloco is not None
    assert bloco.startswith(_HINT_HEADER)
    assert "\n- " in bloco


def test_all_hint_texts_cobre_o_mapa():
    textos = all_hint_texts()
    assert len(textos) > 5
    assert _HINT_HEADER in textos


# ---------------------------------------------------------------------------
# Integração: o gerador anexa o bloco ao prompt real
# ---------------------------------------------------------------------------


class _SpyClient:
    def __init__(self, model: str) -> None:
        self.model = model
        self.prompts: list[str] = []

    def generate(self, prompt: str, system: str | None = None):
        self.prompts.append(prompt)
        return (
            '{"opcoes": [{"valor": "EI 90", "justificativa": "t", "confianca": "media"}]}',
            {},
        )


def _run_generate(model: str) -> list[str]:
    client = _SpyClient(model)
    generator = SuggestionGenerator(ollama_client=client)
    generator.generate(make_issue(), building_context={})
    return client.prompts


def test_generate_anexa_hint_para_modelo_mapeado():
    prompts = _run_generate("mistral:7b")
    assert prompts, "o cliente deveria ter sido chamado"
    assert _HINT_HEADER in prompts[0]


def test_generate_nao_anexa_hint_para_modelo_fora_do_mapa():
    prompts = _run_generate("modelo-inedito:1b")
    assert prompts
    assert _HINT_HEADER not in prompts[0]
