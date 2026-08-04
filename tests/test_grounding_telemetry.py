"""Telemetria de grounding por issue (revisão bSDD 2026-08-04).

Os JSONL de resultado por issue não registravam NADA sobre grounding — nem
``source_status`` do bSDD, nem as fontes usadas, nem a URI da classe. Sem isso
não dá para provar pelos artefatos o que o bSDD entregou em cada issue, e a
ablação de grounding do plano experimental não é executável.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.experiment.evaluator import Evaluator, GroundTruth, GroundTruthItem
from src.experiment.per_issue import build_issue_outcomes
from src.models import (
    BSDDContext,
    BSDDProperty,
    Issue,
    Suggestion,
    SuggestionMetrics,
    SuggestionSet,
)
from src.suggestion_engine.ollama_client import OllamaClient
from src.suggestion_engine.suggestion import SuggestionGenerator

_BUILDING_CTX = {
    "building_type": "Residencial unifamiliar",
    "bioclimatic_zone": "3",
}

_CLASS_URI = "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/class/IfcWall"


def _make_client(response: str) -> MagicMock:
    client = MagicMock(spec=OllamaClient)
    client.generate.return_value = response
    return client


def _pset_issue() -> Issue:
    return Issue(
        element_guid="W" * 22,
        element_class="IfcWall",
        element_name="Parede 01",
        issue_type="pset_missing",
        severity="high",
        description="FireRating ausente",
        context={"check_pset": "Pset_WallCommon", "check_property": "FireRating"},
    )


def _bsdd_context(issue: Issue) -> BSDDContext:
    return BSDDContext(
        issue_id=issue.id,
        element_class="IfcWall",
        class_name="IfcWall",
        class_uri=_CLASS_URI,
        source_status="cache",
        properties=[BSDDProperty(name="Fire Rating", data_type="String")],
    )


def test_generate_records_grounding_telemetry():
    """generate() grava fontes, source_status e URI da classe nas métricas."""
    client = _make_client(
        '{"opcoes": [{"value": "REI 60", "justification": "Alvenaria.", "confidence": "alta"}]}'
    )
    gen = SuggestionGenerator(client)
    issue = _pset_issue()

    result = gen.generate(issue, _BUILDING_CTX, bsdd_context=_bsdd_context(issue))

    assert result.metrics is not None
    assert "bsdd" in result.metrics.grounding_sources
    assert result.metrics.bsdd_source_status == "cache"
    assert result.metrics.bsdd_class_uri == _CLASS_URI
    assert result.metrics.has_official_candidates is False


def test_generate_batch_reuse_copies_grounding_telemetry():
    """Issues reusadas herdam a telemetria de grounding da primária.

    O estímulo é o mesmo; sem a cópia, as linhas reusadas do JSONL ficariam
    sem proveniência e a ablação perderia 95% das issues.
    """
    client = _make_client(
        '{"opcoes": [{"value": "REI 60", "justification": "Alvenaria.", "confidence": "alta"}]}'
    )
    gen = SuggestionGenerator(client)
    primary = _pset_issue()
    secondary = _pset_issue()

    results = gen.generate_batch(
        [primary, secondary],
        _BUILDING_CTX,
        bsdd_context_map={
            primary.id: _bsdd_context(primary),
            secondary.id: _bsdd_context(secondary),
        },
        reuse_map={secondary.id: primary.id},
    )

    reused = results[1]
    assert reused.metrics is not None
    assert reused.metrics.reused_from_issue_id == primary.id
    assert reused.metrics.bsdd_source_status == "cache"
    assert "bsdd" in reused.metrics.grounding_sources
    assert reused.metrics.bsdd_class_uri == _CLASS_URI


def test_issue_outcome_exports_grounding_fields():
    """build_issue_outcomes repassa a telemetria de grounding ao JSONL por issue."""
    issue = _pset_issue()
    suggestion_set = SuggestionSet(
        issue_id=issue.id,
        suggestions=[
            Suggestion(label="REI 60", value="REI 60", justification="j", confidence="alta")
        ],
        metrics=SuggestionMetrics(
            issue_id=issue.id,
            grounding_sources=["ids", "bsdd"],
            bsdd_source_status="live",
            bsdd_class_uri=_CLASS_URI,
            has_official_candidates=True,
        ),
    )
    ground_truth = GroundTruth(
        items=[
            GroundTruthItem(
                element_guid=issue.element_guid,
                issue_type=issue.issue_type,
                check_property="FireRating",
                expected_value="REI 60",
                accepted_alternatives=[],
            )
        ]
    )

    outcomes = build_issue_outcomes([(issue, suggestion_set)], ground_truth, Evaluator())

    out = outcomes[0]
    assert out.grounding_sources == ["ids", "bsdd"]
    assert out.bsdd_source_status == "live"
    assert out.bsdd_class_uri == _CLASS_URI
    assert out.has_official_candidates is True
