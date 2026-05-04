"""Métricas agregadas para os experimentos de grounding."""

from collections import Counter
from typing import Any

from src.models import Issue


def calculate_metrics(issues: list[Issue]) -> dict[str, Any]:
    """Calcula métricas simples por lote de issues."""
    total = len(issues)
    decisions = Counter(issue.status for issue in issues)
    accepted = decisions.get("accepted", 0)
    edited = decisions.get("edited", 0)
    rejected = decisions.get("rejected", 0)
    resolved = accepted + edited
    return {
        "total_issues": total,
        "accepted": accepted,
        "edited": edited,
        "rejected": rejected,
        "acceptance_rate": (accepted / total) if total else 0.0,
        "edit_rate": (edited / total) if total else 0.0,
        "resolution_rate": (resolved / total) if total else 0.0,
        "issues_by_type": dict(Counter(issue.issue_type for issue in issues)),
        "issues_by_severity": dict(Counter(issue.severity for issue in issues)),
    }
