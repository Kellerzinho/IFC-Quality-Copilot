"""Regras de conteúdo da curadoria (E2): validação, materialização, patch e diff.

Conteúdo SINTÉTICO das fábricas da E1 (``SYN_*``). Verifica que só a aprovação
promove proposta a ``approved``, que o release-base não é alterado nem perdido em
silêncio, que decisão pendente trava o portador dos usos afetados e que pendências
e capacidades indisponíveis ficam visíveis.
"""

import pytest

from src.domain_catalog.content import CatalogContent, EntityKind
from src.domain_catalog.curation_errors import DraftPatchError
from src.domain_catalog.curation_models import (
    DeprecateEntity,
    DraftPatch,
    DuplicateEntity,
    LifecycleKind,
    RemoveProposal,
    UpsertEntity,
    ValidationReport,
    content_sha256,
)
from src.domain_catalog.curation_validation import (
    PendingCarrierPolicy,
    apply_patch,
    content_diff,
    materialize_release_content,
    pending_items,
    validate_revision,
)
from src.domain_catalog.models import (
    CatalogModel,
    EvidencePolicy,
    IFCBinding,
    LifecycleState,
    ReconciliationDecision,
)
from src.domain_catalog.operations import OperationRegistry, OperationSpec
from tests.domain_catalog import factories as f
from tests.domain_catalog.factories import R

DRAFT = "urn:uuid:00000000-0000-4000-8000-0000000d0001"
POLICY_ID = "urn:uuid:00000000-0000-4000-8000-0000000d0002"
DECISION_ID = "urn:uuid:00000000-0000-4000-8000-0000000d0003"


def _with_lifecycle(content: CatalogContent, lifecycle: LifecycleState) -> CatalogContent:
    """Mesmo conteúdo com outro estado cadastral em toda entidade que o tem."""
    data = content.model_dump()
    for rows in data.values():
        for row in rows:
            if "lifecycle" in row:
                row["lifecycle"] = lifecycle
    return CatalogContent.model_validate(data)


def _replace(content: CatalogContent, kind: str, entity: CatalogModel) -> CatalogContent:
    """Troca (ou acrescenta) a entidade de mesmo ID no tipo dado."""
    entity_id = getattr(entity, "id")  # noqa: B009 - toda entidade do conteúdo tem ``id``
    rows = [e for e in getattr(content, kind) if e.id != entity_id]
    return content.model_copy(update={kind: (*rows, entity)})


def _report(
    content: CatalogContent,
    base: CatalogContent | None = None,
    *,
    policy: PendingCarrierPolicy = "block",
    registry: OperationRegistry | None = None,
) -> ValidationReport:
    return validate_revision(
        draft_id=DRAFT,
        revision=1,
        content=content,
        base=base,
        base_release=None,
        registry=registry or OperationRegistry(),
        pending_carrier_policy=policy,
    )


def _codes(report: ValidationReport, severity: str) -> set[str]:
    return {finding.code for finding in report.findings if finding.severity == severity}


# --- identidade e materialização -----------------------------------------------------------


def test_content_hash_ignores_entity_order_but_not_data() -> None:
    content = f.resolution_content()
    reordered = content.model_copy(update={"bindings": tuple(reversed(content.bindings))})
    relabeled = _replace(
        content, "concepts", f._concept_for(R.METODO, "SYN_METODO", labels=f.pt("Outro rótulo"))
    )

    assert content_sha256(reordered) == content_sha256(content)
    assert content_sha256(relabeled) != content_sha256(content)


def test_materialization_promotes_only_draft_and_reviewed_proposals() -> None:
    base = f.minimal_content("approved")
    deprecated_rule = f.rule("deprecated")
    content = _replace(_with_lifecycle(base, "draft"), "applicability_rules", deprecated_rule)
    content = _replace(content, "value_sets", f.value_set("reviewed"))

    released = materialize_release_content(content)

    assert released.concepts[0].lifecycle == "approved"
    assert released.bindings[0].lifecycle == "approved"
    assert released.value_sets[0].lifecycle == "approved"
    assert released.applicability_rules[0].lifecycle == "deprecated"
    assert released.source_assertions == content.source_assertions


# --- validação sem release-base ----------------------------------------------------------


def test_first_draft_with_proposals_passes_and_lists_no_pending_items() -> None:
    report = _report(f.minimal_content("draft"))

    assert report.passed
    assert _codes(report, "pending") == set()
    assert report.content_sha256 == content_sha256(f.minimal_content("draft"))


def test_approved_state_cannot_be_written_into_a_first_draft() -> None:
    report = _report(f.minimal_content("approved"))

    assert not report.passed
    assert "lifecycle.not_from_release" in _codes(report, "error")


def test_e1_content_issues_are_errors_located_by_entity_and_field() -> None:
    orphan = f.binding("draft").model_copy(
        update={"concept_id": "urn:uuid:00000000-0000-4000-8000-00000000beef"}
    )
    report = _report(_replace(f.minimal_content("draft"), "bindings", orphan))

    errors = [x for x in report.findings if x.code == "content.orphan_reference"]
    assert errors
    assert (errors[0].entity_kind, errors[0].entity_id, errors[0].field) == (
        "bindings",
        f.BINDING_ID,
        "concept_id",
    )


# --- herança do release-base -------------------------------------------------------------


def test_inherited_entities_unchanged_pass() -> None:
    base = f.minimal_content("approved")

    assert _report(base, base=base).passed


def test_published_entity_changed_without_becoming_a_proposal_is_refused() -> None:
    base = f.minimal_content("approved")
    sneaky = f.concept("approved").model_copy(update={"labels": f.pt("Rótulo trocado")})

    report = _report(_replace(base, "concepts", sneaky), base=base)

    assert "lifecycle.published_entity_modified" in _codes(report, "error")


def test_changing_a_published_entity_as_draft_proposal_is_allowed() -> None:
    base = f.minimal_content("approved")
    proposal = f.concept("draft").model_copy(update={"labels": f.pt("Rótulo revisto")})

    report = _report(_replace(base, "concepts", proposal), base=base)

    assert report.passed


def test_published_entity_cannot_disappear_from_the_next_release() -> None:
    base = f.resolution_content()
    without = base.model_copy(update={"aliases": base.aliases[1:]})

    report = _report(without, base=base)

    assert "lifecycle.published_entity_removed" in _codes(report, "error")


def test_deprecation_keeps_the_published_data() -> None:
    base = f.minimal_content("approved")
    deprecated = _replace(base, "bindings", f.binding("deprecated"))
    altered = _replace(
        base,
        "bindings",
        f.binding("deprecated").model_copy(update={"field_name": "SYN_Outro"}),
    )

    assert _report(deprecated, base=base).passed
    assert "lifecycle.published_entity_modified" in _codes(_report(altered, base=base), "error")


def test_published_source_assertion_is_immutable() -> None:
    base = f.minimal_content("approved")
    changed = f.source_assertion().model_copy(update={"target_literal": "SYN_Corrigido"})

    report = _report(_replace(base, "source_assertions", changed), base=base)

    assert "source.published_source_modified" in _codes(report, "error")


# --- decisões, portador e duplicatas -----------------------------------------------------


def _pending_carrier_draft() -> CatalogContent:
    """Proposta sintética com portador não determinado e decisão pendente que a afeta."""
    content = _with_lifecycle(f.resolution_content(), "draft")
    pending = next(b for b in content.bindings if b.id == R.B_AREA_PENDENTE)
    undetermined = IFCBinding.model_validate(
        {**pending.model_dump(), "carrier_kind": "property_or_quantity", "ifc_type": None}
    )
    return _replace(content, "bindings", undetermined)


def test_pending_decision_locks_the_carrier_of_the_bindings_it_affects() -> None:
    content = _pending_carrier_draft()
    reconciled = IFCBinding.model_validate(
        {
            **next(b for b in content.bindings if b.id == R.B_AREA_PENDENTE).model_dump(),
            "carrier_kind": "quantity",
            "carrier_status": "approved",
            "ifc_type": "IfcQuantityArea",
        }
    )

    report = _report(_replace(content, "bindings", reconciled), policy="allow")

    locked = [x for x in report.findings if x.code == "decision.pending_locks_carrier"]
    assert [(x.severity, x.entity_id) for x in locked] == [("error", R.B_AREA_PENDENTE)]


def test_deciding_the_divergence_with_justification_unlocks_reconciliation() -> None:
    content = _pending_carrier_draft()
    reconciled = IFCBinding.model_validate(
        {
            **next(b for b in content.bindings if b.id == R.B_AREA_PENDENTE).model_dump(),
            "carrier_kind": "quantity",
            "carrier_status": "approved",
            "ifc_type": "IfcQuantityArea",
        }
    )
    decided = ReconciliationDecision.model_validate(
        {
            **content.reconciliation_decisions[0].model_dump(),
            "status": "decided",
            "justification": "Evidência sintética de teste.",
        }
    )
    content = _replace(
        _replace(content, "bindings", reconciled), "reconciliation_decisions", decided
    )

    report = _report(content, policy="block")

    assert "decision.pending_locks_carrier" not in _codes(report, "error")
    assert "carrier.pending_proposal" not in _codes(report, "error")
    assert report.passed


@pytest.mark.parametrize(
    ("policy", "severity"), [("block", "error"), ("acknowledge", "pending"), ("allow", "pending")]
)
def test_pending_carrier_proposal_follows_the_publication_policy(
    policy: PendingCarrierPolicy, severity: str
) -> None:
    report = _report(_pending_carrier_draft(), policy=policy)

    found = [x for x in report.findings if x.code == "carrier.pending_proposal"]
    assert [(x.severity, x.entity_id) for x in found] == [(severity, R.B_AREA_PENDENTE)]


def test_pending_items_list_decisions_and_undetermined_carriers() -> None:
    items = pending_items(_pending_carrier_draft())

    assert [(item.kind, item.entity_id) for item in items] == [
        ("carrier_pending", R.B_AREA_PENDENTE),
        ("reconciliation_decision", R.DECISION_AREA),
    ]


def test_unreviewed_duplicate_is_an_error_until_its_identity_is_reviewed() -> None:
    content = f.minimal_content("draft")
    copy_id = "urn:uuid:00000000-0000-4000-8000-0000000d0099"
    duplicated, _ = apply_patch(
        content,
        DraftPatch(
            operations=(
                DuplicateEntity(
                    op="duplicate", kind="bindings", source_id=f.BINDING_ID, new_id=copy_id
                ),
            ),
            reason="duplicar uso",
        ),
        base=None,
    )
    reviewed, _ = apply_patch(
        duplicated,
        DraftPatch(
            operations=(
                UpsertEntity(
                    op="upsert",
                    kind="bindings",
                    entity={
                        **next(b for b in duplicated.bindings if b.id == copy_id).model_dump(
                            mode="json"
                        ),
                        "declared_schemas": ["IFC2X3"],
                    },
                ),
            ),
            reason="revisar identidade",
        ),
        base=None,
    )

    assert "identity.unreviewed_duplicate" in _codes(_report(duplicated), "error")
    assert "identity.unreviewed_duplicate" not in _codes(_report(reviewed), "error")
    assert [c.id for c in duplicated.concepts] == [f.CONCEPT_ID]


# --- avisos ---------------------------------------------------------------------------------


def _with_policy(content: CatalogContent, operation: str, version: str | None) -> CatalogContent:
    policy = EvidencePolicy(
        id=POLICY_ID,
        operation_id=operation,
        operation_version=version,
        admissible_channels=("P",),
        on_missing="request_human",
        on_conflict="request_review",
        lifecycle="draft",
    )
    binding = f.binding("draft").model_copy(update={"evidence_policy_id": POLICY_ID})
    return _replace(
        content.model_copy(update={"evidence_policies": (policy,)}), "bindings", binding
    )


def test_unsupported_operation_is_a_visible_warning_not_an_error() -> None:
    report = _report(_with_policy(f.minimal_content("draft"), "exact_read", "1"))

    assert report.passed
    assert "capability.operation_unavailable" in _codes(report, "warning")


def test_registered_operation_does_not_warn() -> None:
    registry = OperationRegistry(
        [
            OperationSpec(
                operation_id="exact_read",
                version="1",
                description="leitura sintética",
                inputs=("binding",),
                output="valor",
                implementation="tests:fake",
                tests=("tests/fake",),
            )
        ]
    )

    report = _report(_with_policy(f.minimal_content("draft"), "exact_read", "1"), registry=registry)

    assert "capability.operation_unavailable" not in _codes(report, "warning")


def test_synthetic_sources_and_unspecified_scope_are_flagged() -> None:
    unspecified = f.binding("draft").model_copy(update={"scope": "unspecified"})

    report = _report(_replace(f.minimal_content("draft"), "bindings", unspecified))

    assert {"source.synthetic_content", "binding.scope_unspecified"} <= _codes(report, "warning")


# --- patch -------------------------------------------------------------------------------


def test_patch_refuses_proposals_outside_draft_and_applies_nothing() -> None:
    content = f.minimal_content("draft")
    new_concept = f._concept_for(R.METODO, "SYN_NOVO", lifecycle="draft").model_dump(mode="json")
    approved = {**f.concept("draft").model_dump(mode="json"), "lifecycle": "approved"}

    with pytest.raises(DraftPatchError) as caught:
        apply_patch(
            content,
            DraftPatch(
                operations=(
                    UpsertEntity(op="upsert", kind="concepts", entity=new_concept),
                    UpsertEntity(op="upsert", kind="concepts", entity=approved),
                ),
                reason="tentativa de aprovar por edição",
            ),
            base=None,
        )

    assert [issue.code for issue in caught.value.issues] == ["proposal_must_be_draft"]


def test_patch_reports_invalid_entity_fields() -> None:
    broken = {**f.binding("draft").model_dump(mode="json"), "write_enabled": True}

    with pytest.raises(DraftPatchError) as caught:
        apply_patch(
            f.minimal_content("draft"),
            DraftPatch(
                operations=(UpsertEntity(op="upsert", kind="bindings", entity=broken),),
                reason="habilitar escrita",
            ),
            base=None,
        )

    issue = caught.value.issues[0]
    assert (issue.code, issue.entity_kind, issue.entity_id) == (
        "invalid_entity",
        "bindings",
        f.BINDING_ID,
    )


def test_published_entity_can_only_be_deprecated_never_removed() -> None:
    base = f.minimal_content("approved")
    remove = DraftPatch(
        operations=(RemoveProposal(op="remove", kind="bindings", entity_id=f.BINDING_ID),),
        reason="remover",
    )
    deprecate = DraftPatch(
        operations=(DeprecateEntity(op="deprecate", kind="bindings", entity_id=f.BINDING_ID),),
        reason="depreciar",
    )

    with pytest.raises(DraftPatchError, match="published_entity_not_removable") as caught:
        apply_patch(base, remove, base=base)
    deprecated, _ = apply_patch(base, deprecate, base=base)

    assert "deprecate" in caught.value.issues[0].message
    assert deprecated.bindings[0].lifecycle == "deprecated"
    assert deprecated.bindings[0].model_dump(exclude={"lifecycle"}) == base.bindings[0].model_dump(
        exclude={"lifecycle"}
    )


# --- proposta sobre entidade herdada (achado E2-04) ------------------------------------------


def _remove(kind: EntityKind, entity_id: str) -> RemoveProposal:
    return RemoveProposal(op="remove", kind=kind, entity_id=entity_id)


def _deprecate(kind: LifecycleKind, entity_id: str) -> DeprecateEntity:
    return DeprecateEntity(op="deprecate", kind=kind, entity_id=entity_id)


def test_withdrawing_a_change_proposed_on_a_published_entity_restores_its_published_bytes() -> None:
    base = f.minimal_content("approved")
    changed = f.concept("draft").model_copy(update={"definition": f.pt("Definição proposta.")})
    proposal = _replace(base, "concepts", changed)

    restored, log = apply_patch(
        proposal,
        DraftPatch(operations=(_remove("concepts", f.CONCEPT_ID),), reason="desistir"),
        base=base,
    )

    assert restored.concepts == base.concepts
    assert content_sha256(restored) == content_sha256(base)
    assert log == (f"restore concepts {f.CONCEPT_ID}",)


def test_identical_reproposal_can_be_withdrawn_and_deprecated_in_one_patch() -> None:
    base = f.minimal_content("approved")
    reproposal = _replace(base, "concepts", f.concept("draft"))
    with pytest.raises(DraftPatchError) as blocked:
        apply_patch(
            reproposal,
            DraftPatch(operations=(_deprecate("concepts", f.CONCEPT_ID),), reason="depreciar"),
            base=base,
        )
    (issue,) = blocked.value.issues
    assert issue.code == "deprecate_requires_unchanged_entity"
    assert "remove" in issue.message

    deprecated, log = apply_patch(
        reproposal,
        DraftPatch(
            operations=(_remove("concepts", f.CONCEPT_ID), _deprecate("concepts", f.CONCEPT_ID)),
            reason="retirar a proposta e depreciar",
        ),
        base=base,
    )

    (concept,) = deprecated.concepts
    assert concept == f.concept("deprecated")
    assert log == (f"restore concepts {f.CONCEPT_ID}", f"deprecate concepts {f.CONCEPT_ID}")
    assert content_diff(base, deprecated).deprecated == (f"concepts:{f.CONCEPT_ID}",)


def test_withdrawing_a_proposed_deprecation_restores_the_published_entity() -> None:
    base = f.minimal_content("approved")
    deprecated, _ = apply_patch(
        base,
        DraftPatch(operations=(_deprecate("bindings", f.BINDING_ID),), reason="depreciar"),
        base=base,
    )

    restored, log = apply_patch(
        deprecated,
        DraftPatch(operations=(_remove("bindings", f.BINDING_ID),), reason="desistir"),
        base=base,
    )

    assert restored == base
    assert log == (f"restore bindings {f.BINDING_ID}",)


def test_withdrawing_a_change_to_a_published_decision_restores_it() -> None:
    pending = ReconciliationDecision(
        id=DECISION_ID,
        code="syn-divergencia",
        status="pending",
        source_assertion_ids=(f.SYN_ASSERTION_ID,),
        summary="Divergência sintética aberta.",
    )
    base = f.minimal_content("approved").model_copy(update={"reconciliation_decisions": (pending,)})
    decided = pending.model_copy(update={"summary": "Divergência sintética reescrita."})

    restored, log = apply_patch(
        _replace(base, "reconciliation_decisions", decided),
        DraftPatch(
            operations=(_remove("reconciliation_decisions", DECISION_ID),), reason="desistir"
        ),
        base=base,
    )

    assert restored.reconciliation_decisions == (pending,)
    assert log == (f"restore reconciliation_decisions {DECISION_ID}",)


def test_patch_that_changes_nothing_is_refused() -> None:
    content = f.minimal_content("draft")
    same = UpsertEntity(
        op="upsert", kind="concepts", entity=f.concept("draft").model_dump(mode="json")
    )

    with pytest.raises(DraftPatchError, match="no_change"):
        apply_patch(content, DraftPatch(operations=(same,), reason="nada"), base=None)


def test_diff_lists_added_changed_and_deprecated_entities() -> None:
    base = f.minimal_content("approved")
    content = _replace(
        _replace(base, "concepts", f.concept("draft").model_copy(update={"labels": f.pt("Novo")})),
        "bindings",
        f.binding("deprecated"),
    )
    content = content.model_copy(update={"units": (f.length_unit(),)})

    diff = content_diff(base, content)

    assert diff.added == (f"units:{f.UNIT_ID}",)
    assert diff.changed == (f"concepts:{f.CONCEPT_ID}",)
    assert diff.deprecated == (f"bindings:{f.BINDING_ID}",)


def test_duplicate_of_a_writable_published_binding_never_inherits_writing() -> None:
    writable = f.binding("approved").model_copy(update={"write_enabled": True})
    base = _replace(f.minimal_content("approved"), "bindings", writable)
    copy_id = "urn:uuid:00000000-0000-4000-8000-0000000d0098"

    duplicated, _ = apply_patch(
        base,
        DraftPatch(
            operations=(
                DuplicateEntity(
                    op="duplicate", kind="bindings", source_id=f.BINDING_ID, new_id=copy_id
                ),
            ),
            reason="duplicar uso publicado com escrita",
        ),
        base=base,
    )

    copy = next(b for b in duplicated.bindings if b.id == copy_id)
    assert (copy.lifecycle, copy.write_enabled) == ("draft", False)
