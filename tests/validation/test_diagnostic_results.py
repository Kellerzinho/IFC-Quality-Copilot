"""Diagnóstico formal pelo backend real: cinco estados, população, cardinalidade e gates.

Modelos IFC4 e IDS sintéticos, gravados/reabertos; avaliação pelo IfcTester 0.8.5
fixado. Expectativas literais derivadas da matriz de suporte do plano §5.2/§5.3.
"""

import uuid
from pathlib import Path

import ifcopenshell
import pytest
from pydantic import ValidationError

pytest.importorskip("ifctester", reason="extra e3 não instalado (ifctester==0.8.5)")

from src.domain_catalog.curation import utc_now
from src.ifc_analyzer.read_only import IfcSourceError
from src.validation.analysis_identity import ExecutionLimits
from src.validation.diagnostic_models import DiagnosticSnapshot, SpecificationResult
from src.validation.ids_engine import EngineError, IdsEngine
from tests.validation import ids_builders as x
from tests.validation import ifc_builders as ib
from tests.validation.engine_helpers import bundle, prepare, run, states


def _wall(f: ifcopenshell.file, **props: tuple[str | None, object]) -> object:
    wall = ib.element(f)
    if props:
        ib.pset(f, wall, "Pset_X", [ib.single(f, n, t, v) for n, (t, v) in props.items()])
    return wall


def _spec_result(snapshot: DiagnosticSnapshot, index: int = 0) -> SpecificationResult:
    return snapshot.specifications[index]


def test_two_requirements_on_one_element_keep_both_results(tmp_path: Path) -> None:
    f = ib.model()
    wall = _wall(f, A=("IfcLabel", "sim"))
    snapshot = run(
        tmp_path,
        f,
        x.ids(
            x.spec(
                "S",
                x.entity("IFCWALL"),
                x.prop("Pset_X", "A") + x.prop("Pset_X", "B"),
                min_occurs="1",
            )
        ),
    )

    assert states(snapshot) == [
        (0, wall.id(), "compliant", None),  # type: ignore[attr-defined]
        (1, wall.id(), "non_compliant", "requirement_violated"),  # type: ignore[attr-defined]
    ]
    spec = _spec_result(snapshot)
    assert (spec.population_state, spec.member_count, spec.status) == ("known", 1, "violated")
    assert spec.cardinality_evaluation == "satisfied"


def test_interleaved_unsupported_facet_does_not_shift_backend_results(tmp_path: Path) -> None:
    f = ib.model()
    wall = _wall(f, B=("IfcLabel", "b"))
    snapshot = run(
        tmp_path,
        f,
        x.ids(
            x.spec(
                "S",
                x.entity("IFCWALL"),
                x.prop("Pset_X", "A") + x.attribute("Name") + x.prop("Pset_X", "B"),
            )
        ),
    )
    wid = wall.id()  # type: ignore[attr-defined]
    assert states(snapshot) == [
        (0, wid, "non_compliant", "requirement_violated"),
        (1, wid, "not_verified", "unsupported_facet"),
        (2, wid, "compliant", None),
    ]


def test_fresh_backend_per_run_does_not_leak_passes(tmp_path: Path) -> None:
    data = x.ids(x.spec("S", x.entity("IFCWALL"), x.prop("Pset_X", "A")))
    passing, failing = ib.model(), ib.model()
    _wall(passing, A=("IfcLabel", "ok"))
    _wall(failing)
    session_a, document, identity_a = prepare(tmp_path / "a", passing, data)
    session_b, _, identity_b = prepare(tmp_path / "b", failing, data)
    engine = IdsEngine(bundle())

    first = engine.evaluate(session_a, document, identity_a, clock=utc_now)
    second = engine.evaluate(session_b, document, identity_b, clock=utc_now)

    assert [r.state for r in first.requirements] == ["compliant"]
    assert [r.state for r in second.requirements] == ["non_compliant"]


def test_schema_support_and_mismatch_are_distinct(tmp_path: Path) -> None:
    old = ifcopenshell.file(schema="IFC2X3")
    old.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new())
    data = x.ids(x.spec("S", x.entity("IFCWALL"), x.prop("Pset_X", "A")))
    unsupported = run(tmp_path / "a", old, data)
    mismatch = run(
        tmp_path / "b",
        ib.model(),
        x.ids(x.spec("S", x.entity("IFCWALL"), x.prop("Pset_X", "A"), ifc="IFC2X3")),
    )

    assert states(unsupported) == [(0, None, "not_verified", "unsupported_schema")]
    assert states(mismatch) == [(0, None, "not_verified", "schema_mismatch")]
    assert _spec_result(unsupported).population_state == "undetermined"
    assert _spec_result(unsupported).member_count is None


@pytest.mark.parametrize(("min_occurs", "max_occurs"), [("0", "unbounded"), ("0", "0")])
def test_unknown_entity_name_is_never_known_zero_or_satisfied(
    tmp_path: Path, min_occurs: str, max_occurs: str
) -> None:
    data = x.ids(
        x.spec(
            "S",
            x.entity("IFCNOTAREALCLASS"),
            x.prop("Pset_X", "A"),
            min_occurs=min_occurs,
            max_occurs=max_occurs,
        )
    )
    snapshot = run(tmp_path, ib.model(), data)
    spec = _spec_result(snapshot)

    assert (spec.population_state, spec.status, spec.cardinality_evaluation) == (
        "undetermined",
        "not_verified",
        "not_evaluated",
    )
    assert states(snapshot) == [(0, None, "not_verified", "unknown_entity_name")]
    assert [p.code for p in snapshot.problems] == ["unknown_entity_name"]


@pytest.mark.parametrize(
    ("min_occurs", "max_occurs", "status"),
    [("1", "unbounded", "violated"), ("0", "unbounded", "satisfied"), ("0", "0", "satisfied")],
)
def test_existing_class_without_instances_is_known_zero(
    tmp_path: Path, min_occurs: str, max_occurs: str, status: str
) -> None:
    data = x.ids(
        x.spec(
            "S",
            x.entity("IFCWALL"),
            x.prop("Pset_X", "A"),
            min_occurs=min_occurs,
            max_occurs=max_occurs,
        )
    )
    snapshot = run(tmp_path, ib.model(), data)
    spec = _spec_result(snapshot)

    assert (spec.population_state, spec.member_count, spec.members, spec.status) == (
        "known",
        0,
        (),
        status,
    )
    assert states(snapshot) == [(0, None, "not_applicable", "no_applicable_elements")]
    assert snapshot.coverage.known_pairs == 0


def test_applicability_outside_matrix_is_undetermined_and_other_specs_survive(
    tmp_path: Path,
) -> None:
    f = ib.model()
    wall = _wall(f, A=("IfcLabel", "a"))
    data = x.ids(
        x.spec("Fora", x.entity("IFCWALL") + x.prop("Pset_X", "A"), x.prop("Pset_X", "A")),
        x.spec("Dentro", x.entity("IFCWALL"), x.prop("Pset_X", "A")),
    )
    snapshot = run(tmp_path, f, data)

    assert states(snapshot, 0) == [(0, None, "not_verified", "unsupported_applicability")]
    assert _spec_result(snapshot, 0).population_state == "undetermined"
    assert states(snapshot, 1) == [(0, wall.id(), "compliant", None)]  # type: ignore[attr-defined]
    assert snapshot.coverage.known_pairs is None
    assert snapshot.coverage.undetermined_specifications == 1


@pytest.mark.parametrize(
    ("min_occurs", "max_occurs", "reason"),
    [
        ("1", "unbounded", None),
        ("0", "unbounded", None),
        ("0", "0", None),
        (None, "unbounded", None),
        ("2", "unbounded", "unsupported_cardinality"),
        ("0", "1", "unsupported_cardinality"),
        ("1", "1", "unsupported_cardinality"),
        (None, None, "unsupported_cardinality"),
        ("0", None, "unsupported_cardinality"),
        ("1", None, "unsupported_cardinality"),
        ("2", "1", "invalid_cardinality"),
    ],
)
def test_specification_cardinality_matrix(
    tmp_path: Path, min_occurs: str | None, max_occurs: str | None, reason: str | None
) -> None:
    f = ib.model()
    _wall(f, A=("IfcLabel", "a"))
    _wall(f, A=("IfcLabel", "a"))
    snapshot = run(
        tmp_path,
        f,
        x.ids(
            x.spec(
                "S",
                x.entity("IFCWALL"),
                x.prop("Pset_X", "A"),
                min_occurs=min_occurs,
                max_occurs=max_occurs,
            )
        ),
    )
    spec = _spec_result(snapshot)
    if reason is None:
        assert spec.population_state == "known"
        assert spec.member_count == 2
    else:
        assert (spec.population_state, spec.status) == ("undetermined", "not_verified")
        assert states(snapshot) == [(0, None, "not_verified", reason)]
        if reason == "invalid_cardinality":
            assert [p.code for p in snapshot.problems] == ["invalid_cardinality"]


def test_prohibited_specification_with_elements_is_violated_and_requirements_not_applicable(
    tmp_path: Path,
) -> None:
    f = ib.model()
    wall = _wall(f)
    snapshot = run(
        tmp_path,
        f,
        x.ids(
            x.spec("S", x.entity("IFCWALL"), x.prop("Pset_X", "A"), min_occurs="0", max_occurs="0")
        ),
    )

    assert _spec_result(snapshot).status == "violated"
    assert states(snapshot) == [(0, wall.id(), "not_applicable", "prohibited_specification")]  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("cardinality", "present", "expected"),
    [
        ("optional", False, "compliant"),
        ("prohibited", False, "compliant"),
        ("prohibited", True, "non_compliant"),
        (None, False, "non_compliant"),
        (None, True, "compliant"),
    ],
)
def test_property_cardinality_semantics(
    tmp_path: Path, cardinality: str | None, present: bool, expected: str
) -> None:
    f = ib.model()
    _wall(f, **({"A": ("IfcLabel", "a")} if present else {"Outro": ("IfcLabel", "o")}))
    snapshot = run(
        tmp_path,
        f,
        x.ids(x.spec("S", x.entity("IFCWALL"), x.prop("Pset_X", "A", cardinality=cardinality))),
    )

    assert [r.state for r in snapshot.requirements] == [expected]
    expected_field = snapshot.expected_for(snapshot.requirements[0])
    assert expected_field.cardinality == (cardinality or "required")
    assert expected_field.cardinality_origin == ("explicit" if cardinality else "schema_default")


@pytest.mark.parametrize(
    ("field", "data_type", "expected"),
    [
        ("Flag", "IFCBOOLEAN", "compliant"),
        ("Count", "IFCINTEGER", "compliant"),
        ("Nulo", "IFCLABEL", "non_compliant"),
        ("Vazio", "IFCLABEL", "non_compliant"),
        ("Ausente", "IFCLABEL", "non_compliant"),
        ("Texto", "IFCINTEGER", "non_compliant"),
    ],
)
def test_false_zero_null_empty_and_absent_follow_backend_semantics(
    tmp_path: Path, field: str, data_type: str, expected: str
) -> None:
    f = ib.model()
    _wall(
        f,
        Flag=("IfcBoolean", False),
        Count=("IfcInteger", 0),
        Nulo=(None, None),
        Vazio=("IfcLabel", ""),
        Texto=("IfcLabel", "ABC"),
    )
    snapshot = run(
        tmp_path,
        f,
        x.ids(x.spec("S", x.entity("IFCWALL"), x.prop("Pset_X", field, data_type=data_type))),
    )
    assert [r.state for r in snapshot.requirements] == [expected]


@pytest.mark.parametrize(
    ("value", "observed", "expected", "reason"),
    [
        (x.simple(""), "ABC", "not_verified", "unsupported_empty_simple_value"),
        (x.simple(""), "", "not_verified", "unsupported_empty_simple_value"),
        (x.simple("ABC"), "ABC", "compliant", None),
        (x.simple("ABC"), "abc", "non_compliant", "requirement_violated"),
        (None, "ABC", "compliant", None),
        (x.simple("  "), "ABC", "non_compliant", "requirement_violated"),
        (x.simple("  "), "  ", "compliant", None),
        (x.enum("A", "B", "C"), "B", "compliant", None),
        (x.enum("A", "B", "C"), "Z", "non_compliant", "requirement_violated"),
        (x.pattern("A.*"), "ABC", "not_verified", "unsupported_constraint"),
    ],
)
def test_text_value_constraints(
    tmp_path: Path, value: str | None, observed: str, expected: str, reason: str | None
) -> None:
    f = ib.model()
    _wall(f, Target=("IfcLabel", observed))
    snapshot = run(
        tmp_path,
        f,
        x.ids(x.spec("S", x.entity("IFCWALL"), x.prop("Pset_X", "Target", value=value))),
    )
    (row,) = snapshot.requirements
    assert (row.state, row.reason) == (expected, reason)


@pytest.mark.parametrize(
    ("data_type", "value"),
    [("IFCBOOLEAN", x.simple("false")), ("IFCINTEGER", x.simple("0")), (None, x.simple("A"))],
)
def test_bool_int_and_untyped_value_comparisons_are_not_verified(
    tmp_path: Path, data_type: str | None, value: str
) -> None:
    f = ib.model()
    _wall(f, Target=("IfcBoolean", False))
    snapshot = run(
        tmp_path,
        f,
        x.ids(
            x.spec(
                "S",
                x.entity("IFCWALL"),
                x.prop("Pset_X", "Target", data_type=data_type, value=value),
            )
        ),
    )
    (row,) = snapshot.requirements
    assert row.state == "not_verified"
    assert row.reason in {"unsupported_constraint", "unsupported_datatype"}


def test_measure_datatype_is_unsupported_unit(tmp_path: Path) -> None:
    f = ib.model()
    _wall(f, Target=("IfcLengthMeasure", 2.0))
    snapshot = run(
        tmp_path,
        f,
        x.ids(
            x.spec(
                "S", x.entity("IFCWALL"), x.prop("Pset_X", "Target", data_type="IFCLENGTHMEASURE")
            )
        ),
    )
    assert [(r.state, r.reason) for r in snapshot.requirements] == [
        ("not_verified", "unsupported_unit")
    ]


def _overlay_model(
    occurrence_props: list[tuple[str, str, object]] | None,
    occurrence_set: str = "Pset_X",
    type_value: tuple[str, object] = ("IfcInteger", 3),
) -> ifcopenshell.file:
    f = ib.model()
    wall = ib.element(f)
    wall_type = ib.typed(f, wall)
    ib.pset(f, wall_type, "Pset_X", [ib.single(f, "Target", type_value[0], type_value[1])])
    if occurrence_props is not None:
        ib.pset(f, wall, occurrence_set, [ib.single(f, n, t, v) for n, t, v in occurrence_props])
    return f


TARGET_LABEL = x.ids(
    x.spec("S", x.entity("IFCWALL"), x.prop("Pset_X", "Target", data_type="IFCLABEL"))
)


def test_inherited_property_overlay_is_not_verified_even_if_backend_passes(tmp_path: Path) -> None:
    snapshot = run(tmp_path, _overlay_model([("Other", "IfcLabel", "x")]), TARGET_LABEL)
    (row,) = snapshot.requirements
    assert (row.state, row.reason) == ("not_verified", "unsupported_inherited_property_overlay")
    assert row.backend_passed is True
    report = snapshot.report_for(row)
    assert [(o.origin, o.typed_value.value) for o in report.observations] == [("type", 3)]  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        (lambda: _overlay_model(None, type_value=("IfcLabel", "ok")), "compliant"),
        (lambda: _overlay_model(None), "non_compliant"),
        (lambda: _overlay_model([("Target", "IfcLabel", "proprio")]), "compliant"),
        (
            lambda: _overlay_model(
                [("Other", "IfcLabel", "x")], occurrence_set="Pset_Y", type_value=("IfcLabel", "ok")
            ),
            "compliant",
        ),
    ],
)
def test_overlay_neighbours_keep_real_datatype_checks(
    tmp_path: Path, model: object, expected: str
) -> None:
    snapshot = run(tmp_path, model(), TARGET_LABEL)  # type: ignore[operator]
    assert [r.state for r in snapshot.requirements] == [expected]


def test_own_occurrence_value_keeps_divergent_type_observation(tmp_path: Path) -> None:
    snapshot = run(tmp_path, _overlay_model([("Target", "IfcLabel", "proprio")]), TARGET_LABEL)
    report = snapshot.report_for(snapshot.requirements[0])
    assert sorted(o.origin for o in report.observations) == ["occurrence", "type"]


def test_ambiguous_sources_and_unsupported_carriers_are_not_absence(tmp_path: Path) -> None:
    def duplicated() -> ifcopenshell.file:
        f = ib.model()
        wall = ib.element(f)
        ib.pset(f, wall, "Pset_X", [ib.single(f, "Target", "IfcLabel", "a")])
        ib.pset(f, wall, "Pset_X", [ib.single(f, "Target", "IfcLabel", "a")])
        return f

    def enumerated() -> ifcopenshell.file:
        f = ib.model()
        wall = ib.element(f)
        prop = f.create_entity(
            "IfcPropertyEnumeratedValue",
            Name="Target",
            EnumerationValues=[f.create_entity("IfcLabel", "a")],
        )
        ib.pset(f, wall, "Pset_X", [prop])
        return f

    def two_types() -> ifcopenshell.file:
        f = ib.model()
        wall = ib.element(f)
        ib.typed(f, wall)
        ib.typed(f, wall)
        return f

    def quantity_set() -> ifcopenshell.file:
        f = ib.model()
        ib.quantities(f, ib.element(f), "Pset_X", "Target")
        return f

    def with_unit() -> ifcopenshell.file:
        f = ib.model()
        wall = ib.element(f)
        unit = f.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
        prop = f.create_entity(
            "IfcPropertySingleValue",
            Name="Target",
            NominalValue=f.create_entity("IfcLabel", "a"),
            Unit=unit,
        )
        ib.pset(f, wall, "Pset_X", [prop])
        return f

    cases = [
        (duplicated, "ambiguous_source"),
        (enumerated, "unsupported_carrier"),
        (two_types, "ambiguous_source"),
        (quantity_set, "unsupported_carrier"),
        (with_unit, "unsupported_unit"),
    ]
    for index, (build, reason) in enumerate(cases):
        snapshot = run(tmp_path / str(index), build(), TARGET_LABEL)
        assert [(r.state, r.reason) for r in snapshot.requirements] == [("not_verified", reason)], (
            reason
        )


def test_predefined_type_filters_population_and_userdefined_is_unsupported(tmp_path: Path) -> None:
    f = ib.model()
    solid = ib.element(f, PredefinedType="SOLIDWALL")
    ib.element(f, PredefinedType="PARTITIONING")
    ordinary = run(
        tmp_path / "a",
        f,
        x.ids(x.spec("S", x.entity("IFCWALL", "SOLIDWALL"), x.prop("Pset_X", "A"))),
    )
    assert [m.express_id for m in _spec_result(ordinary).members] == [solid.id()]

    userdefined = run(
        tmp_path / "b",
        f,
        x.ids(x.spec("S", x.entity("IFCWALL", "USERDEFINED"), x.prop("Pset_X", "A"))),
    )
    assert states(userdefined) == [(0, None, "not_verified", "unsupported_applicability")]


def test_sources_are_unchanged_and_in_memory_mutation_invalidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = ib.model()
    wall = _wall(f, A=("IfcLabel", "a"))
    data = x.ids(x.spec("S", x.entity("IFCWALL"), x.prop("Pset_X", "A")))
    session, document, identity = prepare(tmp_path, f, data)
    before = (session.signature, session.entity_count)
    snapshot = IdsEngine(bundle()).evaluate(session, document, identity, clock=utc_now)
    assert (snapshot.source_check.signature_before, snapshot.source_check.signature_after) == (
        before[0],
        before[0],
    )
    assert snapshot.source_check.entity_count == before[1]

    from ifctester.ids import Ids  # type: ignore[import-untyped]

    original = Ids.validate

    def mutating(self: Ids, ifc_file: ifcopenshell.file, *args: object, **kwargs: object) -> None:
        original(self, ifc_file, *args, **kwargs)
        ifc_file.by_id(wall.id()).Name = "mutado"  # type: ignore[attr-defined]

    monkeypatch.setattr(Ids, "validate", mutating)
    session2, document2, identity2 = prepare(tmp_path / "b", f, data)
    with pytest.raises(IfcSourceError) as mutated:
        IdsEngine(bundle()).evaluate(session2, document2, identity2, clock=utc_now)
    assert mutated.value.reason == "source_mutated"


def test_snapshot_hash_excludes_metadata_and_detects_tampering(tmp_path: Path) -> None:
    f = ib.model()
    _wall(f, A=("IfcLabel", "a"))
    session, document, identity = prepare(
        tmp_path, f, x.ids(x.spec("S", x.entity("IFCWALL"), x.prop("Pset_X", "A")))
    )
    engine = IdsEngine(bundle())
    first = engine.evaluate(session, document, identity, clock=utc_now)
    second = engine.evaluate(session, document, identity, clock=utc_now, snapshot_id=uuid.uuid4())

    assert first.snapshot_id != second.snapshot_id
    assert first.content_sha256 == second.content_sha256
    data = first.model_dump(mode="json")
    assert DiagnosticSnapshot.model_validate(data) == first
    data["requirements"][0]["state"] = "non_compliant"
    with pytest.raises(ValidationError):
        DiagnosticSnapshot.model_validate(data)


def test_result_row_limit_allows_equality_and_refuses_excess(tmp_path: Path) -> None:
    f = ib.model()
    _wall(f)
    _wall(f)
    data = x.ids(x.spec("S", x.entity("IFCWALL"), x.prop("Pset_X", "A")))
    session, document, identity = prepare(tmp_path, f, data)
    engine = IdsEngine(bundle())
    exact = identity.model_copy(update={"limits": ExecutionLimits(max_result_rows=2)})
    assert len(engine.evaluate(session, document, exact, clock=utc_now).requirements) == 2
    over = identity.model_copy(update={"limits": ExecutionLimits(max_result_rows=1)})
    with pytest.raises(EngineError) as refused:
        engine.evaluate(session, document, over, clock=utc_now)
    assert refused.value.reason == "resource_limit_exceeded"


def test_engine_refuses_sources_other_than_the_identity(tmp_path: Path) -> None:
    f = ib.model()
    _wall(f)
    data = x.ids(x.spec("S", x.entity("IFCWALL"), x.prop("Pset_X", "A")))
    session, document, identity = prepare(tmp_path, f, data)
    other_session, _, _ = prepare(tmp_path / "o", f, data)
    with pytest.raises(EngineError) as foreign:
        IdsEngine(bundle()).evaluate(other_session, document, identity, clock=utc_now)
    assert foreign.value.reason == "identity_mismatch"
    other_ids = x.ids(x.spec("Outro", x.entity("IFCWALL"), x.prop("Pset_X", "A")))
    from src.translator.ids_document import parse_ids_document

    with pytest.raises(EngineError):
        IdsEngine(bundle()).evaluate(
            session, parse_ids_document(other_ids, bundle()), identity, clock=utc_now
        )


def test_type_object_applicability_is_not_verified_and_other_specs_survive(
    tmp_path: Path,
) -> None:
    model = ib.model()
    wall = ib.element(model, "IfcWall")
    ib.pset(model, wall, "Pset_X", [ib.single(model, "Code", "IfcLabel", "A")])
    wall_type = ib.typed(model, wall, "IfcWallType", PredefinedType="STANDARD")
    ib.pset(model, wall_type, "Pset_X", [ib.single(model, "Code", "IfcLabel", "A")])
    doc = x.ids(
        x.spec("paredes", x.entity("IFCWALL"), x.prop("Pset_X", "Code")),
        x.spec("tipos", x.entity("IFCWALLTYPE"), x.prop("Pset_X", "Code")),
    )

    snapshot = run(tmp_path, model, doc)

    assert [(state, reason) for _, _, state, reason in states(snapshot, 0)] == [("compliant", None)]
    assert states(snapshot, 1) == [(0, None, "not_verified", "unsupported_applicability")]
    assert snapshot.specifications[1].population_state == "undetermined"


def test_local_evaluation_error_is_localized_to_its_specification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.ifc_analyzer.observations import IfcObservationReader, SearchPlan, SearchReport

    model = ib.model()
    wall = ib.element(model, "IfcWall")
    ib.pset(model, wall, "Pset_X", [ib.single(model, "Code", "IfcLabel", "A")])
    ib.pset(model, wall, "Pset_Y", [ib.single(model, "Code", "IfcLabel", "A")])
    doc = x.ids(
        x.spec("boa", x.entity("IFCWALL"), x.prop("Pset_X", "Code")),
        x.spec("quebrada", x.entity("IFCWALL"), x.prop("Pset_Y", "Code")),
    )
    original = IfcObservationReader.read

    def failing(self: IfcObservationReader, plan: SearchPlan) -> SearchReport:
        if any(s.set_name == "Pset_Y" for s in plan.selectors):
            raise RuntimeError("falha local simulada")
        return original(self, plan)

    monkeypatch.setattr(IfcObservationReader, "read", failing)
    snapshot = run(tmp_path, model, doc)

    assert [(state, reason) for _, _, state, reason in states(snapshot, 0)] == [("compliant", None)]
    assert states(snapshot, 1) == [(0, None, "error", "evaluation_error")]
    assert [(p.code, p.specification_index) for p in snapshot.problems] == [("evaluation_error", 1)]


def _homonyms(count: int, *, on_type: bool = False, split: int = 0) -> ifcopenshell.file:
    """Parede com ``count`` membros ``Target`` homônimos num só Pset_X (ou no tipo)."""
    f = ib.model()
    wall = ib.element(f)
    owner = ib.typed(f, wall) if on_type else wall
    ib.pset(f, owner, "Pset_X", [ib.single(f, "Target", "IfcLabel", "ok") for _ in range(count)])
    if split:
        type_object = ib.typed(f, wall)
        ib.pset(
            f,
            type_object,
            "Pset_X",
            [ib.single(f, "Target", "IfcLabel", "ok") for _ in range(split)],
        )
    return f


@pytest.mark.parametrize("on_type", [False, True])
def test_homonym_limit_exact_is_ambiguous_and_excess_is_never_compliant(
    tmp_path: Path, on_type: bool
) -> None:
    """E3-01: 512 membros = ambiguidade; 513 excede o limite e nunca vira conformidade."""
    at_limit = run(tmp_path / "a", _homonyms(512, on_type=on_type), TARGET_LABEL)
    assert [(r.state, r.reason) for r in at_limit.requirements] == [
        ("not_verified", "ambiguous_source")
    ]
    over = run(tmp_path / "b", _homonyms(513, on_type=on_type), TARGET_LABEL)
    assert [(r.state, r.reason) for r in over.requirements] == [
        ("not_verified", "context_limit_exceeded")
    ]
    assert over.specifications[0].status == "not_verified"
    assert over.report_for(over.requirements[0]).observations == ()


def test_homonym_limit_is_counted_per_field_across_both_scopes(tmp_path: Path) -> None:
    """E3-01/E3-07: 300 na ocorrência + 300 no tipo excedem 512 por campo (sem truncar)."""
    snapshot = run(tmp_path, _homonyms(300, split=300), TARGET_LABEL)
    assert [(r.state, r.reason) for r in snapshot.requirements] == [
        ("not_verified", "context_limit_exceeded")
    ]
    report = snapshot.report_for(snapshot.requirements[0])
    assert report.observations == ()
    assert {c.status for c in report.coverage} == {"unsupported"}


def _predefined_case(case: str) -> ifcopenshell.file:
    """Parede com a propriedade requerida e PredefinedType que esta condição não determina."""
    f = ib.model()
    if case == "occurrence_userdefined":
        wall = ib.element(f, PredefinedType="USERDEFINED", ObjectType="SOLIDWALL")
    else:
        wall = ib.element(f, PredefinedType="SOLIDWALL")
    ib.pset(f, wall, "Pset_X", [ib.single(f, "A", "IfcLabel", "ok")])
    if case == "type_userdefined":
        ib.typed(f, wall, PredefinedType="USERDEFINED", ElementType="SOLIDWALL")
    elif case == "types_wrong_first":
        ib.typed(f, wall, PredefinedType="PARTITIONING")
        ib.typed(f, wall, PredefinedType="SOLIDWALL")
    elif case == "types_right_first":
        ib.typed(f, wall, PredefinedType="SOLIDWALL")
        ib.typed(f, wall, PredefinedType="PARTITIONING")
    return f


@pytest.mark.parametrize(
    "case",
    ["occurrence_userdefined", "type_userdefined", "types_wrong_first", "types_right_first"],
)
@pytest.mark.parametrize(
    ("min_occurs", "max_occurs"), [("1", "unbounded"), ("0", "unbounded"), ("0", "0")]
)
def test_undetermined_predefined_type_population_is_never_known(
    tmp_path: Path, case: str, min_occurs: str, max_occurs: str
) -> None:
    """E3-02: população que depende de PredefinedType indeterminado não é conhecida nem aprovada."""
    snapshot = run(
        tmp_path,
        _predefined_case(case),
        x.ids(
            x.spec(
                "S",
                x.entity("IFCWALL", "SOLIDWALL"),
                x.prop("Pset_X", "A"),
                min_occurs=min_occurs,
                max_occurs=max_occurs,
            )
        ),
    )
    spec = _spec_result(snapshot)
    assert (spec.population_state, spec.status) == ("undetermined", "not_verified")
    assert spec.reasons == ("undetermined_predefined_type",)
    assert states(snapshot) == [(0, None, "not_verified", "undetermined_predefined_type")]


def test_determined_predefined_type_keeps_ordinary_filter(tmp_path: Path) -> None:
    """Controle E3-02: só ocorrências determinadas → população conhecida e filtrada."""
    f = ib.model()
    solid = ib.element(f, PredefinedType="SOLIDWALL")
    typed_solid = ib.element(f, PredefinedType="NOTDEFINED")
    ib.typed(f, typed_solid, PredefinedType="SOLIDWALL")
    ib.element(f, PredefinedType="PARTITIONING")
    snapshot = run(
        tmp_path, f, x.ids(x.spec("S", x.entity("IFCWALL", "SOLIDWALL"), x.prop("Pset_X", "A")))
    )
    assert [m.express_id for m in _spec_result(snapshot).members] == sorted(
        [solid.id(), typed_solid.id()]
    )


@pytest.mark.parametrize(
    "inner", ["AB<!-- inerte -->C", "AB<?pi x?>C", "<!-- a -->AB<!-- b -->C<!-- c -->"]
)
def test_xml_comment_in_simple_value_is_one_requirement_for_backend_and_candidate(
    tmp_path: Path, inner: str
) -> None:
    """E3-03: inventário, backend e validador de candidato exigem o mesmo texto ``ABC``."""
    from src.ifc_analyzer.observations import TextValue
    from src.validation.candidate_validation import validate_candidate

    data = x.ids(
        x.spec(
            "S",
            x.entity("IFCWALL"),
            x.prop("Pset_X", "A", value=f"<simpleValue>{inner}</simpleValue>"),
        )
    )
    outcomes = {}
    for observed in ("AB", "ABC"):
        f = ib.model()
        ib.pset(f, ib.element(f), "Pset_X", [ib.single(f, "A", "IfcLabel", observed)])
        snapshot = run(tmp_path / observed, f, data)
        outcomes[observed] = snapshot.requirements[0].state
        expected = snapshot.expected_fields[0]
        assert expected.value is not None
        assert expected.value.text == "ABC"
        verifier = snapshot.identity.verifier
        candidate = validate_candidate(expected, TextValue(value=observed), verifier)
        assert candidate.status == ("satisfied" if observed == "ABC" else "violates")
    assert outcomes == {"AB": "non_compliant", "ABC": "compliant"}


def test_exception_in_one_facet_keeps_safe_results_of_the_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E3-10: falha de uma faceta é erro localizado; a outra e a população continuam válidas."""
    from ifctester.facet import Property

    f = ib.model()
    wall = ib.element(f)
    ib.pset(
        f,
        wall,
        "Pset_X",
        [ib.single(f, "Good", "IfcLabel", "ok"), ib.single(f, "Broken", "IfcLabel", "ok")],
    )
    data = x.ids(
        x.spec("S", x.entity("IFCWALL"), x.prop("Pset_X", "Good") + x.prop("Pset_X", "Broken"))
    )
    real_call = Property.__call__

    def failing(self: Property, inst: object, *args: object, **kwargs: object) -> object:
        if self.baseName == "Broken":
            raise RuntimeError("falha localizada sintética")
        return real_call(self, inst, *args, **kwargs)

    monkeypatch.setattr(Property, "__call__", failing)
    snapshot = run(tmp_path, f, data)

    assert states(snapshot) == [
        (0, wall.id(), "compliant", None),
        (1, wall.id(), "error", "evaluation_error"),
    ]
    spec = _spec_result(snapshot)
    assert (spec.population_state, spec.member_count, spec.status) == ("known", 1, "error")
    assert [(p.code, p.specification_index, p.element) for p in snapshot.problems] == [
        ("evaluation_error", 0, snapshot.requirements[1].element)
    ]


@pytest.mark.parametrize("case", ["occurrence_object_type", "type_element_type", "notdefined_type"])
def test_predefined_type_from_object_or_element_type_is_not_verified_not_error(
    tmp_path: Path, case: str
) -> None:
    """M-01 (revisão rodada 2): texto ObjectType/ElementType é capacidade, não erro técnico."""
    f = ib.model()
    if case == "occurrence_object_type":
        wall = ib.element(f, ObjectType="SOLIDWALL")
    elif case == "type_element_type":
        wall = ib.element(f)
        ib.typed(f, wall, ElementType="SOLIDWALL")
    else:
        wall = ib.element(f, ObjectType="SOLIDWALL")
        ib.typed(f, wall, PredefinedType="NOTDEFINED")
    ib.pset(f, wall, "Pset_X", [ib.single(f, "A", "IfcLabel", "ok")])
    snapshot = run(
        tmp_path, f, x.ids(x.spec("S", x.entity("IFCWALL", "SOLIDWALL"), x.prop("Pset_X", "A")))
    )
    spec = _spec_result(snapshot)
    assert (spec.population_state, spec.status) == ("undetermined", "not_verified")
    assert states(snapshot) == [(0, None, "not_verified", "undetermined_predefined_type")]
    assert snapshot.problems == ()


def test_undetermined_member_keeps_safe_results_of_determined_members(tmp_path: Path) -> None:
    """M-02: um USERDEFINED não esconde a violação real de um membro determinado."""
    f = ib.model()
    good = ib.element(f, PredefinedType="SOLIDWALL")
    ib.pset(f, good, "Pset_X", [ib.single(f, "A", "IfcLabel", "ok")])
    bad = ib.element(f, PredefinedType="SOLIDWALL")
    ib.element(f, PredefinedType="USERDEFINED", ObjectType="QUALQUER")
    ib.element(f, PredefinedType="PARTITIONING")
    snapshot = run(
        tmp_path,
        f,
        x.ids(x.spec("S", x.entity("IFCWALL", "SOLIDWALL"), x.prop("Pset_X", "A"), min_occurs="1")),
    )
    spec = _spec_result(snapshot)
    assert (spec.population_state, spec.cardinality_evaluation) == ("undetermined", "not_evaluated")
    assert spec.status == "violated"
    assert states(snapshot) == [
        (0, None, "not_verified", "undetermined_predefined_type"),
        (0, good.id(), "compliant", None),
        (0, bad.id(), "non_compliant", "requirement_violated"),
    ]


def test_undetermined_member_with_all_determined_compliant_is_never_satisfied(
    tmp_path: Path,
) -> None:
    """M-02 controle: sem violação conhecida, a especificação continua não verificada."""
    f = ib.model()
    good = ib.element(f, PredefinedType="SOLIDWALL")
    ib.pset(f, good, "Pset_X", [ib.single(f, "A", "IfcLabel", "ok")])
    ib.element(f, PredefinedType="USERDEFINED", ObjectType="SOLIDWALL")
    snapshot = run(
        tmp_path, f, x.ids(x.spec("S", x.entity("IFCWALL", "SOLIDWALL"), x.prop("Pset_X", "A")))
    )
    assert _spec_result(snapshot).status == "not_verified"
    assert (0, good.id(), "compliant", None) in states(snapshot)


def test_predefined_type_context_failure_is_localized_to_its_specification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M-08: falha no pré-filtro M2 vira erro só da especificação, não do run."""
    import src.validation.ids_engine as engine

    f = ib.model()
    wall = ib.element(f, PredefinedType="SOLIDWALL")
    ib.pset(f, wall, "Pset_X", [ib.single(f, "A", "IfcLabel", "ok")])
    doc = x.ids(
        x.spec("simples", x.entity("IFCWALL"), x.prop("Pset_X", "A")),
        x.spec("tipada", x.entity("IFCWALL", "SOLIDWALL"), x.prop("Pset_X", "A")),
    )

    def failing(instance: object) -> bool:
        raise RuntimeError("falha sintética do pré-filtro M2")

    monkeypatch.setattr(engine, "_text_dependent", failing)
    snapshot = run(tmp_path, f, doc)
    assert [(s, r) for _, _, s, r in states(snapshot, 0)] == [("compliant", None)]
    assert states(snapshot, 1) == [(0, None, "error", "evaluation_error")]


@pytest.mark.parametrize("object_type", [None, "Texto irrelevante da ocorrência"])
@pytest.mark.parametrize("present", [True, False])
def test_ordinary_type_predefined_type_prevails_over_occurrence_object_type(
    tmp_path: Path, object_type: str | None, present: bool
) -> None:
    """R-01: tipo único SOLIDWALL determina; ObjectType da ocorrência é ignorado (backend idem)."""
    f = ib.model()
    wall = ib.element(f, ObjectType=object_type)
    ib.typed(f, wall, PredefinedType="SOLIDWALL")
    if present:
        ib.pset(f, wall, "Pset_X", [ib.single(f, "A", "IfcLabel", "ok")])
    snapshot = run(
        tmp_path, f, x.ids(x.spec("S", x.entity("IFCWALL", "SOLIDWALL"), x.prop("Pset_X", "A")))
    )
    spec = _spec_result(snapshot)
    assert (spec.population_state, spec.member_count) == ("known", 1)
    assert spec.status == ("satisfied" if present else "violated")
    assert states(snapshot) == [
        (0, wall.id(), "compliant", None)
        if present
        else (0, wall.id(), "non_compliant", "requirement_violated")
    ]
    assert snapshot.problems == ()


@pytest.mark.parametrize(
    "case",
    [
        "occurrence_userdefined",
        "type_userdefined_element_type",
        "type_empty_element_type",
        "type_notdefined_occurrence_object_type",
        "no_type_occurrence_object_type",
        "two_types",
    ],
)
def test_text_or_ambiguous_predefined_type_stays_undetermined(tmp_path: Path, case: str) -> None:
    """R-01 controles: USERDEFINED, texto efetivo e tipos múltiplos continuam recusados."""
    f = ib.model()
    if case == "occurrence_userdefined":
        wall = ib.element(f, PredefinedType="USERDEFINED", ObjectType="SOLIDWALL")
    elif case in ("type_notdefined_occurrence_object_type", "no_type_occurrence_object_type"):
        wall = ib.element(f, ObjectType="SOLIDWALL")
    else:
        # Sem ObjectType: só o texto do tipo pode causar a recusa (cobre ``_type_text``).
        wall = ib.element(f)
    if case == "type_userdefined_element_type":
        ib.typed(f, wall, PredefinedType="USERDEFINED", ElementType="SOLIDWALL")
    elif case == "type_empty_element_type":
        ib.typed(f, wall, ElementType="SOLIDWALL")
    elif case == "type_notdefined_occurrence_object_type":
        ib.typed(f, wall, PredefinedType="NOTDEFINED")
    elif case == "two_types":
        ib.typed(f, wall, PredefinedType="SOLIDWALL")
        ib.typed(f, wall, PredefinedType="PARTITIONING")
    ib.pset(f, wall, "Pset_X", [ib.single(f, "A", "IfcLabel", "ok")])
    snapshot = run(
        tmp_path, f, x.ids(x.spec("S", x.entity("IFCWALL", "SOLIDWALL"), x.prop("Pset_X", "A")))
    )
    spec = _spec_result(snapshot)
    assert (spec.population_state, spec.status) == ("undetermined", "not_verified")
    assert states(snapshot) == [(0, None, "not_verified", "undetermined_predefined_type")]


@pytest.mark.parametrize("process_type", ["CONSTRUCTION", "DEMOLITION"])
def test_process_type_text_of_the_type_is_undetermined(tmp_path: Path, process_type: str) -> None:
    """m-04: sem ``ElementType`` o backend lê ``ProcessType`` do tipo; texto não determina."""
    f = ib.model()
    task = ib.element(f, "IfcTask", PredefinedType="CONSTRUCTION")
    ib.typed(f, task, "IfcTaskType", ProcessType=process_type)
    ib.pset(f, task, "Pset_X", [ib.single(f, "A", "IfcLabel", "ok")])
    snapshot = run(
        tmp_path,
        f,
        x.ids(x.spec("S", x.entity("IFCTASK", "CONSTRUCTION"), x.prop("Pset_X", "A"))),
    )
    spec = _spec_result(snapshot)
    assert (spec.population_state, spec.status) == ("undetermined", "not_verified")
    assert states(snapshot) == [(0, None, "not_verified", "undetermined_predefined_type")]
    assert snapshot.problems == ()
