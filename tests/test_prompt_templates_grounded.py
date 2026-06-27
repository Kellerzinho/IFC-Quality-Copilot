"""Testes para prompts grounded com bloco IDS + bSDD."""

from src.bsdd.context_builder import build_grounding_block
from src.models import BSDDContext, BSDDProperty, IDSContext, Issue
from src.suggestion_engine.prompt_templates import build_grounded_prompt, build_prompt, parse_llm_response


def _make_issue(**context_overrides) -> Issue:
    return Issue(
        element_guid="W" * 22,
        element_class="IfcWall",
        element_name="Parede Externa 01",
        issue_type="pset_missing",
        severity="high",
        description="FireRating ausente",
        context={
            "check_property": "FireRating",
            "material_name": "Bloco ceramico",
            "floor": "Terreo",
            **context_overrides,
        },
    )


def _make_ids_context(issue: Issue) -> IDSContext:
    return IDSContext(
        issue_id=issue.id,
        requirement_id="req-fire-1",
        specification_name="Seguranca contra incendio",
        check_pset="Pset_WallCommon",
        check_property="FireRating",
        check_type="exists",
        severity="high",
    )


def _make_bsdd_context() -> BSDDContext:
    return BSDDContext(
        class_name="Wall",
        class_uri="https://example.org/classes/wall",
        related_properties=[
            BSDDProperty(
                name="FireRating",
                uri="https://example.org/properties/fire-rating",
                allowed_values=["30", "60", "90"],
            )
        ],
        source_uris=[
            "https://example.org/classes/wall",
            "https://example.org/properties/fire-rating",
        ],
        source_status="live",
    )


def test_build_grounded_prompt_with_full_grounding():
    issue = _make_issue()
    grounding_block = build_grounding_block(_make_ids_context(issue), _make_bsdd_context())

    prompt = build_grounded_prompt(
        issue=issue,
        building_context="Edificacao residencial multifamiliar na zona bioclimatica 3.",
        grounding_block=grounding_block,
        few_shot='{"opcoes": [{"label": "60", "value": "60"}]}',
    )

    assert "Você é um engenheiro civil brasileiro especialista em BIM, IFC e normas de desempenho." in prompt
    assert "CONTEXTO DA EDIFICAÇÃO:" in prompt
    assert "CONTEXTO DA ISSUE:" in prompt
    assert "GROUNDING BLOCK:" in prompt
    assert "REQUISITO IDS VIOLADO:" in prompt
    assert "VOCABULARIO bSDD" in prompt
    assert "RESTRIÇÃO: suas sugestões devem usar APENAS termos" in prompt
    assert '"canonical_term": "...", "semantic_hint": "..."' in prompt


def test_build_grounded_prompt_no_grounding():
    issue = _make_issue()

    prompt = build_grounded_prompt(
        issue=issue,
        building_context="Edificacao residencial multifamiliar na zona bioclimatica 3.",
        grounding_block="",
    )

    assert "GROUNDING BLOCK:" not in prompt
    assert "RESTRIÇÃO:" not in prompt
    assert "FireRating ausente" in prompt


def test_build_grounded_prompt_ids_without_bsdd():
    issue = _make_issue()
    grounding_block = build_grounding_block(_make_ids_context(issue), None)

    prompt = build_grounded_prompt(
        issue=issue,
        building_context="Edificacao residencial multifamiliar na zona bioclimatica 3.",
        grounding_block=grounding_block,
    )

    assert "GROUNDING BLOCK:" in prompt
    assert "REQUISITO IDS VIOLADO:" in prompt
    assert "VOCABULARIO bSDD" not in prompt
    assert "RESTRIÇÃO:" in prompt


def test_parse_response_with_bsdd_uri():
    raw = (
        '{"opcoes": ['
        '{"label": "60", "value": "60", "justification": "Valor permitido no vocabulário.", '
        '"confidence": "alta", "normative_ref": "NBR 14432", '
        '"semantic_hint": "fire_rating", "canonical_term": "REI 60", '
        '"bsdd_uri": "https://example.org/properties/fire-rating"}'
        "]}"
    )

    suggestions = parse_llm_response(raw, "pset_missing")

    assert len(suggestions) == 1
    assert suggestions[0].label == "60"
    assert suggestions[0].value == "60"
    assert suggestions[0].justification == "Valor permitido no vocabulário."
    assert suggestions[0].normative_ref == "NBR 14432"
    assert suggestions[0].canonical_term == "REI 60"
    assert suggestions[0].semantic_hint == "fire_rating"
    assert suggestions[0].bsdd_uri is None


def test_build_prompt_backward_compatibility():
    issue = _make_issue()

    system_prompt, user_prompt = build_prompt(
        issue,
        {"building_type": "Residencial", "bioclimatic_zone": "3"},
    )

    assert "FireRating" in user_prompt
    assert "GROUNDING BLOCK:" not in user_prompt
    assert "vocabul" not in system_prompt.lower()
