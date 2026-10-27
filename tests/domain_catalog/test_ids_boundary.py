"""Fronteira IDS/catálogo (Task 4): anexo semântico nunca altera o diagnóstico formal.

IDS e IFC sintéticos, catálogo sintético ``minimal_content`` (binding
``SYN_Conjunto.SYN_Metodo`` em ``IfcSlab``). Nenhuma ausência de cadastro cria
violação formal; alias/outro Pset não satisfaz o caminho literal do IDS.
"""

import hashlib
import shutil
from pathlib import Path
from typing import Any, Literal

import ifcopenshell
import pytest

pytest.importorskip("ifctester", reason="extra e3 não instalado (ifctester==0.8.5)")

from src.domain_catalog.content import CatalogContent
from src.domain_catalog.contracts import CatalogReleaseRef, PredefinedTypeContext
from src.domain_catalog.models import AliasMapping, AliasScope
from src.domain_catalog.reader import CatalogReader, open_catalog
from src.validation.analysis_service import (
    CatalogUnavailable,
    attach_catalog_annotations,
    predefined_type_context,
)
from src.validation.diagnostic_models import DiagnosticSnapshot
from tests.domain_catalog import factories as f
from tests.validation import ids_builders as x
from tests.validation import ifc_builders as ib
from tests.validation.engine_helpers import prepare, run

METODO = x.ids(x.spec("Lajes", x.entity("IFCSLAB"), x.prop("SYN_Conjunto", "SYN_Metodo")))
UNMAPPED = x.ids(x.spec("Lajes", x.entity("IFCSLAB"), x.prop("SYN_Conjunto", "SYN_NaoCadastrado")))


def _slab(
    f_: ifcopenshell.file, pset: str | None = None, field: str = "SYN_Metodo", value: str = "A"
) -> Any:
    slab = ib.element(f_, "IfcSlab")
    if pset is not None:
        ib.pset(f_, slab, pset, [ib.single(f_, field, "IfcLabel", value)])
    return slab


def _reader(
    tmp_path: Path, content: CatalogContent | None = None
) -> tuple[CatalogReader, CatalogReleaseRef, Path]:
    ref, folder = f.write_synthetic_release(tmp_path / "cat", content or f.minimal_content())
    return open_catalog(ref, folder), ref, folder


def _formal(snapshot: DiagnosticSnapshot) -> list[dict[str, object]]:
    return [r.model_dump(mode="json", exclude={"annotation"}) for r in snapshot.requirements]


@pytest.mark.parametrize("present", [True, False])
def test_unmapped_requirement_validates_identically_with_and_without_catalog(
    tmp_path: Path, present: bool
) -> None:
    model = ib.model()
    _slab(model, "SYN_Conjunto" if present else None, field="SYN_NaoCadastrado")
    snapshot = run(tmp_path / "s", model, UNMAPPED)
    reader, ref, _ = _reader(tmp_path)

    with_catalog = attach_catalog_annotations(snapshot, reader)
    without = attach_catalog_annotations(snapshot, CatalogUnavailable(state="not_attached"))

    assert _formal(with_catalog) == _formal(snapshot) == _formal(without)
    assert [r.state for r in snapshot.requirements] == ["compliant" if present else "non_compliant"]
    (annotated,) = with_catalog.requirements
    assert annotated.annotation is not None
    assert annotated.annotation.state == "unresolved"
    assert annotated.annotation.resolution is not None
    assert annotated.annotation.resolution.status == "unmapped"
    assert annotated.annotation.catalog == ref
    assert with_catalog.catalog_runtime_state == "available"
    (bare,) = without.requirements
    assert bare.annotation is not None
    assert (bare.annotation.state, bare.annotation.error_reason) == ("unavailable", "not_attached")


def test_invalid_or_missing_package_is_lateral_problem_not_ids_failure(tmp_path: Path) -> None:
    model = ib.model()
    _slab(model, "SYN_Conjunto")
    snapshot = run(tmp_path / "s", model, METODO)
    states: tuple[Literal["invalid", "unavailable"], ...] = ("invalid", "unavailable")
    for state in states:
        annotated = attach_catalog_annotations(
            snapshot, CatalogUnavailable(state=state, reason="falha simulada")
        )
        assert _formal(annotated) == _formal(snapshot)
        assert [r.state for r in annotated.requirements] == ["compliant"]
        assert annotated.catalog_runtime_state == state
        assert [p.code for p in annotated.problems] == [f"catalog_{state}"]
        assert {r.annotation.state for r in annotated.requirements if r.annotation} == {
            "unavailable"
        }


def test_alias_or_other_pset_never_satisfies_the_literal_ids_path(tmp_path: Path) -> None:
    alias = AliasMapping(
        id="urn:uuid:00000000-0000-4000-8000-00000000a1a5",
        term="Metodo",
        purpose="approved_equivalence",
        scope=AliasScope(set_names=("SYN_Legado",)),
        target_binding_id=f.BINDING_ID,
        lifecycle="approved",
    )
    content = f.minimal_content().model_copy(update={"aliases": (alias,)})
    model = ib.model()
    _slab(model, "SYN_Legado", field="Metodo")
    snapshot = run(tmp_path / "s", model, METODO)
    reader, _, _ = _reader(tmp_path, content)
    annotated = attach_catalog_annotations(snapshot, reader)

    (row,) = annotated.requirements
    assert row.state == "non_compliant"
    assert row.annotation is not None
    assert row.annotation.resolution is not None
    assert row.annotation.resolution.status == "exact"
    assert row.annotation.resolution.binding_id == f.BINDING_ID
    assert row.annotation.request is not None
    assert (row.annotation.request.set_name, row.annotation.request.field_name) == (
        "SYN_Conjunto",
        "SYN_Metodo",
    )


def test_predefined_type_context_preserves_readings_and_origin(tmp_path: Path) -> None:
    model = ib.model()
    typed = ib.element(model, "IfcWall", PredefinedType="NOTDEFINED")
    ib.typed(model, typed, PredefinedType="SOLIDWALL")
    own = ib.element(model, "IfcWall", PredefinedType="PARTITIONING")
    userdefined = ib.element(model, "IfcWall", PredefinedType="USERDEFINED", ObjectType="Muro")
    shared = ib.element(model, "IfcWall")
    ib.typed(model, shared, PredefinedType="SOLIDWALL")
    ib.typed(model, shared, PredefinedType="PARAPET")
    bare = ib.element(model, "IfcWall")
    session, _, _ = prepare(tmp_path, model, METODO)

    def context(inst: Any) -> PredefinedTypeContext:
        return predefined_type_context(
            session, session.element_ref(session.by_express_id(inst.id()))
        )

    first = context(typed)
    assert (first.status, first.effective_origin, first.effective) == (
        "determined",
        "type",
        "SOLIDWALL",
    )
    assert {(r.origin, r.value) for r in first.readings} == {
        ("occurrence", "NOTDEFINED"),
        ("type", "SOLIDWALL"),
    }
    assert (context(own).status, context(own).effective) == ("determined", "PARTITIONING")
    assert context(userdefined).status == "undetermined"
    assert context(shared).status == "undetermined"
    assert context(bare).status == "absent"


def test_annotation_carries_m2_context_and_exact_release_trace(tmp_path: Path) -> None:
    model = ib.model()
    _slab(model, "SYN_Conjunto")
    snapshot = run(tmp_path / "s", model, METODO)
    reader, ref, _ = _reader(tmp_path)
    annotated = attach_catalog_annotations(snapshot, reader)

    (row,) = annotated.requirements
    assert row.annotation is not None
    request = row.annotation.request
    assert request is not None
    assert (request.ifc_schema, request.entity, request.requirement_ref) == (
        "IFC4",
        "IfcSlab",
        row.requirement.key(),
    )
    assert request.predefined_type is not None
    assert row.annotation.resolution is not None
    assert row.annotation.resolution.catalog == ref
    reopened = DiagnosticSnapshot.model_validate(annotated.model_dump(mode="json"))
    assert reopened == annotated
    assert reopened.content_sha256 != snapshot.content_sha256
    assert reopened.identity == snapshot.identity


def test_same_guid_in_two_sources_or_duplicated_in_one_never_merges(tmp_path: Path) -> None:
    guid = "1kTvXnbbzCWw8lcMd1dR4o"
    first, second = ib.model(), ib.model()
    ib.element(first, "IfcSlab", GlobalId=guid)
    ib.element(first, "IfcSlab", GlobalId=guid)
    ib.element(second, "IfcSlab", GlobalId=guid)
    a = run(tmp_path / "a", first, METODO)
    b = run(tmp_path / "b", second, METODO)

    keys_a = {r.element.key() for r in a.requirements if r.element}
    keys_b = {r.element.key() for r in b.requirements if r.element}
    assert len(keys_a) == 2
    assert not keys_a & keys_b
    assert {r.element.guid_state for r in a.requirements if r.element} == {"duplicate"}


def test_sources_bytes_are_identical_after_diagnosis_and_annotation(tmp_path: Path) -> None:
    model = ib.model()
    _slab(model, "SYN_Conjunto")
    session, document, identity = prepare(tmp_path, model, METODO)
    ifc_path = session._path  # caminho da fonte retida da sessão
    before = hashlib.sha256(ifc_path.read_bytes()).hexdigest()
    entity_count = session.entity_count
    from src.domain_catalog.curation import utc_now
    from src.validation.ids_engine import IdsEngine

    snapshot = IdsEngine().evaluate(session, document, identity, clock=utc_now)
    reader, _, folder = _reader(tmp_path)
    catalog_before = {p.name: p.read_bytes() for p in folder.iterdir()}
    attach_catalog_annotations(snapshot, reader)

    assert hashlib.sha256(ifc_path.read_bytes()).hexdigest() == before
    session.verify_unchanged()
    assert session.entity_count == entity_count
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == catalog_before
    shutil.rmtree(folder)
