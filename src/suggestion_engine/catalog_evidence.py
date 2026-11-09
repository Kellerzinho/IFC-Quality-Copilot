"""Avaliação de evidência de um campo (plano §7.2 passos 4–6 e §7.4).

Prioridade determinística: erro técnico → capacidade ausente → conflito → busca
incompleta → insuficiência → suficiência. Todos os fatos são coletados antes de
decidir; todos os motivos encontrados são preservados nessa ordem, com o principal
primeiro. Normalização exige o conjunto de valores efetivo ``approved``.
``on_missing`` só se aplica depois de busca completa; busca parcial nunca é ausência.
Conflito não se resolve por ordem, confiança ou precedência formal, e é verificado
antes de qualquer transformação.
Enum e valor esperado do IDS nunca são evidência.
"""

from collections import Counter
from typing import Final

from src.suggestion_engine.catalog_contracts import (
    EvidenceAssessment,
    FieldEvidenceContext,
    M3Reason,
    RejectedObservation,
)
from src.suggestion_engine.catalog_operations import ACCEPTED_PRECONDITIONS, E3OperationBundle

_FORMAL: Final[dict[str, M3Reason]] = {
    "compliant": "already_satisfied",
    "not_applicable": "not_applicable",
    "not_verified": "formal_not_verified",
    "error": "formal_error",
}
_TECHNICAL: Final = frozenset(
    {"package_error", "identity_mismatch", "foreign_reference", "integrity_error", "search_error"}
)


def assess_evidence(context: FieldEvidenceContext, bundle: E3OperationBundle) -> EvidenceAssessment:
    """Estado da evidência, política/operação exatas, pertinência, conflitos e ação."""

    def result(status: str, *reasons: M3Reason, **extra: object) -> EvidenceAssessment:
        return EvidenceAssessment.model_validate(
            {
                "status": status,
                "context_sha256": context.context_sha256,
                "reasons": tuple(dict.fromkeys(reasons)),
                **extra,
            }
        )

    if context.formal_state in _FORMAL:
        return result("unavailable", _FORMAL[context.formal_state])
    if context.unavailable_reason is not None:
        return result("unavailable", context.unavailable_reason)
    projection = context.projection
    assert projection is not None
    binding, concept, policy = projection.binding, projection.concept, projection.evidence_policy
    if policy is None:
        return result("unavailable", "policy_missing")
    exact = {
        "policy_id": policy.id,
        "operation_id": policy.operation_id,
        "operation_version": policy.operation_version,
    }
    capability: list[M3Reason] = []
    if policy.operation_version is None:
        capability.append("operation_unpinned")
    elif policy.operation_id not in bundle.registry.operation_ids:
        capability.append("operation_unavailable")
    elif (policy.operation_id, policy.operation_version) not in bundle.handlers:
        capability.append("operation_version_mismatch")
    accepted = ACCEPTED_PRECONDITIONS.get(
        (policy.operation_id, policy.operation_version or ""), frozenset()
    )
    if any(item not in accepted for item in policy.preconditions):
        capability.append("unsupported_precondition")
    if any(
        channel not in context.recipe.supported_channels for channel in policy.admissible_channels
    ):
        capability.append("unsupported_channel")
    if binding.carrier_status != "approved":
        capability.append("pending_carrier")
    if binding.carrier_kind != "property":
        capability.append("unsupported_carrier")
    if binding.scope != context.recipe.target_scope:
        capability.append("unsupported_target_scope")
    if concept.unit_id is not None or concept.dimension not in (None, "dimensionless"):
        capability.append("unit_mismatch")
    lifecycles = [
        binding.lifecycle,
        concept.lifecycle,
        policy.lifecycle,
        projection.applicability_rule.lifecycle,
    ]
    if policy.operation_id == "normalize_code_nfc_trim":
        values = projection.effective_value_set
        if values is None or any(not isinstance(v.code, str) for v in values.values):
            capability.append("unsupported_value_type")
        else:
            # Só enum textual aprovado autoriza transformação (E3-08).
            lifecycles.append(values.lifecycle)
    if any(lifecycle != "approved" for lifecycle in lifecycles):
        capability.append("unapproved_content")
    report = context.search_report
    if report is None:
        return result("unavailable", *(capability or ["insufficient_context"]), **exact)
    admitted = {r.observation_id for r in context.resolutions if r.admissible}
    rejected = tuple(
        RejectedObservation(observation_id=r.observation_id, reason=r.rejection_reason)  # type: ignore[arg-type]
        for r in context.resolutions
        if not r.admissible
    )
    coverage = tuple(c for c in report.coverage if c.scope in context.search_plan.admitted_scopes)  # type: ignore[union-attr]
    details: dict[str, object] = {
        **exact,
        "admissible_observation_ids": tuple(sorted(admitted)),
        "rejected": rejected,
        "coverage": coverage,
    }
    # Todos os fatos são coletados; a ordem única (§7.4) decide estado e motivo principal.
    technical: list[M3Reason] = []
    conflict: list[M3Reason] = []
    incomplete: list[M3Reason] = []
    observations = [o for o in report.observations if o.observation_id in admitted]
    if any(c.status == "error" for c in coverage) or any(o.state == "error" for o in observations):
        technical.append("search_error")
    if any(c.status == "unsupported" for c in coverage):
        capability.append("context_limit_exceeded")
    if any(o.state == "unsupported" for o in observations):
        capability.append("unsupported_carrier")
    present = [o for o in observations if o.state == "present" and o.typed_value is not None]
    duplicated = [
        key
        for key, count in Counter(
            (o.owner.express_id, o.set_name, o.field_name) for o in observations
        ).items()
        if count > 1
    ]
    distinct = {(o.typed_value.tag, o.typed_value.value) for o in present}  # type: ignore[union-attr]
    conflicts: tuple[tuple[str, ...], ...] = ()
    if duplicated:
        conflict.append("duplicate_source_ambiguity")
        conflicts = tuple(
            tuple(
                sorted(
                    o.observation_id
                    for o in observations
                    if (o.owner.express_id, o.set_name, o.field_name) == key
                )
            )
            for key in sorted(duplicated)
        )
    elif len(distinct) > 1:
        conflict.append("evidence_conflict")
        conflicts = (tuple(sorted(o.observation_id for o in present)),)
    if any(c.status in ("partial", "not_searched") for c in coverage):
        incomplete.append("incomplete_search")
    insufficient: list[M3Reason] = []
    if not present:
        states = {o.state for o in observations}
        insufficient.append(
            "null_value"
            if "null" in states
            else "empty_value"
            if "empty" in states
            else "invalid_value"
            if "invalid" in states
            else "no_evidence"
        )
    reasons = [*technical, *capability, *conflict, *incomplete, *insufficient]
    if technical or capability:
        return result("unavailable", *reasons, **details)
    if conflict:
        action = "request_review" if policy.on_conflict == "request_review" else "none"
        return result("conflicting", *reasons, **details, conflicts=conflicts, action=action)
    if incomplete:
        # Busca parcial nunca é ausência: ``on_missing`` não se aplica.
        return result("partial", *reasons, **details)
    if insufficient:
        action = "request_human" if policy.on_missing == "request_human" else "none"
        return result("insufficient", *reasons, **details, action=action)
    details["admissible_observation_ids"] = tuple(sorted(o.observation_id for o in present))
    return result("sufficient", **details)
