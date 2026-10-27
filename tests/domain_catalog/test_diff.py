"""Comparação tipada, manifesto e preflight de identidade (adendo E3.2a, Tarefa 2).

Pacotes sintéticos reais: ``build_release_files`` → ``write_release_dir`` →
``open_catalog``. Nenhuma validação ou comparação é simulada.
"""

import hashlib
import json
import socket
from pathlib import Path
from typing import Any

import pytest

from src.domain_catalog import diff as diff_module
from src.domain_catalog.canonical import canonical_json_bytes, canonical_json_text
from src.domain_catalog.content import CatalogContent
from src.domain_catalog.contracts import CatalogReleaseRef
from src.domain_catalog.diff import _classify_entity_field, diff_catalogs, diff_release_packages
from src.domain_catalog.diff_contracts import CatalogDiff, EntityKey
from src.domain_catalog.errors import CatalogComparisonError, CatalogPackageError
from src.domain_catalog.models import AllowedValue, LocalizedText, Qualifier
from src.domain_catalog.package import ComponentTerms
from src.domain_catalog.reader import open_catalog
from tests.domain_catalog import diff_builders as b

C, C2, CF, U, U2, V, V2, VR, R, R2, P, B, A, D, M, X = (b.uid(n) for n in range(30, 46))
SEM_OP = ("semantic", "operational")


def rich() -> CatalogContent:
    """Uma entidade de cada uma das onze famílias, com relações válidas."""
    return b.content(
        ("units", b.unit(U, "m")),
        ("units", b.unit(U2, "mm")),
        ("value_sets", b.value_set(V, ("A", "B"))),
        ("value_sets", b.value_set(V2, ("X", "Y"))),
        ("value_sets", b.value_set(VR, ("A",), restricts_value_set_id=V)),
        ("concepts", b.concept(C, "SYN_C", value_set_id=V, source_assertion_ids=(b.ASSERTION,))),
        (
            "concepts",
            b.concept(CF, "SYN_LEN", unit_id=U, logical_type="decimal", dimension="length"),
        ),
        ("concepts", b.concept(C2, "SYN_LIVRE", logical_type="string")),
        ("applicability_rules", b.rule(R)),
        ("applicability_rules", b.rule(R2, "IfcSlab")),
        ("evidence_policies", b.policy(P)),
        ("bindings", b.binding(B, C, R, evidence_policy_id=P, field_name="SYN_Campo")),
        ("aliases", b.alias(A, "Apelido", target_binding_id=B)),
        ("profile_memberships", b.membership(M, B)),
        ("reconciliation_decisions", b.decision(D, (B,))),
    )


def _pair(
    tmp_path: Path, old_content: CatalogContent, new_content: CatalogContent, **kw: Any
) -> CatalogDiff:
    old_ref, old_dir = b.write(tmp_path / "o", old_content, "1.0.0", **kw.get("old", {}))
    new_ref, new_dir = b.write(tmp_path / "n", new_content, "1.1.0", **kw.get("new", {}))
    return diff_release_packages(old_ref=old_ref, old_dir=old_dir, new_ref=new_ref, new_dir=new_dir)


def _key(kind: str, entity_id: str) -> EntityKey:
    return EntityKey(kind=kind, id=entity_id)  # type: ignore[arg-type]


def test_entity_matching_uses_kind_and_stable_id(tmp_path: Path) -> None:
    base = rich()
    reordered = CatalogContent.model_validate(
        {kind: tuple(reversed(getattr(base, kind))) for kind in CatalogContent.model_fields}
    )
    ref_a, dir_a = b.write(tmp_path / "a", base)
    ref_b, dir_b = b.write(tmp_path / "b", reordered)
    assert ref_a == ref_b
    same = diff_release_packages(old_ref=ref_a, old_dir=dir_a, new_ref=ref_b, new_dir=dir_b)
    assert same.no_changes

    renamed = base.model_copy(update={"aliases": (b.alias(X, "Apelido", target_binding_id=B),)})
    diff = _pair(tmp_path / "id", base, renamed)
    alias_changes = [
        (c.entity.id, c.change_kind) for c in diff.entity_changes if c.entity.kind == "aliases"
    ]
    assert alias_changes == [(A, "removed"), (X, "added")]

    kind_old = b.replace(base, "units", U2, symbol="mm")
    kind_new = base.model_copy(
        update={
            "units": (b.unit(U, "m"),),
            "value_sets": (*base.value_sets, b.value_set(U2, ("Z",))),
        }
    )
    moved = _pair(tmp_path / "kind", kind_old, kind_new)
    assert [(c.entity.kind, c.entity.id, c.change_kind) for c in moved.entity_changes] == [
        ("units", U2, "removed"),
        ("value_sets", U2, "added"),
    ]


def _one_field(
    diff: CatalogDiff, kind: str, entity_id: str
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    (change,) = [c for c in diff.entity_changes if c.entity == _key(kind, entity_id)]
    (field,) = change.fields
    return field.field, field.categories, field.classes


CASES: list[tuple[str, str, str, dict[str, Any], tuple[str, ...], tuple[str, ...]]] = [
    ("source_artifacts", b.ARTIFACT, "title", {"title": "Outro título"}, ("source",), SEM_OP),
    ("source_assertions", b.ASSERTION, "notes", {"notes": ("nota",)}, ("source",), SEM_OP),
    ("concepts", C, "labels", {"labels": b.pt("Outro rótulo")}, ("label",), ("cosmetic",)),
    (
        "concepts",
        C,
        "definition",
        {"definition": b.pt("Outra definição.")},
        ("definition",),
        SEM_OP,
    ),
    (
        "concepts",
        C,
        "qualifiers",
        {"qualifiers": (Qualifier(name="m", value="v"),)},
        ("definition",),
        SEM_OP,
    ),
    ("concepts", C2, "logical_type", {"logical_type": "code"}, ("type",), SEM_OP),
    ("concepts", CF, "unit_id", {"unit_id": U2}, ("unit",), SEM_OP),
    ("concepts", C, "value_set_id", {"value_set_id": V2}, ("enum",), SEM_OP),
    ("concepts", C, "code", {"code": "SYN_OUTRO"}, ("other",), SEM_OP),
    ("concepts", C, "notes", {"notes": "nota"}, ("other",), SEM_OP),
    ("concepts", C, "source_assertion_ids", {"source_assertion_ids": ()}, ("source",), SEM_OP),
    (
        "concepts",
        C2,
        "lifecycle",
        {"lifecycle": "deprecated"},
        ("deprecation", "lifecycle"),
        SEM_OP,
    ),
    ("units", U, "labels", {"labels": b.pt("metro")}, ("label",), ("cosmetic",)),
    ("units", U, "symbol", {"symbol": "metro"}, ("unit",), SEM_OP),
    ("units", U, "reference", {"reference": "SI"}, ("unit",), SEM_OP),
    (
        "value_sets",
        V,
        "values",
        {"values": (AllowedValue(code="A", labels=b.pt("a")), AllowedValue(code="B"))},
        ("label", "enum"),
        ("cosmetic",),
    ),
    (
        "value_sets",
        V,
        "values",
        {"values": (AllowedValue(code="A"), AllowedValue(code="B"), AllowedValue(code="C"))},
        ("enum",),
        SEM_OP,
    ),
    ("value_sets", V, "ordered", {"ordered": True}, ("enum",), SEM_OP),
    (
        "applicability_rules",
        R,
        "include_subtypes",
        {"include_subtypes": True},
        ("applicability",),
        SEM_OP,
    ),
    (
        "evidence_policies",
        P,
        "admissible_channels",
        {"admissible_channels": ("P", "T")},
        ("evidence_policy",),
        SEM_OP,
    ),
    (
        "evidence_policies",
        P,
        "operation_id",
        {"operation_id": "outra"},
        ("evidence_policy", "operation"),
        SEM_OP,
    ),
    (
        "evidence_policies",
        P,
        "operation_version",
        {"operation_version": "2.0.0"},
        ("evidence_policy", "operation"),
        SEM_OP,
    ),
    ("bindings", B, "ifc_type", {"ifc_type": "IfcIdentifier"}, ("type", "binding"), SEM_OP),
    ("bindings", B, "value_set_id", {"value_set_id": VR}, ("enum", "binding"), SEM_OP),
    (
        "bindings",
        B,
        "declared_schemas",
        {"declared_schemas": ("IFC4", "IFC4X3_ADD2")},
        ("binding", "schema"),
        SEM_OP,
    ),
    (
        "bindings",
        B,
        "applicability_rule_id",
        {"applicability_rule_id": R2},
        ("binding", "applicability"),
        SEM_OP,
    ),
    (
        "bindings",
        B,
        "evidence_policy_id",
        {"evidence_policy_id": None},
        ("binding", "evidence_policy"),
        SEM_OP,
    ),
    ("bindings", B, "scope", {"scope": "type"}, ("binding",), SEM_OP),
    ("bindings", B, "field_name", {"field_name": "SYN_Outro"}, ("binding",), SEM_OP),
    ("aliases", A, "term", {"term": "Outro"}, ("alias",), SEM_OP),
    ("profile_memberships", M, "profile_id", {"profile_id": "perfil-b"}, ("profile",), SEM_OP),
    (
        "reconciliation_decisions",
        D,
        "summary",
        {"summary": "Outra divergência."},
        ("decision",),
        SEM_OP,
    ),
]


@pytest.mark.parametrize(("kind", "entity_id", "field", "changes", "categories", "classes"), CASES)
def test_all_entity_kinds_and_change_categories_are_reported(
    tmp_path: Path,
    kind: str,
    entity_id: str,
    field: str,
    changes: dict[str, Any],
    categories: tuple[str, ...],
    classes: tuple[str, ...],
) -> None:
    diff = _pair(tmp_path, rich(), b.replace(rich(), kind, entity_id, **changes))

    assert _one_field(diff, kind, entity_id) == (field, categories, classes)
    (change,) = [c for c in diff.entity_changes if c.entity == _key(kind, entity_id)]
    before, after = change.fields[0].before, change.fields[0].after
    assert before is not None
    assert after is not None
    entity = next(e for e in getattr(rich(), kind) if e.id == entity_id)
    assert before.json_text == canonical_json_text(entity.model_dump(mode="json")[field])
    assert diff.old_ref.version == "1.0.0"
    assert diff.new_ref.version == "1.1.0"


def test_all_eleven_families_are_covered_by_the_matrix() -> None:
    assert {case[0] for case in CASES} == set(CatalogContent.model_fields)
    assert {cat for case in CASES for cat in case[4]} | {"addition", "removal"} == set(
        diff_module.CATEGORY_ORDER
    )


def test_labels_do_not_hide_definition_or_other_semantic_changes(tmp_path: Path) -> None:
    changed = b.replace(rich(), "concepts", C, labels=b.pt("Novo"), definition=b.pt("Nova def."))
    diff = _pair(tmp_path / "a", rich(), changed)
    (change,) = diff.entity_changes
    assert [(f.field, f.classes) for f in change.fields] == [
        ("definition", SEM_OP),
        ("labels", ("cosmetic",)),
    ]
    with_unit = b.replace(rich(), "concepts", CF, labels=b.pt("Novo"), unit_id=U2)
    unit_diff = _pair(tmp_path / "b", rich(), with_unit)
    assert [(f.field, f.categories) for f in unit_diff.entity_changes[0].fields] == [
        ("labels", ("label",)),
        ("unit_id", ("unit",)),
    ]


def test_integer_boolean_and_text_codes_remain_distinct(tmp_path: Path) -> None:
    def typed(code: Any, value_type: str, logical: str, ifc: str) -> CatalogContent:
        return b.content(
            ("value_sets", b.value_set(V, (code,), value_type=value_type)),
            ("concepts", b.concept(C, value_set_id=V, logical_type=logical)),
            ("applicability_rules", b.rule(R)),
            ("bindings", b.binding(B, C, R, ifc_type=ifc)),
        )

    integer = typed(1, "integer", "integer", "IfcInteger")
    boolean = typed(True, "boolean", "boolean", "IfcBoolean")
    text = typed("1", "code", "code", "IfcLabel")
    to_bool = _pair(tmp_path / "ib", integer, boolean)
    to_text = _pair(tmp_path / "it", integer, text)

    def values(diff: CatalogDiff) -> tuple[str, str]:
        (change,) = [c for c in diff.entity_changes if c.entity.kind == "value_sets"]
        field = next(f for f in change.fields if f.field == "values")
        assert field.before is not None
        assert field.after is not None
        return field.before.json_text, field.after.json_text

    assert values(to_bool) == ('[{"code":1,"labels":[]}]', '[{"code":true,"labels":[]}]')
    assert values(to_text) == ('[{"code":1,"labels":[]}]', '[{"code":"1","labels":[]}]')
    assert ("enum",) in [f.categories for c in to_bool.entity_changes for f in c.fields]


def test_internal_order_and_duplicates_are_preserved(tmp_path: Path) -> None:
    two_langs = (
        LocalizedText(lang="pt-BR", text="Método"),
        LocalizedText(lang="en", text="Method"),
    )
    base = b.replace(rich(), "concepts", C, labels=two_langs)
    swapped = b.replace(base, "concepts", C, labels=tuple(reversed(two_langs)))
    labels = _pair(tmp_path / "l", base, swapped)
    assert _one_field(labels, "concepts", C) == ("labels", ("label",), ("cosmetic",))

    reordered = b.replace(
        rich(), "value_sets", V, values=(AllowedValue(code="B"), AllowedValue(code="A"))
    )
    order = _pair(tmp_path / "v", rich(), reordered)
    assert _one_field(order, "value_sets", V) == ("values", ("enum",), SEM_OP)

    twice = b.replace(rich(), "concepts", C, source_assertion_ids=(b.ASSERTION, b.ASSERTION))
    dup = _pair(tmp_path / "d", rich(), twice)
    field = dup.entity_changes[0].fields[0]
    assert field.after is not None
    assert field.after.value == [b.ASSERTION, b.ASSERTION]
    terms = (ComponentTerms(component="a", terms="x"), ComponentTerms(component="b", terms="y"))
    term_diff = _pair(
        tmp_path / "t",
        rich(),
        rich(),
        old={"terms": terms},
        new={"terms": tuple(reversed(terms))},
    )
    assert "terms" in [m.field for m in term_diff.manifest_changes]


def _omit_default(
    release_dir: Path, ref: CatalogReleaseRef, kind_file: str, key: str
) -> CatalogReleaseRef:
    """Reescreve um arquivo omitindo um campo com valor default e refaz manifesto e hashes."""
    rows = json.loads((release_dir / kind_file).read_bytes())
    for row in rows:
        row.pop(key)
    blob = canonical_json_bytes(rows)
    (release_dir / kind_file).write_bytes(blob)
    manifest = json.loads((release_dir / "manifest.json").read_bytes())
    for item in manifest["files"]:
        if item["path"] == kind_file:
            item["bytes"], item["sha256"] = len(blob), hashlib.sha256(blob).hexdigest()
    manifest_bytes = canonical_json_bytes(manifest)
    (release_dir / "manifest.json").write_bytes(manifest_bytes)
    return ref.model_copy(update={"manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest()})


def test_explicit_null_and_omitted_default_are_equal_only_as_models(tmp_path: Path) -> None:
    old_ref, old_dir = b.write(tmp_path / "o", rich(), "1.0.0")
    old_ref = _omit_default(old_dir, old_ref, "concepts.json", "notes")
    assert b"notes" not in (old_dir / "concepts.json").read_bytes()
    open_catalog(old_ref, old_dir)
    new_ref, new_dir = b.write(tmp_path / "n", rich(), "1.0.1")
    assert b'"notes":null' in (new_dir / "concepts.json").read_bytes()

    diff = diff_release_packages(old_ref=old_ref, old_dir=old_dir, new_ref=new_ref, new_dir=new_dir)

    assert diff.entity_changes == ()
    assert [m.field for m in diff.manifest_changes] == ["files", "version"]
    assert not diff.no_changes


def test_identical_valid_release_has_no_changes(tmp_path: Path) -> None:
    ref, first = b.write(tmp_path / "a", rich())
    _, second = b.write(tmp_path / "b", rich())
    diff = diff_release_packages(old_ref=ref, old_dir=first, new_ref=ref, new_dir=second)

    assert (diff.entity_changes, diff.manifest_changes, diff.impacts) == ((), (), ())
    assert diff.same_release
    assert diff.no_changes


def test_only_version_and_date_change_is_not_no_changes(tmp_path: Path) -> None:
    diff = _pair(tmp_path, rich(), rich(), new={"created_at": "2026-10-23T00:00:00Z"})

    assert [m.field for m in diff.manifest_changes] == ["created_at", "version"]
    assert [(m.category, m.classes) for m in diff.manifest_changes] == [
        ("release_identity", ("operational",)),
        ("release_identity", ("operational",)),
    ]
    assert (diff.entity_changes, diff.impacts) == ((), ())
    assert diff.has_changes


def test_terms_origin_and_catalog_metadata_are_reported(tmp_path: Path) -> None:
    diff = _pair(
        tmp_path,
        rich(),
        rich(),
        new={
            "terms": (ComponentTerms(component="conteúdo", terms="outros termos sintéticos"),),
            "origin": "curated",
            "catalog": b.identity(
                maintainer="Outro mantenedor sintético", language="en", name="Outro nome"
            ),
        },
    )
    found = {m.field: (m.category, m.classes) for m in diff.manifest_changes}

    assert found == {
        "catalog.language": ("catalog_metadata", ("operational",)),
        "catalog.maintainer": ("catalog_metadata", ("operational",)),
        "catalog.name": ("catalog_metadata", ("cosmetic",)),
        "content_origin": ("provenance", ("operational",)),
        "terms": ("distribution_terms", ("operational",)),
        "version": ("release_identity", ("operational",)),
    }
    assert diff.impacts == ()


def test_previous_release_and_derived_inventory_remain_visible(tmp_path: Path) -> None:
    previous = CatalogReleaseRef(
        catalog_id=b.f.SYN_CATALOG_ID, version="0.1.0", manifest_sha256="e" * 64
    )
    changed = b.replace(rich(), "bindings", B, declared_schemas=("IFC4", "IFC4X3_ADD2"))
    diff = _pair(tmp_path, rich(), changed, new={"previous": previous})
    fields = {m.field: m.category for m in diff.manifest_changes}

    assert fields == {
        "declared_schemas": "derived_summary",
        "files": "package_inventory",
        "previous_release": "release_identity",
        "version": "release_identity",
    }
    assert {t.origin for t in diff.impacts} == {_key("bindings", B)}


def test_unknown_field_classification_is_conservative(tmp_path: Path) -> None:
    assert _classify_entity_field("concepts", "campo_futuro", 1, 2) == (("other",), SEM_OP)
    ref, folder = b.write(tmp_path, rich())
    rows = json.loads((folder / "units.json").read_bytes())
    rows[0]["campo_futuro"] = 1
    blob = canonical_json_bytes(rows)
    (folder / "units.json").write_bytes(blob)
    manifest = json.loads((folder / "manifest.json").read_bytes())
    for item in manifest["files"]:
        if item["path"] == "units.json":
            item["bytes"], item["sha256"] = len(blob), hashlib.sha256(blob).hexdigest()
    manifest_bytes = canonical_json_bytes(manifest)
    (folder / "manifest.json").write_bytes(manifest_bytes)
    forged = ref.model_copy(update={"manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest()})
    with pytest.raises(CatalogPackageError) as refused:
        open_catalog(forged, folder)
    assert refused.value.reason == "content"


def test_same_version_different_hash_refuses_without_diff(tmp_path: Path) -> None:
    ref_a, dir_a = b.write(tmp_path / "a", rich(), "1.0.0")
    ref_b, dir_b = b.write(tmp_path / "b", b.replace(rich(), "aliases", A, term="Outro"), "1.0.0")
    with pytest.raises(CatalogComparisonError) as refused:
        diff_release_packages(old_ref=ref_a, old_dir=dir_a, new_ref=ref_b, new_dir=dir_b)
    assert (refused.value.reason, refused.value.old_ref, refused.value.new_ref) == (
        "version_hash_collision",
        ref_a,
        ref_b,
    )


def test_different_catalog_ids_refuse_without_entity_matching(tmp_path: Path) -> None:
    other = b.identity(catalog_id="urn:uuid:00000000-0000-4000-8000-0000000000e2")
    ref_a, dir_a = b.write(tmp_path / "a", rich(), "1.0.0")
    ref_b, dir_b = b.write(
        tmp_path / "b", b.replace(rich(), "aliases", A, term="X"), "1.0.0", catalog=other
    )
    with pytest.raises(CatalogComparisonError) as refused:
        diff_release_packages(old_ref=ref_a, old_dir=dir_a, new_ref=ref_b, new_dir=dir_b)
    assert refused.value.reason == "catalog_id_mismatch"


@pytest.mark.parametrize("side", ["old", "new"])
@pytest.mark.parametrize("damage", ["missing", "tampered", "format"])
def test_package_errors_are_not_empty_diff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, side: str, damage: str
) -> None:
    old_ref, old_dir = b.write(tmp_path / "o", rich(), "1.0.0")
    new_ref, new_dir = b.write(tmp_path / "n", rich(), "1.1.0")
    target = old_dir if side == "old" else new_dir
    if damage == "missing":
        for item in target.iterdir():
            item.unlink()
        target.rmdir()
    elif damage == "tampered":
        (target / "bindings.json").write_bytes((target / "bindings.json").read_bytes() + b" ")
    else:
        manifest = canonical_json_bytes({"format": "outro", "format_version": 1})
        (target / "manifest.json").write_bytes(manifest)
        forged = hashlib.sha256(manifest).hexdigest()
        if side == "old":
            old_ref = old_ref.model_copy(update={"manifest_sha256": forged})
        else:
            new_ref = new_ref.model_copy(update={"manifest_sha256": forged})

    def never(*args: object, **kwargs: object) -> None:
        raise AssertionError("comparação chamada depois de falha de abertura")

    monkeypatch.setattr(diff_module, "diff_catalogs", never)
    with pytest.raises(CatalogPackageError) as refused:
        diff_release_packages(old_ref=old_ref, old_dir=old_dir, new_ref=new_ref, new_dir=new_dir)
    expected = {"missing": "not_found", "tampered": "integrity", "format": "format"}[damage]
    assert refused.value.reason == expected


def test_identical_refs_still_open_both_packages(tmp_path: Path) -> None:
    ref, first = b.write(tmp_path / "a", rich())
    _, second = b.write(tmp_path / "b", rich())
    (second / "aliases.json").write_bytes((second / "aliases.json").read_bytes() + b" ")
    with pytest.raises(CatalogPackageError) as tampered:
        diff_release_packages(old_ref=ref, old_dir=first, new_ref=ref, new_dir=second)
    assert tampered.value.reason == "integrity"
    with pytest.raises(CatalogPackageError) as missing:
        diff_release_packages(old_ref=ref, old_dir=first, new_ref=ref, new_dir=tmp_path / "nada")
    assert missing.value.reason == "not_found"


def test_comparison_is_directional_not_version_chronology(tmp_path: Path) -> None:
    unrelated = CatalogReleaseRef(
        catalog_id=b.f.SYN_CATALOG_ID, version="0.0.1", manifest_sha256="f" * 64
    )
    new_content = b.replace(rich(), "aliases", A, term="Outro")
    high_ref, high_dir = b.write(tmp_path / "h", rich(), "2.0.0", previous=unrelated)
    low_ref, low_dir = b.write(tmp_path / "l", new_content, "1.0.0")

    forward = diff_release_packages(
        old_ref=high_ref, old_dir=high_dir, new_ref=low_ref, new_dir=low_dir
    )
    backward = diff_release_packages(
        old_ref=low_ref, old_dir=low_dir, new_ref=high_ref, new_dir=high_dir
    )

    (f_change,) = forward.entity_changes
    (b_change,) = backward.entity_changes
    assert (f_change.fields[0].before, f_change.fields[0].after) == (
        b_change.fields[0].after,
        b_change.fields[0].before,
    )
    assert forward.old_ref == backward.new_ref
    f_version = next(m for m in forward.manifest_changes if m.field == "version")
    assert (f_version.before.value, f_version.after.value) == ("2.0.0", "1.0.0")


def test_diff_is_deterministic_local_and_non_mutating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old_ref, old_dir = b.write(tmp_path / "o", rich(), "1.0.0")
    new_ref, new_dir = b.write(
        tmp_path / "n", b.replace(rich(), "concepts", C, definition=b.pt("Outra.")), "1.1.0"
    )

    def snapshot() -> dict[str, str]:
        return {
            str(p.relative_to(tmp_path)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(tmp_path.rglob("*"))
            if p.is_file()
        }

    before = snapshot()

    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("rede proibida no diff")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    import httpx

    monkeypatch.setattr(httpx.Client, "send", blocked)
    first = diff_release_packages(
        old_ref=old_ref, old_dir=old_dir, new_ref=new_ref, new_dir=new_dir
    )
    second = diff_release_packages(
        old_ref=old_ref, old_dir=old_dir, new_ref=new_ref, new_dir=new_dir
    )
    old_reader, new_reader = open_catalog(old_ref, old_dir), open_catalog(new_ref, new_dir)
    content_before = (old_reader.content, new_reader.content)

    def no_disk(*args: object, **kwargs: object) -> None:
        raise AssertionError("diff puro tocou o disco")

    monkeypatch.setattr(Path, "open", no_disk)
    monkeypatch.setattr(Path, "read_bytes", no_disk)
    pure = diff_catalogs(old_reader, new_reader)
    monkeypatch.undo()

    assert canonical_json_bytes(first.model_dump(mode="json")) == canonical_json_bytes(
        second.model_dump(mode="json")
    )
    assert pure == first
    assert (old_reader.content, new_reader.content) == content_before
    assert (old_reader.ref, new_reader.ref) == (old_ref, new_ref)
    assert snapshot() == before
