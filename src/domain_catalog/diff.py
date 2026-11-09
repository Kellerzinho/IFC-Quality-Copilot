"""Comparação de dois releases do mesmo catálogo (E3.2a, parte do M1-11).

``diff_release_packages`` abre os **dois** pacotes pelas refs exatas (mesmo se forem
iguais) com ``open_catalog`` e só então compara; erro de pacote sai como
``CatalogPackageError`` com o motivo original. ``diff_catalogs`` é o comparador puro
sobre readers já abertos: não toca disco nem rede e não autentica reader construído
à mão. Precedência das recusas: catálogo distinto, depois mesma versão com hash
diferente; nas duas, nenhum ``CatalogDiff`` é devolvido. ``old``/``new`` indicam a
direção pedida, não cronologia: SemVer e ``previous_release`` não são validados.

Entidades são casadas por ``(tipo, ID)``; a comparação é dos ``model_dump`` validados
(com defaults), campo superior a campo superior, por JSON canônico — tipos, caixa,
acentos, nulo e ordem/multiplicidade de listas permanecem observáveis. O manifesto
vira lista própria. Classes são conservadoras e não exclusivas; não afirmam
equivalência nem adoção segura.
"""

from pathlib import Path
from typing import Any

from src.domain_catalog.canonical import canonical_json_text
from src.domain_catalog.content import ENTITY_KINDS, CatalogContent
from src.domain_catalog.contracts import CatalogReleaseRef
from src.domain_catalog.diff_contracts import (
    CATEGORY_ORDER,
    CatalogDiff,
    ChangeCategory,
    ChangeClass,
    DiffLimits,
    DiffValue,
    EntityChange,
    EntityKey,
    FieldChange,
    ManifestCategory,
    ManifestChange,
)
from src.domain_catalog.errors import CatalogComparisonError
from src.domain_catalog.impact import build_catalog_impacts
from src.domain_catalog.package import CatalogManifest, PackageLimits
from src.domain_catalog.reader import CatalogReader, open_catalog

__all__ = ["CATEGORY_ORDER", "diff_catalogs", "diff_release_packages"]

_SEM_OP: tuple[ChangeClass, ...] = ("semantic", "operational")
_COSMETIC: tuple[ChangeClass, ...] = ("cosmetic",)
_SOURCE_KINDS = frozenset({"source_artifacts", "source_assertions"})
_UNIT_FIELDS = frozenset(
    {
        ("concepts", "dimension"),
        ("concepts", "unit_id"),
        ("units", "symbol"),
        ("units", "dimension"),
        ("units", "reference"),
    }
)
_VALUE_SET_DOMAIN = frozenset({"value_type", "values", "ordered", "restricts_value_set_id"})


def _ordered(categories: set[str]) -> tuple[ChangeCategory, ...]:
    return tuple(c for c in CATEGORY_ORDER if c in categories)  # type: ignore[misc]


def _labels_only(before: Any, after: Any) -> bool:
    """Mesma sequência de códigos, com tipos exatos posição a posição; só rótulos mudam."""
    if not (isinstance(before, list) and isinstance(after, list)) or len(before) != len(after):
        return False
    for old, new in zip(before, after, strict=True):
        if not (isinstance(old, dict) and isinstance(new, dict)):
            return False
        if set(old) != set(new) or set(old) - {"code", "labels"}:
            return False
        if type(old.get("code")) is not type(new.get("code")) or old.get("code") != new.get("code"):
            return False
    return True


def _classify_entity_field(
    kind: str, field: str, before: object, after: object
) -> tuple[tuple[ChangeCategory, ...], tuple[ChangeClass, ...]]:
    """Categorias e classes de um campo alterado (adendo §3.2), com precedência fixa.

    lifecycle → ``source_assertion_ids`` → regras de campo → família → ``other``.
    """
    if field == "lifecycle":
        found = {"lifecycle"}
        if after == "deprecated" and before != "deprecated":
            found.add("deprecation")
        return _ordered(found), _SEM_OP
    if field == "source_assertion_ids":
        return ("source",), _SEM_OP
    key = (kind, field)
    if key in (("concepts", "labels"), ("units", "labels")):
        return ("label",), _COSMETIC
    if key == ("value_sets", "values") and _labels_only(before, after):
        return ("label", "enum"), _COSMETIC
    if key in (("concepts", "definition"), ("concepts", "qualifiers")):
        return ("definition",), _SEM_OP
    if key == ("concepts", "logical_type"):
        return ("type",), _SEM_OP
    if key == ("bindings", "ifc_type"):
        return ("type", "binding"), _SEM_OP
    if key in _UNIT_FIELDS:
        return ("unit",), _SEM_OP
    if key == ("concepts", "value_set_id"):
        return ("enum",), _SEM_OP
    if key == ("bindings", "value_set_id"):
        return ("enum", "binding"), _SEM_OP
    if kind == "value_sets" and field in _VALUE_SET_DOMAIN:
        return ("enum",), _SEM_OP
    if key == ("bindings", "declared_schemas"):
        return ("binding", "schema"), _SEM_OP
    if key == ("bindings", "applicability_rule_id"):
        return ("binding", "applicability"), _SEM_OP
    if key == ("bindings", "evidence_policy_id"):
        return ("binding", "evidence_policy"), _SEM_OP
    if kind == "evidence_policies" and field in ("operation_id", "operation_version"):
        return ("evidence_policy", "operation"), _SEM_OP
    family: dict[str, ChangeCategory] = {
        "applicability_rules": "applicability",
        "evidence_policies": "evidence_policy",
        "bindings": "binding",
        "aliases": "alias",
        "reconciliation_decisions": "decision",
        "profile_memberships": "profile",
    }
    if kind in family:
        return (family[kind],), _SEM_OP
    if kind in _SOURCE_KINDS:
        return ("source",), _SEM_OP
    return ("other",), _SEM_OP


def _value(value: Any) -> DiffValue:
    return DiffValue(json_text=canonical_json_text(value))


def _entity_changes(old: CatalogContent, new: CatalogContent) -> tuple[EntityChange, ...]:
    """Mudanças por ``(tipo, ID)``, na ordem do formato e por ID literal."""
    changes: list[EntityChange] = []
    for kind in ENTITY_KINDS:
        before = {entity.id: entity.model_dump(mode="json") for entity in getattr(old, kind)}
        after = {entity.id: entity.model_dump(mode="json") for entity in getattr(new, kind)}
        for entity_id in sorted(set(before) | set(after)):
            key = EntityKey(kind=kind, id=entity_id)
            if entity_id not in after:
                field = FieldChange(
                    field="$",
                    before=_value(before[entity_id]),
                    after=None,
                    categories=("removal",),
                    classes=_SEM_OP,
                )
                changes.append(EntityChange(entity=key, change_kind="removed", fields=(field,)))
                continue
            if entity_id not in before:
                field = FieldChange(
                    field="$",
                    before=None,
                    after=_value(after[entity_id]),
                    categories=("addition",),
                    classes=_SEM_OP,
                )
                changes.append(EntityChange(entity=key, change_kind="added", fields=(field,)))
                continue
            fields = []
            names = sorted((set(before[entity_id]) | set(after[entity_id])) - {"id"})
            for name in names:
                old_value = before[entity_id].get(name)
                new_value = after[entity_id].get(name)
                if canonical_json_text(old_value) == canonical_json_text(new_value):
                    continue
                categories, classes = _classify_entity_field(kind, name, old_value, new_value)
                fields.append(
                    FieldChange(
                        field=name,
                        before=_value(old_value),
                        after=_value(new_value),
                        categories=categories,
                        classes=classes,
                    )
                )
            if fields:
                changes.append(
                    EntityChange(entity=key, change_kind="modified", fields=tuple(fields))
                )
    return tuple(changes)


_MANIFEST_RULES: dict[str, tuple[ManifestCategory, tuple[ChangeClass, ...]]] = {
    "version": ("release_identity", ("operational",)),
    "created_at": ("release_identity", ("operational",)),
    "previous_release": ("release_identity", ("operational",)),
    "catalog.name": ("catalog_metadata", _COSMETIC),
    "catalog.description": ("catalog_metadata", _COSMETIC),
    "catalog.namespace": ("catalog_metadata", ("operational",)),
    "catalog.namespace_status": ("catalog_metadata", ("operational",)),
    "catalog.maintainer": ("catalog_metadata", ("operational",)),
    "catalog.language": ("catalog_metadata", ("operational",)),
    "content_origin": ("provenance", ("operational",)),
    "terms": ("distribution_terms", ("operational",)),
    "profiles": ("derived_summary", ("operational",)),
    "declared_schemas": ("derived_summary", ("operational",)),
    "files": ("package_inventory", ("operational",)),
    "format": ("format", ("operational",)),
    "format_version": ("format", ("operational",)),
}


def _manifest_fields(manifest: CatalogManifest) -> dict[str, Any]:
    dumped = manifest.model_dump(mode="json")
    fields: dict[str, Any] = {}
    for name, value in dumped.items():
        if name == "catalog":
            for sub, sub_value in value.items():
                if sub != "catalog_id":
                    fields[f"catalog.{sub}"] = sub_value
        else:
            fields[name] = value
    return fields


def _manifest_changes(old: CatalogManifest, new: CatalogManifest) -> tuple[ManifestChange, ...]:
    """Todos os campos superiores do manifesto (``catalog`` desdobrado), por nome literal."""
    before, after = _manifest_fields(old), _manifest_fields(new)
    changes = []
    for name in sorted(set(before) | set(after)):
        old_value, new_value = before.get(name), after.get(name)
        if canonical_json_text(old_value) == canonical_json_text(new_value):
            continue
        category, classes = _MANIFEST_RULES.get(name, ("other", _SEM_OP))
        changes.append(
            ManifestChange(
                field=name,
                before=_value(old_value),
                after=_value(new_value),
                category=category,
                classes=classes,
            )
        )
    return tuple(changes)


def diff_catalogs(
    old: CatalogReader, new: CatalogReader, *, limits: DiffLimits | None = None
) -> CatalogDiff:
    """Diff puro entre readers abertos por ``open_catalog``; recusas não devolvem diff."""
    limits = limits or DiffLimits()
    old_ref, new_ref = old.ref, new.ref
    if old_ref.catalog_id != new_ref.catalog_id:
        raise CatalogComparisonError(
            "catalog_id_mismatch",
            "releases de catálogos distintos não são comparáveis; nenhum casamento por nome",
            old_ref=old_ref,
            new_ref=new_ref,
        )
    if old_ref.version == new_ref.version and old_ref.manifest_sha256 != new_ref.manifest_sha256:
        raise CatalogComparisonError(
            "version_hash_collision",
            f"versão {old_ref.version} com dois manifestos distintos",
            old_ref=old_ref,
            new_ref=new_ref,
        )
    changes = _entity_changes(old.content, new.content)
    return CatalogDiff(
        old_ref=old_ref,
        new_ref=new_ref,
        entity_changes=changes,
        manifest_changes=_manifest_changes(old.describe(), new.describe()),
        impacts=build_catalog_impacts(
            old.content, new.content, changes, limits=limits, old_ref=old_ref, new_ref=new_ref
        ),
    )


def diff_release_packages(
    *,
    old_ref: CatalogReleaseRef,
    old_dir: Path,
    new_ref: CatalogReleaseRef,
    new_dir: Path,
    package_limits: PackageLimits | None = None,
    diff_limits: DiffLimits | None = None,
) -> CatalogDiff:
    """Abre ``old`` e depois ``new`` (sempre os dois) e compara; erro de pacote propaga."""
    old_reader = open_catalog(old_ref, old_dir, limits=package_limits)
    new_reader = open_catalog(new_ref, new_dir, limits=package_limits)
    return diff_catalogs(old_reader, new_reader, limits=diff_limits)
