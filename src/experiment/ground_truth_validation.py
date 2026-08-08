"""Validação estrutural local para documentos canônicos de ground truth."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

NaturalKey = tuple[str, str, str]


class GroundTruthValidationError(ValueError):
    """Indica que um documento de ground truth viola invariantes estruturais."""


@dataclass(frozen=True)
class GroundTruthValidationReport:
    """Resumo das chaves e contagens verificadas em um documento válido."""

    path: Path
    total_items: int
    total_skipped: int
    item_keys: set[NaturalKey]
    skipped_keys: set[NaturalKey]


def natural_key_from_mapping(entry: Mapping[str, Any]) -> NaturalKey:
    """Extrai a chave natural ``(element_guid, issue_type, check_property)``."""
    return (
        str(entry["element_guid"]),
        str(entry["issue_type"]),
        str(entry["check_property"]),
    )


def load_ground_truth_document(path: str | Path) -> dict[str, Any]:
    """Carrega um YAML de ground truth e exige um mapeamento na raiz."""
    document_path = Path(path)
    try:
        raw = yaml.safe_load(document_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise GroundTruthValidationError(f"invalid_yaml: {error}") from error

    if not isinstance(raw, dict):
        raise GroundTruthValidationError("root_must_be_mapping")
    return raw


def validate_ground_truth_document(path: str | Path) -> GroundTruthValidationReport:
    """Valida invariantes locais e retorna as chaves canônicas do documento.

    Todos os problemas que podem ser observados são agregados; a mensagem é ordenada
    para manter resultados estáveis entre execuções.
    """
    document_path = Path(path)
    document = load_ground_truth_document(document_path)
    problems: list[str] = []

    metadata = document.get("metadata")
    if not isinstance(metadata, Mapping):
        problems.append("metadata_must_be_mapping")
        metadata = {}

    items = _read_entries(document, "items", problems)
    skipped = _read_entries(document, "skipped", problems)

    item_keys, item_issue_ids = _validate_items(items, problems)
    skipped_keys, skipped_issue_ids = _validate_skipped(skipped, problems)

    _validate_unique_issue_ids(item_issue_ids, skipped_issue_ids, problems)
    for key in sorted(item_keys & skipped_keys):
        problems.append(f"item_and_skip_overlap: {key!r}")
    _validate_declared_counts(metadata, len(items), len(skipped), problems)

    if problems:
        ordered = "\n".join(f"- {problem}" for problem in sorted(problems))
        raise GroundTruthValidationError(f"ground_truth_validation_failed:\n{ordered}")

    return GroundTruthValidationReport(
        path=document_path,
        total_items=len(items),
        total_skipped=len(skipped),
        item_keys=item_keys,
        skipped_keys=skipped_keys,
    )


def _read_entries(document: Mapping[str, Any], name: str, problems: list[str]) -> list[Any]:
    entries = document.get(name)
    if not isinstance(entries, list):
        problems.append(f"{name}_must_be_list")
        return []
    return entries


def _validate_items(entries: list[Any], problems: list[str]) -> tuple[set[NaturalKey], list[str]]:
    keys: set[NaturalKey] = set()
    issue_ids: list[str] = []
    for index, entry in enumerate(entries):
        location = f"items[{index}]"
        key, issue_id = _validate_common_entry(entry, location, problems)
        if key is not None:
            if key in keys:
                problems.append(f"duplicate_natural_key: {location}: {key!r}")
            keys.add(key)
        if issue_id is not None:
            issue_ids.append(issue_id)
        if not isinstance(entry, Mapping):
            continue
        if entry.get("expected_value") is None:
            problems.append(f"null_expected_value: {location}")
        if entry.get("verified") is not True:
            problems.append(f"unverified_item: {location}")
    return keys, issue_ids


def _validate_skipped(entries: list[Any], problems: list[str]) -> tuple[set[NaturalKey], list[str]]:
    keys: set[NaturalKey] = set()
    issue_ids: list[str] = []
    for index, entry in enumerate(entries):
        location = f"skipped[{index}]"
        key, issue_id = _validate_common_entry(entry, location, problems)
        if key is not None:
            if key in keys:
                problems.append(f"duplicate_natural_key: {location}: {key!r}")
            keys.add(key)
        if issue_id is not None:
            issue_ids.append(issue_id)
    return keys, issue_ids


def _validate_common_entry(
    entry: Any, location: str, problems: list[str]
) -> tuple[NaturalKey | None, str | None]:
    if not isinstance(entry, Mapping):
        problems.append(f"entry_must_be_mapping: {location}")
        return None, None

    has_complete_key = (
        isinstance(entry.get("element_guid"), str)
        and bool(entry["element_guid"])
        and isinstance(entry.get("issue_type"), str)
        and bool(entry["issue_type"])
        and isinstance(entry.get("check_property"), str)
    )
    if not has_complete_key:
        problems.append(f"incomplete_natural_key: {location}")
        key = None
    else:
        key = natural_key_from_mapping(entry)
        if entry["issue_type"] == "pset_missing" and not entry["check_property"]:
            problems.append(f"pset_missing_requires_check_property: {location}")

    issue_id = entry.get("issue_id")
    if not isinstance(issue_id, str) or not issue_id:
        problems.append(f"invalid_issue_id: {location}")
        return key, None
    return key, issue_id


def _validate_unique_issue_ids(
    item_issue_ids: list[str], skipped_issue_ids: list[str], problems: list[str]
) -> None:
    seen: set[str] = set()
    for issue_id in [*item_issue_ids, *skipped_issue_ids]:
        if issue_id in seen:
            problems.append(f"duplicate_issue_id: {issue_id!r}")
        seen.add(issue_id)


def _validate_declared_counts(
    metadata: Mapping[str, Any], total_items: int, total_skipped: int, problems: list[str]
) -> None:
    for name, actual in (("total_items", total_items), ("total_skipped", total_skipped)):
        declared = metadata.get(name)
        if isinstance(declared, bool) or not isinstance(declared, int) or declared != actual:
            problems.append(
                f"declared_count_mismatch: metadata.{name}={declared!r}, actual={actual}"
            )
