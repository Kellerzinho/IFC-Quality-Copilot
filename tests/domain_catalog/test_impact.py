"""Impacto interno por snapshot: direção, alcance, testemunha mínima e limite (E3.2a T3).

Expectativas literais derivadas à mão dos cenários; não são calculadas pelo
algoritmo sob teste.
"""

from pathlib import Path

import pytest

from src.domain_catalog.content import REFERENCES
from src.domain_catalog.diff import diff_catalogs
from src.domain_catalog.diff_contracts import (
    REFERENCE_DIRECTIONS,
    CatalogDiff,
    DiffLimits,
    EntityKey,
)
from src.domain_catalog.errors import CatalogComparisonError
from tests.domain_catalog import diff_builders as b

U, U2, C1, C2, B1, B2, B3, P1, A, D, M, S, Q, V0, V1 = (b.uid(n) for n in range(1, 16))
R = b.uid(90)
UNIT_C = {"logical_type": "decimal", "dimension": "length"}
LENGTH = {"ifc_type": "IfcLengthMeasure"}


def _key(kind: str, entity_id: str) -> EntityKey:
    return EntityKey(kind=kind, id=entity_id)  # type: ignore[arg-type]


def _reach(diff: CatalogDiff, origin: EntityKey, snapshot: str) -> dict[str, int]:
    return {
        t.target.id: t.distance
        for t in diff.impacts
        if t.origin == origin and t.snapshot == snapshot
    }


def _diff(
    tmp_path: Path, old: object, new: object, limits: DiffLimits | None = None
) -> CatalogDiff:
    return diff_catalogs(
        b.opened(tmp_path / "old", old, "1.0.0"),  # type: ignore[arg-type]
        b.opened(tmp_path / "new", new, "1.1.0"),  # type: ignore[arg-type]
        limits=limits,
    )


def test_impact_directions_cover_all_reference_rules() -> None:
    forward = {
        ("aliases", "target_concept_id", "concepts"),
        ("aliases", "target_binding_id", "bindings"),
        ("profile_memberships", "binding_id", "bindings"),
        ("reconciliation_decisions", "affected_binding_ids", "bindings"),
    }
    assert len(REFERENCES) == 21
    assert set(REFERENCE_DIRECTIONS) == set(REFERENCES)
    assert {k for k, v in REFERENCE_DIRECTIONS.items() if v == "forward_contribution"} == forward
    assert all(REFERENCE_DIRECTIONS[k] == "reverse_dependency" for k in set(REFERENCES) - forward)


def test_shared_unit_reaches_consumers_only(tmp_path: Path) -> None:
    def build(symbol: str) -> object:
        return b.content(
            ("units", b.unit(U, symbol)),
            ("concepts", b.concept(C1, "SYN_C1", unit_id=U, **UNIT_C)),
            ("concepts", b.concept(C2, "SYN_C2", unit_id=U, **UNIT_C)),
            ("applicability_rules", b.rule(R)),
            ("evidence_policies", b.policy(P1)),
            ("bindings", b.binding(B1, C1, R, evidence_policy_id=P1, **LENGTH)),
            ("bindings", b.binding(B2, C1, R, **LENGTH)),
            ("bindings", b.binding(B3, C2, R, **LENGTH)),
        )

    diff = _diff(tmp_path, build("m"), build("metro"))
    expected = {U: 0, C1: 1, C2: 1, B1: 2, B2: 2, B3: 2}
    origin = _key("units", U)
    assert _reach(diff, origin, "old") == expected
    assert _reach(diff, origin, "new") == expected
    assert P1 not in {e.id for e in diff.affected_entities}


def _alias_scenario(target_old: str | None, target_new: str | None) -> tuple[object, object]:
    def build(target: str | None) -> object:
        entities: list[tuple[str, object]] = [
            ("concepts", b.concept(C1)),
            ("applicability_rules", b.rule(R)),
            ("evidence_policies", b.policy(P1)),
            ("bindings", b.binding(B1, C1, R, evidence_policy_id=P1)),
            ("bindings", b.binding(B2, C1, R, evidence_policy_id=P1)),
            ("bindings", b.binding(B3, C1, R)),
        ]
        if target is not None:
            entities.append(("aliases", b.alias(A, "Apelido", target_binding_id=target)))
        return b.content(*entities)  # type: ignore[arg-type]

    return build(target_old), build(target_new)


def test_alias_retarget_uses_old_and_new_targets(tmp_path: Path) -> None:
    diff = _diff(tmp_path, *_alias_scenario(B1, B2))
    origin = _key("aliases", A)

    assert _reach(diff, origin, "old") == {A: 0, B1: 1}
    assert _reach(diff, origin, "new") == {A: 0, B2: 1}
    assert {e.id for e in diff.affected_entities} == {A, B1, B2}


def test_removed_alias_keeps_old_target(tmp_path: Path) -> None:
    diff = _diff(tmp_path, *_alias_scenario(B1, None))
    origin = _key("aliases", A)

    assert _reach(diff, origin, "old") == {A: 0, B1: 1}
    assert _reach(diff, origin, "new") == {}
    assert [c.change_kind for c in diff.entity_changes] == ["removed"]


def test_concept_alias_reaches_its_bindings(tmp_path: Path) -> None:
    def build(term: str) -> object:
        return b.content(
            ("concepts", b.concept(C1)),
            ("applicability_rules", b.rule(R)),
            ("bindings", b.binding(B1, C1, R)),
            ("bindings", b.binding(B2, C1, R)),
            ("aliases", b.alias(A, term, target_concept_id=C1)),
        )

    diff = _diff(tmp_path, build("Antigo"), build("Novo"))
    origin = _key("aliases", A)
    for snapshot in ("old", "new"):
        assert _reach(diff, origin, snapshot) == {A: 0, C1: 1, B1: 2, B2: 2}


def test_decision_retarget_does_not_reach_parent_concepts_or_policies(tmp_path: Path) -> None:
    def build(affected: str) -> object:
        return b.content(
            ("concepts", b.concept(C1)),
            ("applicability_rules", b.rule(R)),
            ("evidence_policies", b.policy(P1)),
            ("bindings", b.binding(B1, C1, R, evidence_policy_id=P1)),
            ("bindings", b.binding(B2, C1, R, evidence_policy_id=P1)),
            ("reconciliation_decisions", b.decision(D, (affected,))),
        )

    diff = _diff(tmp_path, build(B1), build(B2))
    origin = _key("reconciliation_decisions", D)

    assert _reach(diff, origin, "old") == {D: 0, B1: 1}
    assert _reach(diff, origin, "new") == {D: 0, B2: 1}
    assert {e.id for e in diff.affected_entities} == {D, B1, B2}


def test_policy_and_profile_have_separate_causes(tmp_path: Path) -> None:
    def build(operation: str, profile: str) -> object:
        return b.content(
            ("concepts", b.concept(C1)),
            ("applicability_rules", b.rule(R)),
            ("evidence_policies", b.policy(P1, operation)),
            ("bindings", b.binding(B1, C1, R, evidence_policy_id=P1)),
            ("bindings", b.binding(B2, C1, R, evidence_policy_id=P1)),
            ("bindings", b.binding(B3, C1, R)),
            ("profile_memberships", b.membership(M, B3, profile)),
        )

    diff = _diff(
        tmp_path, build("recover_exact_property", "perfil-a"), build("outra_operacao", "perfil-b")
    )
    for snapshot in ("old", "new"):
        assert _reach(diff, _key("evidence_policies", P1), snapshot) == {P1: 0, B1: 1, B2: 1}
        assert _reach(diff, _key("profile_memberships", M), snapshot) == {M: 0, B3: 1}


def test_source_reaches_alias_and_decision_consumers(tmp_path: Path) -> None:
    source, line = "synthetic:diff-s", "synthetic:diff-q"

    def build(title: str) -> object:
        return b.content(
            ("source_artifacts", b.artifact(source, title)),
            ("source_assertions", b.assertion(line, source)),
            ("concepts", b.concept(C1)),
            ("applicability_rules", b.rule(R)),
            ("bindings", b.binding(B1, C1, R)),
            ("bindings", b.binding(B2, C1, R)),
            ("aliases", b.alias(A, "Apelido", target_binding_id=B1, source_assertion_ids=(line,))),
            ("reconciliation_decisions", b.decision(D, (B2,), source_assertion_ids=(line,))),
        )

    diff = _diff(tmp_path, build("Título antigo"), build("Título novo"))
    origin = _key("source_artifacts", source)
    expected = {source: 0, line: 1, A: 2, D: 2, B1: 3, B2: 3}
    assert _reach(diff, origin, "old") == expected
    (to_b1,) = [
        t for t in diff.impacts if t.origin == origin and t.snapshot == "old" and t.target.id == B1
    ]
    assert [(e.owner.id, e.field, e.referenced.id, e.direction) for e in to_b1.path] == [
        (line, "source_artifact_id", source, "reverse_dependency"),
        (A, "source_assertion_ids", line, "reverse_dependency"),
        (A, "target_binding_id", B1, "forward_contribution"),
    ]


def test_value_set_cycle_terminates(tmp_path: Path) -> None:
    def build(ordered: bool) -> object:
        return b.content(
            ("value_sets", b.value_set(V0, ordered=ordered, restricts_value_set_id=V1)),
            ("value_sets", b.value_set(V1, restricts_value_set_id=V0)),
            ("concepts", b.concept(C1, value_set_id=V1)),
            ("applicability_rules", b.rule(R)),
            ("bindings", b.binding(B1, C1, R)),
        )

    diff = _diff(tmp_path, build(False), build(True))
    origin = _key("value_sets", V0)
    for snapshot in ("old", "new"):
        assert _reach(diff, origin, snapshot) == {V0: 0, V1: 1, C1: 2, B1: 3}
    (self_trace,) = [
        t for t in diff.impacts if t.origin == origin and t.target == origin and t.snapshot == "old"
    ]
    assert self_trace.path == ()


def test_no_path_mixes_old_and_new_edges(tmp_path: Path) -> None:
    old = b.content(
        ("units", b.unit(U, "m")),
        ("units", b.unit(U2, "mm")),
        ("concepts", b.concept(C1, "SYN_C1", unit_id=U, **UNIT_C)),
        ("concepts", b.concept(C2, "SYN_C2", unit_id=U2, **UNIT_C)),
        ("applicability_rules", b.rule(R)),
        ("bindings", b.binding(B1, C1, R, **LENGTH)),
    )
    new = b.content(
        ("units", b.unit(U, "metro")),
        ("units", b.unit(U2, "mm")),
        ("concepts", b.concept(C1, "SYN_C1", unit_id=U2, **UNIT_C)),
        ("concepts", b.concept(C2, "SYN_C2", unit_id=U2, **UNIT_C)),
        ("applicability_rules", b.rule(R)),
        ("bindings", b.binding(B1, C2, R, **LENGTH)),
    )
    diff = _diff(tmp_path, old, new)
    origin = _key("units", U)

    assert _reach(diff, origin, "old") == {U: 0, C1: 1, B1: 2}
    assert _reach(diff, origin, "new") == {U: 0}
    roots = {c.entity.id for c in diff.entity_changes}
    assert {U, C1, B1} <= roots
    assert _reach(diff, _key("bindings", B1), "new") == {B1: 0}


def test_multiple_origins_and_routes_keep_deterministic_shortest_witness(tmp_path: Path) -> None:
    line = "synthetic:diff-q"
    value_set_id, concept_id = b.uid(1), b.uid(2)

    def build(note: str, field: str) -> object:
        return b.content(
            ("source_assertions", b.assertion(line, notes=(note,))),
            ("value_sets", b.value_set(value_set_id, source_assertion_ids=(line,))),
            ("concepts", b.concept(concept_id, source_assertion_ids=(line,))),
            ("applicability_rules", b.rule(R)),
            ("bindings", b.binding(B1, concept_id, R, value_set_id=value_set_id, field_name=field)),
        )

    diff = _diff(tmp_path, build("antes", "Campo"), build("depois", "CampoNovo"))
    origin = _key("source_assertions", line)
    (witness,) = [
        t for t in diff.impacts if t.origin == origin and t.snapshot == "old" and t.target.id == B1
    ]

    assert witness.distance == 2
    assert [(e.owner.id, e.field) for e in witness.path] == [
        (value_set_id, "source_assertion_ids"),
        (B1, "value_set_id"),
    ]
    own = [t for t in diff.impacts if t.origin == _key("bindings", B1) and t.target.id == B1]
    assert [t.snapshot for t in own] == ["old", "new"]
    again = _diff(tmp_path / "again", build("antes", "Campo"), build("depois", "CampoNovo"))
    assert again.impacts == diff.impacts


def test_cosmetic_changes_keep_cosmetic_causes(tmp_path: Path) -> None:
    def build(label: str) -> object:
        return b.content(
            ("concepts", b.concept(C1, labels=b.pt(label))),
            ("applicability_rules", b.rule(R)),
            ("bindings", b.binding(B1, C1, R)),
        )

    diff = _diff(tmp_path, build("Rótulo"), build("Rótulo novo"))
    (change,) = diff.entity_changes
    assert change.entity == _key("concepts", C1)
    assert [f.classes for f in change.fields] == [("cosmetic",)]
    assert _reach(diff, change.entity, "new") == {C1: 0, B1: 1}


def test_impact_limit_refuses_without_partial_diff(tmp_path: Path) -> None:
    old, new = _alias_scenario(B1, B2)
    with pytest.raises(CatalogComparisonError) as refused:
        _diff(tmp_path / "a", old, new, DiffLimits(max_impact_traces=3))
    assert (refused.value.reason, refused.value.limit) == ("impact_limit_exceeded", 3)
    complete = _diff(tmp_path / "b", old, new, DiffLimits(max_impact_traces=4))
    assert len(complete.impacts) == 4
