"""Execução e métricas de experimentos."""

from src.experiment.evaluator import (
    EvaluationMetrics,
    Evaluator,
    GroundTruth,
    GroundTruthItem,
    values_match,
)
from src.experiment.metrics import (
    ExperimentResult,
    ReviewProxyMetrics,
    RunMetadata,
    StabilityMetrics,
    TimingMetrics,
    aggregate_stability,
    aggregate_timing,
    calculate_metrics,
)
from src.experiment.reviewer import ReviewDecision, simulate_review
from src.experiment.runner import ExperimentRunner, sha256_of

__all__ = [
    "ExperimentRunner",
    "sha256_of",
    "calculate_metrics",
    "Evaluator",
    "EvaluationMetrics",
    "GroundTruth",
    "GroundTruthItem",
    "values_match",
    "ExperimentResult",
    "RunMetadata",
    "ReviewProxyMetrics",
    "StabilityMetrics",
    "TimingMetrics",
    "aggregate_stability",
    "aggregate_timing",
    "ReviewDecision",
    "simulate_review",
]
