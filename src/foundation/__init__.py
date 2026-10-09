"""Fundação semântica da reformulação do IFC Quality Copilot.

Contratos para catálogo/bSDD local, IFC/IDS, contexto e LLM local, revisão
visual por elemento, exportação/BCF, governança e avaliação científica, mais a
política de localidade: nada aqui chama rede, e endpoint externo é recusado sem
fallback. Ver ``docs/arquitetura/fundacao-semantica.md``.
"""

from src.foundation.adapters import (
    IDSFileRequirementSource,
    IssueMetricsEvaluation,
    require_local_model,
)
from src.foundation.contracts import (
    AuditTrail,
    ElementReviewQueue,
    EvaluationSuite,
    GroundingContextBuilder,
    IssueExporter,
    LocalLanguageModel,
    ModelInspector,
    RequirementSource,
    SemanticCatalog,
)
from src.foundation.locality import (
    EndpointScope,
    ExternalEndpointError,
    LocalityPolicy,
    classify_endpoint,
    ensure_local_endpoint,
)
from src.foundation.review import ElementReviewItem, ReviewDecision, ReviewVerdict

__all__ = [
    "AuditTrail",
    "ElementReviewItem",
    "ElementReviewQueue",
    "EndpointScope",
    "EvaluationSuite",
    "ExternalEndpointError",
    "GroundingContextBuilder",
    "IDSFileRequirementSource",
    "IssueExporter",
    "IssueMetricsEvaluation",
    "LocalLanguageModel",
    "LocalityPolicy",
    "ModelInspector",
    "RequirementSource",
    "ReviewDecision",
    "ReviewVerdict",
    "SemanticCatalog",
    "classify_endpoint",
    "ensure_local_endpoint",
    "require_local_model",
]
