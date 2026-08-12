"""Testes de normalizacao forte das sugestoes."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.models import BSDDClassification, BSDDContext, BSDDProperty, Issue, Suggestion
from src.suggestion_engine.normalization import (
    canonicalize_space_label,
    canonicalize_system_label,
    is_valid_bsdd_uri,
    normalize_fire_rating,
    normalize_suggestion,
    normalize_value_for_issue,
    parse_numeric_value,
)
from src.suggestion_engine.ollama_client import OllamaClient
from src.suggestion_engine.suggestion import SuggestionGenerator


def _pset_issue(prop: str) -> Issue:
    return Issue(
        element_guid="W" * 22,
        element_class="IfcWall",
        element_name="Parede 01",
        issue_type="pset_missing",
        severity="high",
        description=f"{prop} ausente",
        context={"check_property": prop},
    )


def test_parse_numeric_value_with_units_and_text() -> None:
    assert parse_numeric_value("2.50 W/(m².K)") == pytest.approx(2.5)
    assert parse_numeric_value("Pset_WallCommon.ThermalTransmittance = 2,50 W/(m².K)") == pytest.approx(2.5)
    assert parse_numeric_value("0") is None


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("REI60", "REI 60"),
        ("REI 120", "REI 120"),
        ("EI 30", "EI 30"),
        ("EI-60", "EI 60"),
        ("R 60", "R 60"),
        # Classe declarada longe do número continua valendo.
        ("REI 1h", "REI 60"),
        ("EI de 30 min", "EI 30"),
        ("REI de 60 minutos", "REI 60"),
    ],
)
def test_normalize_fire_rating(raw_value: str, expected: str) -> None:
    assert normalize_fire_rating(raw_value) == expected


@pytest.mark.parametrize(
    "raw_value",
    ["A1", "0", "1", "R 1", "EI 1", "", None, "N/A", "FireRating"],
)
def test_normalize_fire_rating_rejects_invalid(raw_value) -> None:
    assert normalize_fire_rating(raw_value) is None


@pytest.mark.parametrize("raw_value", ["60", "60min", "1h", "2h", "120", "60 minutos"])
def test_normalize_fire_rating_rejects_duration_without_class(raw_value: str) -> None:
    """Duração sozinha não é classe de resistência ao fogo (2026-08-12).

    A normalização preenchia a classe ausente com ``REI`` — o valor esperado mais
    frequente do ground truth —, dando de graça a parte difícil da decisão: R, EI
    e REI dependem da FUNÇÃO do elemento, que é o que o estrato mede. Medido no
    log da rodada v7.5: 108 respostas cruas eram duração pura.
    """
    assert normalize_fire_rating(raw_value) is None


def test_invalid_bsdd_uri_is_rejected_from_llm_payload() -> None:
    issue = _pset_issue("FireRating")
    suggestion = Suggestion(
        label="REI 60",
        value="REI 60",
        justification="teste",
        confidence="alta",
        source="llm",
        bsdd_uri="https://github.com/fake/path",
    )
    context = BSDDContext(
        issue_id=issue.id,
        element_class="IfcWall",
        search_query="Wall",
        properties=[BSDDProperty(name="FireRating", uri="https://identifier.buildingsmart.org/uri/example/fire-rating")],
        source_uris=["https://identifier.buildingsmart.org/uri/example/fire-rating"],
    )

    normalized = normalize_suggestion(issue, suggestion, context)

    assert normalized is not None
    assert normalized.bsdd_uri == "https://identifier.buildingsmart.org/uri/example/fire-rating"


def test_valid_llm_bsdd_uri_is_not_used_as_final_truth_without_context_match() -> None:
    issue = _pset_issue("FireRating")
    suggestion = Suggestion(
        label="REI 60",
        value="REI 60",
        justification="teste",
        confidence="alta",
        source="llm",
        bsdd_uri="https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/prop/FireRating",
    )
    context = BSDDContext(
        issue_id=issue.id,
        element_class="IfcWall",
        search_query="Wall",
        properties=[BSDDProperty(name="FireRating", uri="https://identifier.buildingsmart.org/uri/example/fire-rating")],
        source_uris=["https://identifier.buildingsmart.org/uri/example/fire-rating"],
    )

    normalized = normalize_suggestion(issue, suggestion, context)

    assert normalized is not None
    assert normalized.bsdd_uri == "https://identifier.buildingsmart.org/uri/example/fire-rating"


def test_generator_accepts_ei_fire_rating_after_normalization() -> None:
    client = MagicMock(spec=OllamaClient)
    client.generate.return_value = (
        '{"opcoes": [{"value": "EI 30", "label": "EI 30", '
        '"justification": "resistencia ao fogo", "confidence": "alta"}]}'
    )
    issue = _pset_issue("FireRating")

    result = SuggestionGenerator(client).generate(issue, {"building_type": "Residencial"})

    assert result.error is None
    assert result.suggestions[0].value == "EI 30"


def test_generator_retries_fire_rating_when_first_response_has_no_writable_value() -> None:
    client = MagicMock(spec=OllamaClient)
    client.generate.side_effect = [
        (
            '{"opcoes": [{"label": "Classificacao de resistencia ao fogo", '
            '"value": null, "canonical_term": "FireRating", '
            '"justification": "sem valor seguro", "confidence": "alta"}]}'
        ),
        (
            '{"opcoes": [{"value": "EI 30", "label": "EI 30", '
            '"justification": "resistencia ao fogo", "confidence": "alta"}]}'
        ),
    ]
    issue = _pset_issue("FireRating")

    result = SuggestionGenerator(client).generate(issue, {"building_type": "Residencial"})

    assert result.error is None
    assert result.suggestions[0].value == "EI 30"
    assert client.generate.call_count == 2
    retry_prompt = client.generate.call_args.kwargs["prompt"]
    assert "Para FireRating" in retry_prompt
    assert "N/A" in retry_prompt


def test_generator_retries_fire_rating_when_duration_is_not_plausible() -> None:
    client = MagicMock(spec=OllamaClient)
    client.generate.side_effect = [
        (
            '{"opcoes": [{"value": "R 1", "label": "R 1", '
            '"justification": "classe invalida", "confidence": "alta"}]}'
        ),
        (
            '{"opcoes": [{"value": "R 60", "label": "R 60", '
            '"justification": "classe valida", "confidence": "media"}]}'
        ),
    ]
    issue = _pset_issue("FireRating")

    result = SuggestionGenerator(client).generate(issue, {"building_type": "Residencial"})

    assert result.error is None
    assert result.suggestions[0].value == "R 60"
    assert client.generate.call_count == 2


def test_official_documentation_link_is_not_accepted_as_semantic_bsdd_uri() -> None:
    assert not is_valid_bsdd_uri("https://docs.ifcopenshell.org/ifctester.html")


def test_canonicalize_repetitive_slab_labels() -> None:
    assert canonicalize_system_label("laje macica de concreto armado", "IfcSlab") == "Laje maciça de concreto armado"
    assert canonicalize_system_label("piso ceramico", "IfcSlab") == "Piso cerâmico / porcelanato"


def test_canonicalize_space_aliases() -> None:
    assert canonicalize_space_label("wc") == "Banheiro"
    assert canonicalize_space_label("sala estar") == "Sala de Estar"


def test_generator_deduplicates_semantic_duplicates() -> None:
    client = MagicMock(spec=OllamaClient)
    client.generate.return_value = (
        '{"opcoes": ['
        '{"sistema": "laje macica de concreto armado", "justificativa": "a", "confianca": "alta"},'
        '{"sistema": "Laje maciça de concreto armado", "justificativa": "b", "confianca": "media"}'
        "]}"
    )
    issue = Issue(
        element_guid="S" * 22,
        element_class="IfcSlab",
        issue_type="system_unclassified",
        severity="medium",
        description="Sistema nao classificado",
        context={},
    )

    result = SuggestionGenerator(client).generate(issue, {"building_type": "Residencial"})

    assert len(result.suggestions) == 1
    assert result.suggestions[0].value == "Laje maciça de concreto armado"


def test_generator_extracts_numeric_value_before_exposing_suggestion() -> None:
    client = MagicMock(spec=OllamaClient)
    client.generate.return_value = (
        '{"opcoes": [{"valor": "Pset_WallCommon.ThermalTransmittance = 2.50 W/(m².K)", '
        '"justificativa": "teste", "confianca": "alta"}]}'
    )

    result = SuggestionGenerator(client).generate(_pset_issue("ThermalTransmittance"), {"building_type": "Residencial"})

    assert result.suggestions[0].value == pytest.approx(2.5)
    assert result.suggestions[0].label == "2.50"


def test_generator_keeps_only_valid_options_when_llm_response_is_mixed() -> None:
    client = MagicMock(spec=OllamaClient)
    client.generate.return_value = (
        '{"opcoes": ['
        '{"valor": "2.50 W/(m².K)", "justificativa": "valida", "confianca": "alta"},'
        '{"valor": "zero", "justificativa": "invalida", "confianca": "media"}'
        "]}"
    )

    result = SuggestionGenerator(client).generate(_pset_issue("ThermalTransmittance"), {"building_type": "Residencial"})

    assert len(result.suggestions) == 1
    assert result.suggestions[0].value == pytest.approx(2.5)


def test_system_bsdd_class_matching_uses_canonical_value() -> None:
    client = MagicMock(spec=OllamaClient)
    client.generate.return_value = (
        '{"opcoes": [{"sistema": "laje macica de concreto armado", "justificativa": "ok", "confianca": "alta"}]}'
    )
    issue = Issue(
        element_guid="S" * 22,
        element_class="IfcSlab",
        issue_type="system_unclassified",
        severity="medium",
        description="Sistema nao classificado",
        context={},
    )
    bsdd_context = BSDDContext(
        issue_id=issue.id,
        element_class="IfcSlab",
        search_query="Slab",
        classes=[
            BSDDClassification(
                name="Laje maciça de concreto armado",
                uri="https://identifier.buildingsmart.org/uri/example/slab-system",
            )
        ],
        source_uris=["https://identifier.buildingsmart.org/uri/example/slab-system"],
    )

    result = SuggestionGenerator(client).generate(issue, {"building_type": "Residencial"}, bsdd_context=bsdd_context)

    assert result.suggestions[0].bsdd_uri == "https://identifier.buildingsmart.org/uri/example/slab-system"
    assert result.suggestions[0].semantic_status == "resolved"


def test_space_semantic_hint_resolves_official_context() -> None:
    issue = Issue(
        element_guid="S" * 22,
        element_class="IfcSpace",
        issue_type="space_unnamed",
        severity="medium",
        description="Espaco sem nome",
        context={},
    )
    suggestion = Suggestion(
        label="wc",
        value="wc",
        justification="vaso sanitario presente",
        confidence="alta",
        source="llm",
        semantic_hint="bathroom",
        canonical_term="Banheiro",
        source_candidates=["bathroom", "wc"],
        review_required=True,
    )
    bsdd_context = BSDDContext(
        issue_id=issue.id,
        element_class="IfcSpace",
        search_query="Space",
        classes=[BSDDClassification(name="Banheiro", uri="https://identifier.buildingsmart.org/uri/example/category/bathroom")],
        source_uris=["https://identifier.buildingsmart.org/uri/example/category/bathroom"],
    )

    normalized = normalize_suggestion(issue, suggestion, bsdd_context)

    assert normalized is not None
    assert normalized.label == "Banheiro"
    assert normalized.bsdd_uri == "https://identifier.buildingsmart.org/uri/example/category/bathroom"
    assert normalized.semantic_status == "resolved"


def test_streamlit_ui_no_deprecated_use_container_width() -> None:
    ui_files = [
        Path("src/ui/app.py"),
        Path("src/ui/components/dashboard.py"),
    ]
    for path in ui_files:
        assert "use_container_width" not in path.read_text(encoding="utf-8")


def test_normalize_value_for_issue_rejects_invalid_custom_numeric() -> None:
    issue = _pset_issue("ThermalTransmittance")
    assert normalize_value_for_issue(issue, "0 W/(m².K)") is None


def test_quantity_missing_accepts_only_numeric_values() -> None:
    issue = Issue(
        element_guid="S" * 22,
        element_class="IfcSpace",
        issue_type="quantity_missing",
        severity="low",
        description="NetFloorArea ausente",
        context={"check_pset": "Qto_SpaceBaseQuantities", "check_property": "NetFloorArea"},
    )

    assert normalize_value_for_issue(issue, "NetFloorArea = 12,5 m2") == pytest.approx(12.5)
    assert normalize_value_for_issue(issue, "Ausencia de dados numericos para NetFloorArea") is None


def test_material_unmapped_rejects_llm_text_as_writable_value() -> None:
    issue = Issue(
        element_guid="W" * 22,
        element_class="IfcWallStandardCase",
        issue_type="material_unmapped",
        severity="low",
        description="Material nao mapeado",
        context={},
    )

    assert normalize_value_for_issue(issue, "Material nao mapeado para IfcWallStandardCase") is None


def test_resolve_bsdd_uri_matches_display_named_property() -> None:
    """Regressão (2026-08-04): resolve_bsdd_uri comparava "FireRating" com o nome
    humano do bSDD ("Fire Rating") e devolvia None para todo pset_missing —
    a sugestão aplicada ficava sem a URI canônica da propriedade."""
    from src.suggestion_engine.normalization import resolve_bsdd_uri

    issue = Issue(
        element_guid="W" * 22,
        element_class="IfcWall",
        element_name="Parede 01",
        issue_type="pset_missing",
        severity="high",
        description="FireRating ausente",
        context={"check_property": "FireRating"},
    )
    prop_uri = "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/prop/FireRating"
    ctx = BSDDContext(
        element_class="IfcWall",
        properties=[BSDDProperty(name="Fire Rating", uri=prop_uri)],
    )

    assert resolve_bsdd_uri(issue, "REI 60", ctx) == prop_uri
