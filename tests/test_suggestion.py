"""Testes para SuggestionGenerator."""

from unittest.mock import MagicMock

import pytest

from src.models import BSDDClassification, BSDDContext, BSDDProperty, IDSContext, Issue, Suggestion, SuggestionSet
from src.suggestion_engine.ollama_client import OllamaClient
from src.suggestion_engine.suggestion import SuggestionGenerator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BUILDING_CTX = {
    "building_type": "Residencial unifamiliar",
    "bioclimatic_zone": "3",
}

_VALID_JSON = (
    '{"opcoes": [{"nome": "Sala de Estar", "justificativa": "25m²", "confianca": "alta"},'
    '{"nome": "Escritório", "justificativa": "mesa presente", "confianca": "media"}]}'
)


def _space_issue() -> Issue:
    return Issue(
        element_guid="S" * 22,
        element_class="IfcSpace",
        element_name="Room 1",
        issue_type="space_unnamed",
        severity="low",
        description="Espaço sem classificação funcional",
        context={
            "area_m2": 4.2,
            "height_m": 2.6,
            "contained_elements": ["IfcDoor"],
            "adjacent_spaces": ["Corredor"],
            "floor": "Pavimento 1",
        },
    )


def _make_client(response: str = _VALID_JSON) -> MagicMock:
    client = MagicMock(spec=OllamaClient)
    client.generate.return_value = response
    return client


def _make_suggestion(label: str = "Sala", confidence: str = "alta") -> Suggestion:
    return Suggestion(
        label=label,
        value=label,
        justification="teste",
        confidence=confidence,
        source="llm",
    )


# ---------------------------------------------------------------------------
# generate — sucesso
# ---------------------------------------------------------------------------

def test_generate_success():
    """generate retorna SuggestionSet populado em caso de sucesso."""
    client = _make_client(_VALID_JSON)
    gen = SuggestionGenerator(client)

    result = gen.generate(_space_issue(), _BUILDING_CTX)

    assert isinstance(result, SuggestionSet)
    assert result.has_suggestions
    assert result.suggestions[0].label == "Sala de Estar"
    assert result.suggestions[0].source == "llm"
    assert result.error is None
    client.generate.assert_called_once()


def test_generate_issue_id_matches():
    """SuggestionSet retornado tem issue_id igual ao id do Issue original."""
    issue = _space_issue()
    gen = SuggestionGenerator(_make_client())

    result = gen.generate(issue, _BUILDING_CTX)

    assert result.issue_id == issue.id


def test_generate_passes_system_and_prompt_to_client():
    """generate chama ollama_client.generate com system e prompt preenchidos."""
    client = _make_client()
    gen = SuggestionGenerator(client)

    gen.generate(_space_issue(), _BUILDING_CTX)

    call_kwargs = client.generate.call_args
    kwargs = call_kwargs.kwargs if call_kwargs.kwargs else {}
    args = call_kwargs.args

    # system deve conter algo sobre BIM/IFC
    system_arg = kwargs.get("system") or (args[1] if len(args) > 1 else None)
    assert system_arg is not None
    assert "BIM" in system_arg or "IFC" in system_arg


# ---------------------------------------------------------------------------
# generate — retry e falha
# ---------------------------------------------------------------------------

def test_generate_retries_on_failure():
    """generate tenta novamente após RuntimeError e retorna resultado na segunda tentativa."""
    client = MagicMock(spec=OllamaClient)
    client.generate.side_effect = [RuntimeError("timeout"), _VALID_JSON]

    gen = SuggestionGenerator(client)
    result = gen.generate(_space_issue(), _BUILDING_CTX)

    assert result.has_suggestions
    assert client.generate.call_count == 2


def test_generate_returns_error_after_3_failures():
    """generate retorna SuggestionSet com error após esgotar 3 tentativas."""
    client = MagicMock(spec=OllamaClient)
    client.generate.side_effect = RuntimeError("indisponível")

    gen = SuggestionGenerator(client)
    result = gen.generate(_space_issue(), _BUILDING_CTX)

    assert not result.has_suggestions
    assert result.error is not None
    assert "3" in result.error
    assert client.generate.call_count == 3


def test_generate_returns_empty_set_on_empty_llm_response():
    """generate sinaliza revisao quando LLM retorna lista vazia."""
    client = _make_client('{"opcoes": []}')
    gen = SuggestionGenerator(client)

    result = gen.generate(_space_issue(), _BUILDING_CTX)

    assert isinstance(result, SuggestionSet)
    assert not result.has_suggestions
    assert result.error is not None


def test_generate_with_grounding():
    client = _make_client(
        '{"opcoes": [{"label": "Sala de Estar", "value": "Sala de Estar", '
        '"justification": "Termo presente no vocabulário.", "confidence": "alta", '
        '"bsdd_uri": "https://github.com/fake/category/sala"}]}'
    )
    gen = SuggestionGenerator(client)
    issue = _space_issue()
    ids_context = IDSContext(
        issue_id=issue.id,
        requirement_id="req-123",
        specification_name="Spec Espaços",
        check_pset="Pset_SpaceCommon",
        check_property="Category",
        check_type="exists",
        severity="high",
    )
    bsdd_context = BSDDContext(
        issue_id=issue.id,
        element_class="IfcSpace",
        search_query="Space",
        properties=[BSDDProperty(name="Category", allowed_values=["Sala de Estar"])],
        classes=[BSDDClassification(name="Sala de Estar", uri="https://identifier.buildingsmart.org/uri/example/category/sala")],
        source_uris=["https://identifier.buildingsmart.org/uri/example/category/sala"],
        source_status="live",
    )

    result = gen.generate(
        issue,
        _BUILDING_CTX,
        bsdd_context=bsdd_context,
        ids_context=ids_context,
        grounding_mode="ids_bsdd",
    )

    assert result.has_suggestions
    assert result.suggestions[0].bsdd_uri == "https://identifier.buildingsmart.org/uri/example/category/sala"
    assert result.suggestions[0].ids_requirement_id == "req-123"

    call_kwargs = client.generate.call_args.kwargs
    assert "GROUNDING BLOCK:" in call_kwargs["prompt"]
    assert "REQUISITO IDS VIOLADO:" in call_kwargs["prompt"]
    assert "VOCABULARIO bSDD" in call_kwargs["prompt"]


def test_generate_without_grounding_unchanged():
    client = _make_client(_VALID_JSON)
    gen = SuggestionGenerator(client)
    issue = _space_issue()

    result = gen.generate(issue, _BUILDING_CTX, grounding_mode="none")

    assert result.has_suggestions
    assert result.suggestions[0].bsdd_uri is None
    assert result.suggestions[0].ids_requirement_id is None

    call_kwargs = client.generate.call_args.kwargs
    assert "GROUNDING BLOCK:" not in call_kwargs["prompt"]


# ---------------------------------------------------------------------------
# generate_batch
# ---------------------------------------------------------------------------

def test_generate_batch_processes_all():
    """generate_batch processa todas as issues e retorna lista de mesmo tamanho."""
    client = _make_client()
    gen = SuggestionGenerator(client)
    issues = [_space_issue() for _ in range(3)]

    results = gen.generate_batch(issues, _BUILDING_CTX)

    assert len(results) == 3
    assert all(isinstance(r, SuggestionSet) for r in results)


def test_generate_batch_preserves_order():
    """generate_batch retorna results na mesma ordem das issues de entrada."""
    issue1 = _space_issue()
    issue2 = _space_issue()
    issue3 = _space_issue()

    client = _make_client()
    gen = SuggestionGenerator(client)

    results = gen.generate_batch([issue1, issue2, issue3], _BUILDING_CTX)

    assert results[0].issue_id == issue1.id
    assert results[1].issue_id == issue2.id
    assert results[2].issue_id == issue3.id


def test_generate_batch_calls_progress():
    """generate_batch chama on_progress(current, total) após cada issue processada."""
    client = _make_client('{"opcoes": []}')
    gen = SuggestionGenerator(client)
    issues = [_space_issue() for _ in range(3)]

    calls: list[tuple[int, int]] = []
    gen.generate_batch(issues, _BUILDING_CTX, on_progress=lambda c, t: calls.append((c, t)))

    assert calls == [(1, 3), (2, 3), (3, 3)]


def test_generate_batch_without_progress_callback():
    """generate_batch funciona normalmente sem on_progress."""
    gen = SuggestionGenerator(_make_client())
    issues = [_space_issue()]

    results = gen.generate_batch(issues, _BUILDING_CTX)  # sem on_progress

    assert len(results) == 1


def test_generate_batch_empty_list():
    """generate_batch com lista vazia retorna lista vazia."""
    gen = SuggestionGenerator(_make_client())

    results = gen.generate_batch([], _BUILDING_CTX)

    assert results == []


# ---------------------------------------------------------------------------
# _validate_suggestions
# ---------------------------------------------------------------------------

def test_validate_removes_duplicates():
    """_validate_suggestions remove sugestões com label duplicado."""
    gen = SuggestionGenerator(_make_client())
    issue = _space_issue()
    suggestions = [
        _make_suggestion("Sala"),
        _make_suggestion("Sala"),   # duplicata
        _make_suggestion("Quarto"),
    ]

    result = gen._validate_suggestions(suggestions, issue)

    assert len(result) == 2
    assert result[0].label == "Sala"
    assert result[1].label == "Dormitorio"


def test_validate_limits_to_3():
    """_validate_suggestions limita a no máximo 3 sugestões."""
    gen = SuggestionGenerator(_make_client())
    issue = _space_issue()
    suggestions = [_make_suggestion(f"Opção {i}") for i in range(5)]

    result = gen._validate_suggestions(suggestions, issue)

    assert len(result) == 3


def test_validate_removes_empty_label():
    """_validate_suggestions descarta sugestões com label vazio ou só espaços."""
    gen = SuggestionGenerator(_make_client())
    issue = _space_issue()
    suggestions = [
        _make_suggestion(""),
        _make_suggestion("   "),
        _make_suggestion("Sala"),
    ]

    result = gen._validate_suggestions(suggestions, issue)

    assert len(result) == 1
    assert result[0].label == "Sala"


def test_validate_preserves_order():
    """_validate_suggestions mantém a ordem original (exceto remoções)."""
    gen = SuggestionGenerator(_make_client())
    issue = _space_issue()
    suggestions = [
        _make_suggestion("Quarto", "alta"),
        _make_suggestion("Sala", "media"),
        _make_suggestion("Corredor", "baixa"),
    ]

    result = gen._validate_suggestions(suggestions, issue)

    assert [s.label for s in result] == ["Dormitorio", "Sala", "Circulacao"]


# ---------------------------------------------------------------------------
# PromptRouter
# ---------------------------------------------------------------------------

from src.models import OperationalRule, ReadinessProfile  # noqa: E402
from src.suggestion_engine.prompt_router import PromptRouter  # noqa: E402


def _make_profile(profile_id: str = "energy_readiness") -> ReadinessProfile:
    return ReadinessProfile(
        id=profile_id,
        name="Energy Readiness",
        description="Perfil de teste",
    )


def _make_rule(strategy: str = "llm_inference") -> OperationalRule:
    return OperationalRule(
        source_spec="Test Rule",
        filter_entity="IfcWall",
        filter_conditions=[],
        check_pset="Pset_WallCommon",
        check_property="ThermalTransmittance",
        check_type="is_numeric",
        suggestion_strategy=strategy,
    )


def test_router_selects_profile_template():
    """route() com profile 'energy_readiness' e issue_type 'space_unnamed' deve
    retornar template do PROFILE_TEMPLATES (contém texto sobre energia)."""
    router = PromptRouter()
    issue = _space_issue()  # issue_type == "space_unnamed"
    profile = _make_profile("energy_readiness")
    rule = _make_rule()

    system, template = router.route(issue, profile, rule)

    assert "energia" in template.lower()
    assert "BIM" in system or "IFC" in system


def test_router_falls_back_to_generic():
    """Sem profile e com issue_type que existe em TEMPLATES, route() deve
    retornar o template genérico correspondente (não o de perfil)."""
    router = PromptRouter()
    issue = _space_issue()  # issue_type == "space_unnamed"

    system, template = router.route(issue, profile=None, rule=None)

    # Template genérico de space_unnamed contém a instrução de identificação
    assert "TAREFA" in template
    assert "INTERPRETAÇÃO" in template  # presente no template genérico space_unnamed
    # Não deve conter texto exclusivo do perfil energy_readiness
    assert "zona_termica_sugerida" not in template


def test_router_falls_back_to_pset_generic_when_unknown_type():
    """issue_type sem template dedicado deve cair no pset_missing_generic como fallback."""
    router = PromptRouter()
    issue = Issue(
        element_guid="X" * 22,
        element_class="IfcWall",
        issue_type="quantity_missing",  # não tem template em TEMPLATES
        severity="medium",
        description="Quantidade ausente",
    )

    system, template = router.route(issue, profile=None, rule=None)

    # Deve cair no fallback pset_missing_generic
    assert "check_property" in template


def test_router_build_context_merges():
    """build_context deve combinar issue.context com building_context,
    com issue.context tendo precedência."""
    router = PromptRouter()
    issue = _space_issue()
    building_ctx = {"building_type": "Comercial", "bioclimatic_zone": "4", "extra_key": "valor"}

    ctx = router.build_context(issue, building_ctx, profile=None)

    # Campos de issue.context presentes
    assert ctx["area_m2"] == 4.2
    assert ctx["floor"] == "Pavimento 1"
    # Campos de building_context presentes
    assert ctx["building_type"] == "Comercial"
    assert ctx["extra_key"] == "valor"
    # Campos padrão injetados
    assert ctx["guid"] == "S" * 8
    assert ctx["element_class"] == "IfcSpace"
    assert ctx["element_name"] == "Room 1"


def test_router_replaces_none_with_label():
    """build_context deve substituir valores None por 'não informado'."""
    router = PromptRouter()
    issue = _space_issue()
    issue.context["area_m2"] = None  # forçar None
    building_ctx = {"building_type": None, "bioclimatic_zone": "3"}

    ctx = router.build_context(issue, building_ctx, profile=None)

    assert ctx["area_m2"] == "não informado"
    assert ctx["building_type"] == "não informado"
    # Valor não-None deve ser preservado
    assert ctx["bioclimatic_zone"] == "3"


def test_suggestion_generator_with_router():
    """SuggestionGenerator com prompt_router deve chamar router.route() e
    router.build_context() em vez de build_prompt(), e retornar SuggestionSet populado."""
    from unittest.mock import patch

    client = _make_client(_VALID_JSON)
    router = PromptRouter()
    gen = SuggestionGenerator(client, prompt_router=router)
    issue = _space_issue()
    profile = _make_profile("energy_readiness")
    rule = _make_rule()

    with patch.object(router, "route", wraps=router.route) as mock_route, \
         patch.object(router, "build_context", wraps=router.build_context) as mock_ctx:
        result = gen.generate(issue, _BUILDING_CTX, profile=profile, rule=rule)

    assert isinstance(result, SuggestionSet)
    assert result.has_suggestions
    mock_route.assert_called_once_with(issue, profile, rule)
    mock_ctx.assert_called_once_with(issue, _BUILDING_CTX, profile)


def test_suggestion_generator_without_router_backward_compat():
    """SuggestionGenerator sem prompt_router deve continuar funcionando como antes,
    usando build_prompt() diretamente."""
    from unittest.mock import patch
    import src.suggestion_engine.suggestion as sug_module

    client = _make_client(_VALID_JSON)
    gen = SuggestionGenerator(client)  # sem prompt_router
    issue = _space_issue()

    with patch.object(sug_module, "build_prompt", wraps=sug_module.build_prompt) as mock_bp:
        result = gen.generate(issue, _BUILDING_CTX)

    assert isinstance(result, SuggestionSet)
    assert result.has_suggestions
    mock_bp.assert_called_once()


def test_validate_filters_values_outside_bsdd_vocab():
    gen = SuggestionGenerator(_make_client())
    issue = _space_issue()
    bsdd_context = BSDDContext(
        issue_id=issue.id,
        element_class="IfcSpace",
        search_query="Space",
        properties=[BSDDProperty(name="Category", allowed_values=["Sala"])],
        classes=[BSDDClassification(name="Sala", uri="https://identifier.buildingsmart.org/uri/example/category/sala")],
        source_uris=["https://identifier.buildingsmart.org/uri/example/category/sala"],
    )
    suggestions = [
        Suggestion(label="Sala", value="Sala", justification="ok", confidence="alta", source="llm"),
        Suggestion(label="Quarto", value="Quarto", justification="fora", confidence="media", source="llm"),
    ]

    result = gen._validate_suggestions(suggestions, issue, bsdd_context=bsdd_context)

    assert [s.label for s in result] == ["Sala", "Dormitorio"]
    assert result[0].bsdd_uri == "https://identifier.buildingsmart.org/uri/example/category/sala"


def test_generate_propagates_prompt_hash_and_ids_requirement():
    client = _make_client('{"opcoes": [{"nome": "Sala de Estar", "justificativa": "25m²", "confianca": "alta"}]}')
    gen = SuggestionGenerator(client)
    issue = _space_issue()
    ids_context = IDSContext(
        issue_id=issue.id,
        requirement_id="req-123",
        specification_name="Spec",
        check_pset="",
        check_property="LongName",
        check_type="not_empty",
        severity="low",
    )

    result = gen.generate(issue, _BUILDING_CTX, ids_context=ids_context, grounding_mode="ids_only")

    assert result.prompt_hash is not None
    assert result.suggestions[0].ids_requirement_id == "req-123"
