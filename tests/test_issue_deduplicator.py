"""Testes para IssueDeduplicator e assinatura estrutural."""

from __future__ import annotations

from src.models import Issue
from src.suggestion_engine.issue_deduplicator import (
    IssueDeduplicator,
    compute_structural_signature,
    equivalence_id_for_issue,
    structural_fingerprint_payload,
)


def _wall_thermal_issue(guid_seed: str = "A") -> Issue:
    return Issue(
        element_guid=guid_seed * 22,
        element_class="IfcWall",
        element_name="Wall",
        issue_type="pset_missing",
        severity="high",
        description="ThermalTransmittance ausente",
        context={
            "check_pset": "Pset_WallCommon",
            "check_property": "ThermalTransmittance",
            "expected_type": "real",
            "expected_unit": "W/(m2.K)",
            "material_name": "Bloco ceramico",
            "thickness_m": 0.14,
        },
    )


def _wall_fire_issue() -> Issue:
    return Issue(
        element_guid="B" * 22,
        element_class="IfcWall",
        element_name="Wall",
        issue_type="pset_missing",
        severity="medium",
        description="FireRating ausente",
        context={
            "check_pset": "Pset_WallCommon",
            "check_property": "FireRating",
            "material_name": "Bloco ceramico",
            "thickness_m": 0.14,
        },
    )


def _space_issue(guid_seed: str = "C") -> Issue:
    return Issue(
        element_guid=guid_seed * 22,
        element_class="IfcSpace",
        element_name="Room",
        issue_type="space_unnamed",
        severity="low",
        description="Espaco sem nome",
        context={},
    )


def _space_with_context(guid_seed: str = "C", area: float = 12.0) -> Issue:
    return Issue(
        element_guid=guid_seed * 22,
        element_class="IfcSpace",
        element_name="Room 1",
        issue_type="space_unnamed",
        severity="low",
        description="Espaco sem nome",
        context={
            "area_m2": area,
            "contained_elements": [
                {
                    "ifc_class": "IfcSanitaryTerminal",
                    "functional_label": "WC",
                    "name": "Vaso sanitario",
                }
            ],
        },
    )


def _door_fire_issue(guid_seed: str, material_name: str | None, name: str = "Door") -> Issue:
    return Issue(
        element_guid=guid_seed * 22,
        element_class="IfcDoor",
        element_name=name,
        issue_type="pset_missing",
        severity="high",
        description="FireRating ausente",
        context={
            "pset_name": "Pset_DoorCommon",
            "check_property": "FireRating",
            "material_name": material_name,
        },
    )


def test_signature_equal_for_same_structure():
    a = _wall_thermal_issue("A")
    b = _wall_thermal_issue("B")
    assert compute_structural_signature(a) == compute_structural_signature(b)


def test_signature_differs_by_property():
    a = _wall_thermal_issue("A")
    b = _wall_fire_issue()
    assert compute_structural_signature(a) != compute_structural_signature(b)


def test_signature_differs_by_issue_type():
    a = _wall_thermal_issue("A")
    s = _space_issue()
    assert compute_structural_signature(a) != compute_structural_signature(s)


def test_signature_differs_by_element_class():
    a = _wall_thermal_issue("A")
    b = _wall_thermal_issue("B")
    b.element_class = "IfcDoor"
    assert compute_structural_signature(a) != compute_structural_signature(b)


def test_group_issues_groups_equivalent_walls():
    a = _wall_thermal_issue("A")
    b = _wall_thermal_issue("B")
    c = _wall_thermal_issue("C")
    fire = _wall_fire_issue()

    groups = IssueDeduplicator().group_issues([a, b, fire, c])

    assert a.id in groups
    assert sorted(groups[a.id]) == sorted([a.id, b.id, c.id])
    assert fire.id in groups
    assert groups[fire.id] == [fire.id]


def test_build_reuse_map_returns_only_secondaries():
    a = _wall_thermal_issue("A")
    b = _wall_thermal_issue("B")
    c = _space_with_context("C")

    reuse = IssueDeduplicator().build_reuse_map([a, b, c])

    assert reuse == {b.id: a.id}
    assert a.id not in reuse
    assert c.id not in reuse


def test_build_reuse_map_empty_when_all_distinct():
    a = _wall_thermal_issue("A")
    fire = _wall_fire_issue()
    space = _space_issue()
    reuse = IssueDeduplicator().build_reuse_map([a, fire, space])
    assert reuse == {}


def test_sparse_spaces_are_not_reused():
    a = _space_issue("A")
    b = _space_issue("B")

    reuse = IssueDeduplicator().build_reuse_map([a, b])

    assert reuse == {}
    assert compute_structural_signature(a) != compute_structural_signature(b)


def test_spaces_with_different_context_are_not_reused():
    bathroom = _space_with_context("A", area=4.0)
    living = _space_with_context("B", area=22.0)
    living.context["contained_elements"] = [
        {
            "ifc_class": "IfcFurnishingElement",
            "functional_label": "sofa/poltrona",
            "name": "Sofa",
        }
    ]

    reuse = IssueDeduplicator().build_reuse_map([bathroom, living])

    assert reuse == {}
    assert compute_structural_signature(bathroom) != compute_structural_signature(living)


def test_door_material_changes_signature():
    wooden = _door_fire_issue("A", "Madeira macica", "Porta Madeira")
    glass = _door_fire_issue("B", "Vidro temperado", "Porta Vidro")

    assert compute_structural_signature(wooden) != compute_structural_signature(glass)
    assert IssueDeduplicator().build_reuse_map([wooden, glass]) == {}


def test_sparse_doors_are_not_reused():
    a = _door_fire_issue("A", None)
    b = _door_fire_issue("B", None)

    reuse = IssueDeduplicator().build_reuse_map([a, b])

    assert reuse == {}


def test_equivalence_id_is_public_and_stable_for_safe_reuse():
    first = _wall_thermal_issue("A")
    second = _wall_thermal_issue("B")

    assert equivalence_id_for_issue(first) == equivalence_id_for_issue(second)
    assert len(equivalence_id_for_issue(first)) == len("eq-") + 16
    assert equivalence_id_for_issue(first).startswith("eq-")


def test_equivalence_id_is_unique_for_unsafe_issues():
    first = _space_issue("A")
    second = _space_issue("B")

    assert equivalence_id_for_issue(first) != equivalence_id_for_issue(second)
    assert structural_fingerprint_payload(first)["unique_issue_id"] == first.id
    assert structural_fingerprint_payload(second)["unique_issue_id"] == second.id


def test_equivalence_id_ignores_context_insertion_order():
    first = _wall_thermal_issue("A")
    second = _wall_thermal_issue("B")
    second.context = dict(reversed(list(second.context.items())))

    assert equivalence_id_for_issue(first) == equivalence_id_for_issue(second)


def test_grouping_uses_the_same_public_equivalence_identity():
    first = _wall_thermal_issue("A")
    second = _wall_thermal_issue("B")
    distinct = _wall_fire_issue()

    groups = IssueDeduplicator().group_issues([first, second, distinct])

    members_by_equivalence = {
        equivalence_id_for_issue(issue): issue.id
        for issue in (first, second, distinct)
    }
    assert sorted(groups[first.id]) == sorted([first.id, second.id])
    assert members_by_equivalence[equivalence_id_for_issue(distinct)] == distinct.id
