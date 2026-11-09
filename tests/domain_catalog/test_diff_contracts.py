"""Contratos imutáveis do diff entre releases e suas recusas (adendo E3.2a, Tarefa 1)."""

from typing import Any

import pytest
from pydantic import ValidationError

from src.domain_catalog.canonical import canonical_json_text
from src.domain_catalog.contracts import CatalogReleaseRef
from src.domain_catalog.diff_contracts import (
    CatalogDiff,
    ChangeClass,
    DiffLimits,
    DiffValue,
    EntityChange,
    EntityKey,
    FieldChange,
    ImpactEdge,
    ImpactTrace,
    ManifestChange,
)
from src.domain_catalog.errors import CatalogComparisonError
from tests.domain_catalog import factories as f

CAT = f.SYN_CATALOG_ID
OLD = CatalogReleaseRef(catalog_id=CAT, version="1.0.0", manifest_sha256="a" * 64)
NEW = CatalogReleaseRef(catalog_id=CAT, version="1.1.0", manifest_sha256="b" * 64)
CONCEPT = EntityKey(kind="concepts", id=f.CONCEPT_ID)
BINDING = EntityKey(kind="bindings", id=f.BINDING_ID)
SEM_OP: tuple[ChangeClass, ...] = ("semantic", "operational")


def _v(value: Any) -> DiffValue:
    return DiffValue(json_text=canonical_json_text(value))


def _label_change() -> EntityChange:
    return EntityChange(
        entity=CONCEPT,
        change_kind="modified",
        fields=(
            FieldChange(
                field="labels",
                before=_v([{"lang": "pt-BR", "text": "A"}]),
                after=_v([{"lang": "pt-BR", "text": "B"}]),
                categories=("label",),
                classes=("cosmetic",),
            ),
        ),
    )


def _version_change() -> ManifestChange:
    return ManifestChange(
        field="version",
        before=_v("1.0.0"),
        after=_v("1.1.0"),
        category="release_identity",
        classes=("operational",),
    )


def _edge() -> ImpactEdge:
    return ImpactEdge(
        owner=BINDING, field="concept_id", referenced=CONCEPT, direction="reverse_dependency"
    )


def _trace(target: EntityKey = CONCEPT, snapshot: str = "old", path: tuple = ()) -> ImpactTrace:
    return ImpactTrace(
        origin=CONCEPT,
        target=target,
        snapshot=snapshot,  # type: ignore[arg-type]
        distance=len(path),
        path=path,
    )


def _valid_diff(**changes: object) -> CatalogDiff:
    data: dict[str, object] = {
        "old_ref": OLD,
        "new_ref": NEW,
        "entity_changes": (_label_change(),),
        "manifest_changes": (_version_change(),),
        "impacts": (
            _trace(),
            _trace(BINDING, "old", (_edge(),)),
            _trace(snapshot="new"),
            _trace(BINDING, "new", (_edge(),)),
        ),
    }
    data.update(changes)
    return CatalogDiff.model_validate(data)


def test_diff_values_preserve_json_types_and_missing_vs_null() -> None:
    texts = ["1", "true", '"1"', "null", '"null"', '""', "[]"]
    values = [DiffValue(json_text=text) for text in texts]

    assert [v.value for v in values] == [1, True, "1", None, "null", "", []]
    assert type(values[0].value) is int
    assert type(values[1].value) is bool
    assert len({v.json_text for v in values}) == len(texts)
    for bad in ["1\n", "[1, 2]", '{"b":1,"a":2}', "NaN", "01", '"a"  ']:
        with pytest.raises(ValidationError):
            DiffValue(json_text=bad)
    change = FieldChange(
        field="notes", before=None, after=_v(None), categories=("other",), classes=SEM_OP
    )
    assert change.before is None
    assert change.after is not None
    assert change.after.json_text == "null"


@pytest.mark.parametrize(
    "build",
    [
        lambda: FieldChange(
            field="x", before=None, after=None, categories=("other",), classes=SEM_OP
        ),
        lambda: FieldChange(
            field="x", before=_v(1), after=_v(1), categories=("other",), classes=SEM_OP
        ),
        lambda: FieldChange(field="x", before=_v(1), after=_v(2), categories=(), classes=SEM_OP),
        lambda: FieldChange(
            field="x", before=_v(1), after=_v(2), categories=("other", "other"), classes=SEM_OP
        ),
        lambda: FieldChange(
            field="x", before=_v(1), after=_v(2), categories=("enum", "label"), classes=SEM_OP
        ),
        lambda: FieldChange(
            field="x",
            before=_v(1),
            after=_v(2),
            categories=("other",),
            classes=("operational", "semantic"),
        ),
        lambda: EntityChange(entity=CONCEPT, change_kind="modified", fields=()),
        lambda: EntityChange(
            entity=CONCEPT,
            change_kind="modified",
            fields=(_label_change().fields[0], _label_change().fields[0]),
        ),
        lambda: EntityChange(
            entity=CONCEPT,
            change_kind="modified",
            fields=(
                FieldChange(
                    field="$", before=_v({}), after=_v({}), categories=("other",), classes=SEM_OP
                ),
            ),
        ),
        lambda: EntityChange(
            entity=CONCEPT,
            change_kind="added",
            fields=(
                FieldChange(
                    field="$",
                    before=_v(f.concept().model_dump(mode="json")),
                    after=None,
                    categories=("addition",),
                    classes=SEM_OP,
                ),
            ),
        ),
        lambda: EntityKey(kind="concepts", id="synthetic:linha-001"),
        lambda: EntityKey(kind="source_assertions", id=f.CONCEPT_ID),
        lambda: _trace(BINDING, "old", ()),
        lambda: ImpactTrace(
            origin=CONCEPT, target=BINDING, snapshot="old", distance=2, path=(_edge(),)
        ),
        lambda: ImpactTrace(
            origin=BINDING,
            target=CONCEPT,
            snapshot="old",
            distance=1,
            path=(_edge(),),
        ),
        lambda: ImpactEdge(
            owner=BINDING, field="concept_id", referenced=CONCEPT, direction="forward_contribution"
        ),
        lambda: ImpactEdge(
            owner=BINDING, field="unit_id", referenced=CONCEPT, direction="reverse_dependency"
        ),
        lambda: _valid_diff(impacts=(_trace(snapshot="new"),)),
        lambda: _valid_diff(new_ref=OLD.model_copy(update={"manifest_sha256": "c" * 64})),
        lambda: _valid_diff(
            new_ref=NEW.model_copy(
                update={"catalog_id": "urn:uuid:00000000-0000-4000-8000-0000000000e2"}
            )
        ),
        lambda: _valid_diff(impacts=(*_valid_diff().impacts, _trace(BINDING, "old", (_edge(),)))),
        lambda: _valid_diff(impacts=tuple(reversed(_valid_diff().impacts))),
        lambda: _valid_diff(entity_changes=(), impacts=(_trace(),)),
        lambda: _valid_diff(manifest_changes=(_version_change(), _version_change())),
    ],
)
def test_diff_dtos_reject_incoherent_changes_and_traces(build: Any) -> None:
    with pytest.raises(ValidationError):
        build()


def _added(entity: EntityKey, payload: Any) -> EntityChange:
    return EntityChange(
        entity=entity,
        change_kind="added",
        fields=(
            FieldChange(
                field="$", before=None, after=_v(payload), categories=("addition",), classes=SEM_OP
            ),
        ),
    )


def test_added_removed_payload_matches_entity_key() -> None:
    payload = f.concept().model_dump(mode="json")
    added = _added(CONCEPT, payload)
    assert added.fields[0].after is not None
    assert added.fields[0].after.json_text == canonical_json_text(payload)
    other_id = {**payload, "id": "urn:uuid:00000000-0000-4000-8000-0000000000ff"}
    for bad in (1, None, "texto", other_id, f.binding().model_dump(mode="json")):
        with pytest.raises(ValidationError):
            _added(CONCEPT, bad)


def test_diff_dto_requires_no_changes_iff_same_release() -> None:
    same = CatalogDiff(old_ref=OLD, new_ref=OLD, entity_changes=(), manifest_changes=(), impacts=())
    assert same.same_release
    assert same.no_changes
    assert not same.has_changes
    with pytest.raises(ValidationError):
        CatalogDiff(
            old_ref=OLD,
            new_ref=OLD,
            entity_changes=(),
            manifest_changes=(_version_change(),),
            impacts=(),
        )
    with pytest.raises(ValidationError):
        CatalogDiff(old_ref=OLD, new_ref=NEW, entity_changes=(), manifest_changes=(), impacts=())
    only_version = CatalogDiff(
        old_ref=OLD,
        new_ref=NEW,
        entity_changes=(),
        manifest_changes=(_version_change(),),
        impacts=(),
    )
    assert only_version.has_manifest_changes
    assert not only_version.has_entity_changes
    assert not only_version.no_changes


def test_diff_contract_round_trip_is_deeply_immutable() -> None:
    diff = _valid_diff()
    reloaded = CatalogDiff.model_validate(diff.model_dump(mode="json"))

    assert reloaded == diff
    assert diff.affected_entities == (CONCEPT, BINDING)
    assert diff.affected_concept_ids == (f.CONCEPT_ID,)
    assert diff.affected_binding_ids == (f.BINDING_ID,)
    assert diff.affected_policy_ids == ()
    value = diff.entity_changes[0].fields[0].after
    assert value is not None
    mutable = value.value
    assert isinstance(mutable, list)
    mutable.append("x")
    assert value.value == [{"lang": "pt-BR", "text": "B"}]
    with pytest.raises(ValidationError):
        diff.status = "outro"  # type: ignore[assignment]
    with pytest.raises(ValidationError):
        _valid_diff(no_changes=True)
    with pytest.raises(ValidationError):
        CatalogDiff.model_validate({**diff.model_dump(mode="json"), "extra": 1})


@pytest.mark.parametrize("limit", [True, 0, -1, 1.5])
def test_diff_limits_accept_only_positive_integers(limit: object) -> None:
    with pytest.raises(ValidationError):
        DiffLimits(max_impact_traces=limit)  # type: ignore[arg-type]
    assert DiffLimits().max_impact_traces == 100_000


def test_comparison_error_keeps_reason_refs_and_limit() -> None:
    error = CatalogComparisonError(
        "impact_limit_exceeded", "excedeu", old_ref=OLD, new_ref=NEW, limit=3
    )
    assert (error.reason, error.old_ref, error.new_ref, error.limit, error.code) == (
        "impact_limit_exceeded",
        OLD,
        NEW,
        3,
        "comparison_refused",
    )
    plain = CatalogComparisonError("catalog_id_mismatch", "outro", old_ref=OLD, new_ref=NEW)
    assert plain.limit is None


def _modified(field: str) -> EntityChange:
    return EntityChange(
        entity=CONCEPT,
        change_kind="modified",
        fields=(
            FieldChange(
                field=field,
                before=_v("old"),
                after=_v("new"),
                categories=("other",),
                classes=SEM_OP,
            ),
        ),
    )


@pytest.mark.parametrize(
    "field", ["nonexistent_catalog_field", "definition.0.text", "operation_id"]
)
def test_modified_field_must_be_a_top_level_field_of_the_entity_kind(field: str) -> None:
    """E3-15: inexistente, aninhado ou de outro kind é recusado, também no round-trip."""
    with pytest.raises(ValidationError, match="campo"):
        _modified(field)
    valid = _label_change().model_dump(mode="json")
    valid["fields"][0]["field"] = field
    with pytest.raises(ValidationError):
        EntityChange.model_validate_json(canonical_json_text(valid))


def test_modified_real_top_level_field_is_accepted() -> None:
    """Controle E3-15: ``definition`` é campo superior real de conceito."""
    assert _modified("definition").fields[0].field == "definition"
