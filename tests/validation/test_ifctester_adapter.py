"""Adaptador IfcTester 0.8.5: objetos novos, correlação conferida e execução serializada."""

import importlib.metadata
import threading
from pathlib import Path

import pytest

pytest.importorskip("ifctester", reason="extra e3 não instalado (ifctester==0.8.5)")

from src.domain_catalog.curation import utc_now
from src.validation.ids_engine import IdsEngine
from src.validation.ifctester_adapter import BackendError, run_specification
from tests.validation import ids_builders as x
from tests.validation import ifc_builders as ib
from tests.validation.engine_helpers import bundle, prepare


def test_backend_versions_are_the_pinned_ones() -> None:
    assert importlib.metadata.version("ifctester") == "0.8.5"
    assert importlib.metadata.version("ifcopenshell") == "0.8.5"


def test_default_library_entry_points_are_never_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ifctester.ids as ids_module  # type: ignore[import-untyped]

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("entrada padrão do IfcTester usada")

    for name in ("open", "from_string", "get_schema"):
        monkeypatch.setattr(ids_module, name, forbidden)
    f = ib.model()
    wall = ib.element(f)
    ib.pset(f, wall, "Pset_X", [ib.single(f, "A", "IfcLabel", "a")])
    session, document, identity = prepare(
        tmp_path, f, x.ids(x.spec("S", x.entity("IFCWALL"), x.prop("Pset_X", "A")))
    )
    snapshot = IdsEngine(bundle()).evaluate(session, document, identity, clock=utc_now)
    assert [r.state for r in snapshot.requirements] == ["compliant"]


def test_per_facet_outcomes_are_read_per_element(tmp_path: Path) -> None:
    f = ib.model()
    first, second = ib.element(f), ib.element(f)
    ib.pset(f, first, "Pset_X", [ib.single(f, "A", "IfcLabel", "a")])
    ib.pset(f, second, "Pset_X", [ib.single(f, "B", "IfcLabel", "b")])
    session, document, _ = prepare(
        tmp_path,
        f,
        x.ids(x.spec("S", x.entity("IFCWALL"), x.prop("Pset_X", "A") + x.prop("Pset_X", "B"))),
    )
    spec = document.specifications[0]
    run = run_specification(session.backend_model(), document, spec, list(spec.requirements))

    assert {i: {e: o.passed for e, o in out.items()} for i, out in run.outcomes.items()} == {
        0: {first.id(): True, second.id(): False},
        1: {first.id(): False, second.id(): True},
    }


def test_correlation_mismatch_is_refused_not_guessed(tmp_path: Path) -> None:
    f = ib.model()
    ib.element(f)
    session, document, _ = prepare(
        tmp_path,
        f,
        x.ids(x.spec("S", x.entity("IFCWALL"), x.prop("Pset_X", "A") + x.prop("Pset_X", "B"))),
    )
    spec = document.specifications[0]
    forged = spec.requirements[1].model_copy(update={"occurrence_index": 0})
    with pytest.raises(BackendError) as refused:
        run_specification(session.backend_model(), document, spec, [forged])
    assert refused.value.reason == "backend_inconsistency"


def test_concurrent_evaluations_are_serialized_and_independent(tmp_path: Path) -> None:
    data = x.ids(x.spec("S", x.entity("IFCWALL"), x.prop("Pset_X", "A")))
    prepared = []
    for index in range(4):
        f = ib.model()
        wall = ib.element(f)
        if index % 2 == 0:
            ib.pset(f, wall, "Pset_X", [ib.single(f, "A", "IfcLabel", "a")])
        prepared.append(prepare(tmp_path / str(index), f, data))
    results: dict[int, list[str]] = {}
    barrier = threading.Barrier(len(prepared))

    def evaluate(index: int) -> None:
        session, document, identity = prepared[index]
        barrier.wait()
        snapshot = IdsEngine(bundle()).evaluate(session, document, identity, clock=utc_now)
        results[index] = [r.state for r in snapshot.requirements]

    threads = [threading.Thread(target=evaluate, args=(i,)) for i in range(len(prepared))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert results == {
        0: ["compliant"],
        1: ["non_compliant"],
        2: ["compliant"],
        3: ["non_compliant"],
    }
