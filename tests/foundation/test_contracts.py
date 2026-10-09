"""Forma dos módulos existentes diante dos contratos da fundação, e regras de revisão."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.audit.logger import AuditLogger
from src.bcf.exporter import BCFExporter
from src.config import BASE_DIR
from src.foundation.adapters import (
    IDSFileRequirementSource,
    IssueMetricsEvaluation,
    require_local_model,
)
from src.foundation.contracts import (
    AuditTrail,
    EvaluationSuite,
    IssueExporter,
    LocalLanguageModel,
    ModelInspector,
    RequirementSource,
)
from src.foundation.locality import ExternalEndpointError
from src.foundation.review import ElementReviewItem, ReviewDecision
from src.ifc_analyzer.analyzer import IFCAnalyzer
from src.suggestion_engine.ollama_client import OllamaClient

GUID = "2O2Fr$t4X7Zf8NOew3FLOH"


@pytest.mark.parametrize(
    ("implementation", "contract"),
    [
        (BCFExporter, IssueExporter),
        (AuditLogger, AuditTrail),
        (IFCAnalyzer, ModelInspector),
        (IDSFileRequirementSource, RequirementSource),
        (IssueMetricsEvaluation, EvaluationSuite),
    ],
)
def test_existing_modules_have_the_contract_shape(implementation: type, contract: type) -> None:
    assert issubclass(implementation, contract)


def test_local_ollama_client_is_accepted_as_local_language_model() -> None:
    client = OllamaClient(base_url="http://localhost:11434", model="qwen3.5:9b")
    try:
        assert isinstance(client, LocalLanguageModel)
        assert require_local_model(client) is client
    finally:
        client.close()


def test_language_model_with_external_endpoint_is_refused() -> None:
    client = OllamaClient(base_url="https://api.example.com", model="qualquer")
    try:
        with pytest.raises(ExternalEndpointError):
            require_local_model(client)
    finally:
        client.close()


def test_ids_requirement_source_reads_versioned_template() -> None:
    template = BASE_DIR / "data" / "ids_templates" / "fire_safety_readiness.ids"

    assert IDSFileRequirementSource(template).specifications()


def test_ids_requirement_source_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        IDSFileRequirementSource(tmp_path / "nao_existe.ids")


@pytest.mark.parametrize(
    ("verdict", "edited_value", "allows_write"),
    [
        ("accepted", None, True),
        ("edited", "EI 60", True),
        ("rejected", None, False),
    ],
)
def test_only_accepted_or_edited_decisions_allow_ifc_write(
    verdict: str, edited_value: str | None, allows_write: bool
) -> None:
    decision = ReviewDecision(
        issue_id="issue-1",
        guid=GUID,
        verdict=verdict,
        reviewer="engenheiro",
        edited_value=edited_value,
    )

    assert decision.allows_write is allows_write


def test_edited_decision_requires_edited_value() -> None:
    with pytest.raises(ValidationError):
        ReviewDecision(issue_id="issue-1", guid=GUID, verdict="edited", reviewer="engenheiro")


def test_decision_requires_identified_reviewer() -> None:
    with pytest.raises(ValidationError):
        ReviewDecision(issue_id="issue-1", guid=GUID, verdict="accepted", reviewer="")


def test_review_item_accepts_local_viewer_and_refuses_external() -> None:
    local = ElementReviewItem(
        guid=GUID, ifc_class="IfcWall", viewer_ref="http://localhost:8501/elemento"
    )
    arquivo = ElementReviewItem(guid=GUID, ifc_class="IfcWall", viewer_ref="vistas/parede.png")

    assert local.viewer_ref
    assert arquivo.viewer_ref
    with pytest.raises(ValidationError):
        ElementReviewItem(
            guid=GUID, ifc_class="IfcWall", viewer_ref="https://viewer.example.com/elemento"
        )
