"""Identidade de elemento, sessão IFC somente leitura e observações literais (M2 §6)."""

import shutil
import uuid
from pathlib import Path

import ifcopenshell
import pytest
from pydantic import ValidationError

from src.ifc_analyzer.identity import ElementRef
from src.ifc_analyzer.observations import (
    BooleanValue,
    EvidenceObservation,
    IfcObservationReader,
    IntegerValue,
    ObservationRefused,
    SearchReport,
    TextValue,
    build_search_plan,
)
from src.ifc_analyzer.read_only import IfcSourceError, ReadOnlyIfcSession
from tests.validation import ifc_builders as ib

ANALYSIS = uuid.UUID("5555aaaa-5555-4555-8555-555555555555")


def _session(tmp_path: Path, f: ifcopenshell.file, name: str = "m.ifc") -> ReadOnlyIfcSession:
    path, ref = ib.write(f, tmp_path / name)
    return ReadOnlyIfcSession.open(ref, path)


def _read(
    session: ReadOnlyIfcSession,
    wall: object,
    selectors: list[tuple[str, str, str]],
    scopes: tuple[str, ...] = ("occurrence", "type"),
    **limits: int,
) -> SearchReport:
    element = session.element_ref(session.by_express_id(wall.id()))  # type: ignore[attr-defined]
    plan = build_search_plan(ANALYSIS, element, selectors, scopes)  # type: ignore[arg-type]
    return IfcObservationReader(session, ANALYSIS, **limits).read(plan)


def test_element_identity_is_source_bytes_and_express_id_never_guid(tmp_path: Path) -> None:
    f = ib.model()
    wall = ib.element(f, GlobalId="2O2Fr$t4X7Zf8NOew3FLOH")
    twin = ib.element(f, GlobalId="2O2Fr$t4X7Zf8NOew3FLOH")
    bad = ib.element(f, GlobalId="nao-e-guid")
    first = _session(tmp_path / "a", f)
    second = _session(tmp_path / "b", f, "copia.ifc")

    a = first.element_ref(first.by_express_id(wall.id()))
    b = first.element_ref(first.by_express_id(twin.id()))
    c = second.element_ref(second.by_express_id(wall.id()))
    assert (a.guid_state, b.guid_state) == ("duplicate", "duplicate")
    assert a.key() != b.key()
    assert a.global_id == c.global_id
    assert a.key() != c.key()
    assert first.element_ref(first.by_express_id(bad.id())).guid_state == "invalid"
    assert set(first.guid_index()["2O2Fr$t4X7Zf8NOew3FLOH"]) == {a, b}
    with pytest.raises(ValidationError):
        ElementRef.model_validate({**a.model_dump(), "guid_state": "valid", "global_id": None})


def test_session_refuses_tampered_oversized_or_unreadable_sources(tmp_path: Path) -> None:
    path, ref = ib.write(ib.model(), tmp_path / "m.ifc")
    with pytest.raises(IfcSourceError) as limit:
        ReadOnlyIfcSession.open(ref, path, max_bytes=ref.size_bytes - 1)
    assert limit.value.reason == "resource_limit_exceeded"
    assert ReadOnlyIfcSession.open(ref, path, max_bytes=ref.size_bytes).entity_count >= 1
    with pytest.raises(IfcSourceError) as entities:
        ReadOnlyIfcSession.open(ref, path, max_entities=0)
    assert entities.value.reason == "resource_limit_exceeded"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(IfcSourceError) as tampered:
        ReadOnlyIfcSession.open(ref, path)
    assert tampered.value.reason == "artifact_integrity_error"


def test_in_memory_or_on_disk_mutation_is_detected(tmp_path: Path) -> None:
    f = ib.model()
    wall = ib.element(f, Name="Parede")
    path, ref = ib.write(f, tmp_path / "m.ifc")
    session = ReadOnlyIfcSession.open(ref, path)
    session.verify_unchanged()
    session.backend_model().by_id(wall.id()).Name = "Alterada"
    with pytest.raises(IfcSourceError) as memory:
        session.verify_unchanged()
    assert memory.value.reason == "source_mutated"

    disk = ReadOnlyIfcSession.open(ref, Path(shutil.copy(path, tmp_path / "copia.ifc")))
    (tmp_path / "copia.ifc").write_bytes(path.read_bytes() + b" ")
    with pytest.raises(IfcSourceError) as on_disk:
        disk.verify_unchanged()
    assert on_disk.value.reason == "source_mutated"


def test_false_zero_null_empty_and_absent_are_distinct(tmp_path: Path) -> None:
    f = ib.model()
    wall = ib.element(f)
    ib.pset(
        f,
        wall,
        "Pset_X",
        [
            ib.single(f, "Flag", "IfcBoolean", False),
            ib.single(f, "Count", "IfcInteger", 0),
            ib.single(f, "Nulo", None),
            ib.single(f, "Vazio", "IfcLabel", ""),
            ib.single(f, "Texto", "IfcLabel", "Café  "),
        ],
    )
    session = _session(tmp_path, f)
    report = _read(
        session,
        wall,
        [("Pset_X", n, "teste") for n in ("Flag", "Count", "Nulo", "Vazio", "Texto", "Ausente")],
    )
    by_field = {o.field_name: o for o in report.observations}

    assert by_field["Flag"].typed_value == BooleanValue(value=False)
    assert by_field["Count"].typed_value == IntegerValue(value=0)
    assert (by_field["Nulo"].state, by_field["Nulo"].typed_value) == ("null", None)
    assert (by_field["Vazio"].state, by_field["Vazio"].typed_value) == (
        "empty",
        TextValue(value=""),
    )
    assert by_field["Texto"].typed_value == TextValue(value="Café  ")
    assert by_field["Texto"].unit_state == "not_applicable"
    assert by_field["Texto"].raw_representation == "decoded_ifc_value"
    assert "Ausente" not in by_field
    absent = [c for c in report.coverage if c.field_name == "Ausente"]
    assert {(c.scope, c.status) for c in absent} == {
        ("occurrence", "complete"),
        ("type", "complete"),
    }


def test_type_and_occurrence_observations_keep_provenance(tmp_path: Path) -> None:
    f = ib.model()
    wall = ib.element(f)
    wall_type = ib.typed(f, wall)
    ib.pset(f, wall, "Pset_X", [ib.single(f, "Target", "IfcLabel", "A")])
    ib.pset(f, wall_type, "Pset_X", [ib.single(f, "Target", "IfcLabel", "B")])
    session = _session(tmp_path, f)
    report = _read(session, wall, [("Pset_X", "Target", "teste")])

    origins = {(o.origin, o.owner.ifc_class, o.typed_value) for o in report.observations}
    assert origins == {
        ("occurrence", "IfcWall", TextValue(value="A")),
        ("type", "IfcWallType", TextValue(value="B")),
    }
    type_obs = next(o for o in report.observations if o.origin == "type")
    assert type_obs.type_relation_express_id is not None
    occurrence_only = _read(session, wall, [("Pset_X", "Target", "teste")], ("occurrence",))
    assert [o.origin for o in occurrence_only.observations] == ["occurrence"]
    assert {(c.scope, c.status) for c in occurrence_only.coverage} == {
        ("occurrence", "complete"),
        ("type", "not_searched"),
    }


def test_duplicates_and_unsupported_carriers_are_observed_not_dropped(tmp_path: Path) -> None:
    f = ib.model()
    wall = ib.element(f)
    ib.pset(f, wall, "Pset_X", [ib.single(f, "Target", "IfcLabel", "A")])
    ib.pset(f, wall, "Pset_X", [ib.single(f, "Target", "IfcLabel", "A")])
    enumerated = f.create_entity(
        "IfcPropertyEnumeratedValue",
        Name="Enum",
        EnumerationValues=[f.create_entity("IfcLabel", "X")],
    )
    ib.pset(f, wall, "Pset_Y", [enumerated, ib.single(f, "Medida", "IfcReal", 1.5)])
    ib.quantities(f, wall, "Qto_X", "Comprimento")
    session = _session(tmp_path, f)
    report = _read(
        session,
        wall,
        [
            ("Pset_X", "Target", "t"),
            ("Pset_Y", "Enum", "t"),
            ("Pset_Y", "Medida", "t"),
            ("Qto_X", "Comprimento", "t"),
        ],
    )
    targets = [o for o in report.observations if o.field_name == "Target"]
    assert len(targets) == 2
    assert targets[0].set_express_id != targets[1].set_express_id
    enum_obs = next(o for o in report.observations if o.field_name == "Enum")
    assert (enum_obs.state, enum_obs.carrier_kind) == ("unsupported", "IfcPropertyEnumeratedValue")
    real = next(o for o in report.observations if o.field_name == "Medida")
    assert (real.state, real.typed_value, real.raw_value) == (
        "unsupported",
        None,
        {"ifc_type": "IfcReal", "decimal": "1.5"},
    )
    quantity = next(o for o in report.observations if o.field_name == "Comprimento")
    assert (quantity.state, quantity.set_class) == ("unsupported", "IfcElementQuantity")


def test_type_scope_is_complete_only_with_unique_or_absent_type(tmp_path: Path) -> None:
    f = ib.model()
    lone, shared = ib.element(f), ib.element(f)
    ib.typed(f, shared)
    ib.typed(f, shared)
    session = _session(tmp_path, f)

    lone_report = _read(session, lone, [("Pset_X", "Target", "t")])
    multi_report = _read(session, shared, [("Pset_X", "Target", "t")])

    assert next(c for c in lone_report.coverage if c.scope == "type").status == "complete"
    multi = next(c for c in multi_report.coverage if c.scope == "type")
    assert (multi.status, multi.reason) == ("partial", "multiple_types")


def test_reader_refuses_foreign_element_or_analysis(tmp_path: Path) -> None:
    f = ib.model()
    wall = ib.element(f)
    session, other = _session(tmp_path / "a", f), _session(tmp_path / "b", f)
    foreign = other.element_ref(other.by_express_id(wall.id()))
    plan = build_search_plan(ANALYSIS, foreign, [("P", "A", "t")], ("occurrence",))
    with pytest.raises(ObservationRefused):
        IfcObservationReader(session, ANALYSIS).read(plan)
    mine = session.element_ref(session.by_express_id(wall.id()))
    with pytest.raises(ObservationRefused):
        IfcObservationReader(session, uuid.uuid4()).read(
            build_search_plan(ANALYSIS, mine, [("P", "A", "t")], ("occurrence",))
        )


def test_observation_limit_refuses_without_truncation(tmp_path: Path) -> None:
    f = ib.model()
    wall = ib.element(f)
    for _ in range(3):
        ib.pset(f, wall, "Pset_X", [ib.single(f, "Target", "IfcLabel", "A")])
    session = _session(tmp_path, f)
    exact = _read(session, wall, [("Pset_X", "Target", "t")], ("occurrence",), max_observations=3)
    assert len(exact.observations) == 3
    over = _read(session, wall, [("Pset_X", "Target", "t")], ("occurrence",), max_observations=2)
    assert over.observations == ()
    (coverage,) = [c for c in over.coverage if c.scope == "occurrence"]
    assert (coverage.status, coverage.reason) == ("unsupported", "context_limit_exceeded")


def test_selectors_are_deduplicated_preserving_reasons_and_limited(tmp_path: Path) -> None:
    f = ib.model()
    wall = ib.element(f)
    session = _session(tmp_path, f)
    element = session.element_ref(session.by_express_id(wall.id()))
    plan = build_search_plan(
        ANALYSIS,
        element,
        [("P", "B", "alias-2"), ("P", "A", "ids"), ("P", "B", "alias-1")],
        ("type", "occurrence"),
    )
    assert [(s.set_name, s.field_name, s.reasons) for s in plan.selectors] == [
        ("P", "A", ("ids",)),
        ("P", "B", ("alias-1", "alias-2")),
    ]
    assert plan.admitted_scopes == ("occurrence", "type")
    assert (
        len(
            build_search_plan(
                ANALYSIS, element, [("P", "A", "t")] * 1, ("type",), max_selectors=1
            ).selectors
        )
        == 1
    )
    with pytest.raises(ObservationRefused) as refused:
        build_search_plan(
            ANALYSIS, element, [("P", "A", "t"), ("P", "B", "t")], ("type",), max_selectors=1
        )
    assert refused.value.reason == "context_limit_exceeded"


def test_observation_ids_are_content_hashes(tmp_path: Path) -> None:
    f = ib.model()
    wall = ib.element(f)
    ib.pset(f, wall, "Pset_X", [ib.single(f, "Target", "IfcLabel", "A")])
    session = _session(tmp_path, f)
    (observation,) = _read(session, wall, [("Pset_X", "Target", "t")], ("occurrence",)).observations
    data = observation.model_dump(mode="json")

    assert EvidenceObservation.model_validate(data) == observation
    with pytest.raises(ValidationError):
        EvidenceObservation.model_validate({**data, "typed_value": {"tag": "string", "value": "Z"}})
    with pytest.raises(ValidationError):
        EvidenceObservation.model_validate({**data, "observation_id": "0" * 64})


def test_aggregate_limit_keeps_coverage_that_was_already_incomplete(tmp_path: Path) -> None:
    """M-06: excesso agregado não apaga ``partial/multiple_types`` (nem outro motivo anterior)."""
    f = ib.model()
    wall = ib.element(f)
    ib.pset(f, wall, "P", [ib.single(f, "A", "IfcLabel", "x")])
    for _ in range(2):
        ib.pset(f, ib.typed(f, wall), "P", [ib.single(f, "A", "IfcLabel", "x")])
    report = _read(_session(tmp_path, f), wall, [("P", "A", "t")], max_observations=2)
    assert report.observations == ()
    by_scope = {c.scope: (c.status, c.reason) for c in report.coverage}
    assert by_scope == {
        "occurrence": ("unsupported", "context_limit_exceeded"),
        "type": ("partial", "multiple_types"),
    }
