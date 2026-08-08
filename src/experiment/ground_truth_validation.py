"""Validação estrutural local para documentos canônicos de ground truth."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.models import Issue

NaturalKey = tuple[str, str, str]

WALL_SYSTEM_VALUES = frozenset(
    {
        "Alvenaria de veda\u00e7\u00e3o em bloco cer\u00e2mico",
        "Alvenaria estrutural em bloco cer\u00e2mico",
        "Concreto armado moldado in loco",
        "Concreto pr\u00e9-moldado",
        "Drywall / Steel frame",
        "Alvenaria em bloco de concreto",
        "Estrutura met\u00e1lica",
        "Painel de EPS",
    }
)
SLAB_SYSTEM_VALUES = frozenset(
    {
        "Laje maci\u00e7a de concreto armado",
        "Laje nervurada (vigotas + EPS/cer\u00e2mica)",
        "Laje pr\u00e9-moldada treli\u00e7ada",
        "Laje alveolar pr\u00e9-moldada",
        "Laje de madeira (estrutura em madeira)",
        "Laje steel frame",
        "Piso cer\u00e2mico / porcelanato",
        "Piso de madeira (parquet / taco / deck)",
        "Piso de pedra (m\u00e1rmore / granito / ard\u00f3sia)",
        "Piso de concreto polido",
        "Grama natural ou artificial",
        "Piso de cimento queimado",
        "Deck de madeira externo",
        "Carpete",
        "Piso vin\u00edlico / laminado",
    }
)
CATEGORY_VALUES = frozenset(
    {
        "BEDROOM",
        "LIVING_ROOM",
        "KITCHEN",
        "BATHROOM",
        "WC",
        "CIRCULATION",
        "SERVICE_AREA",
        "OFFICE",
        "MEETING_ROOM",
        "LOBBY",
        "STORAGE",
        "BALCONY",
        "GARAGE",
        "TECHNICAL_AREA",
    }
)
FIRE_RATING_PATTERN = re.compile(r"^(R|E|I|RE|EI|REI|P-CF) [0-9]{2,3}$")


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


def sha256_file(path: str | Path) -> str:
    """Retorna o SHA-256 hexadecimal do arquivo imut\u00e1vel de entrada."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_ground_truth_against_issues(
    path: str | Path,
    issues: Sequence[Issue],
    *,
    ifc_path: str | Path,
    ids_path: str | Path,
) -> GroundTruthValidationReport:
    """Confere que GT can\u00f4nico cobre o diagn\u00f3stico e seus artefatos congelados."""
    report = validate_ground_truth_document(path)
    document = load_ground_truth_document(path)
    metadata = document["metadata"]
    items = document["items"]
    skipped = document["skipped"]
    problems: list[str] = []

    _validate_frozen_hashes(metadata, ifc_path, ids_path, problems)
    _validate_system_properties(items, skipped, problems)
    _validate_diagnostic_coverage(items, skipped, issues, report, metadata, problems)
    _validate_item_semantics(items, issues, problems)
    _validate_skip_reasons(skipped, problems)

    if problems:
        ordered = "\n".join(f"- {problem}" for problem in sorted(problems))
        raise GroundTruthValidationError(f"ground_truth_validation_failed:\n{ordered}")
    return report


def _validate_frozen_hashes(
    metadata: Mapping[str, Any], ifc_path: str | Path, ids_path: str | Path, problems: list[str]
) -> None:
    for name, source_path in (("input_ifc_sha256", ifc_path), ("ids_sha256", ids_path)):
        declared = metadata.get(name)
        actual = sha256_file(source_path)
        if not isinstance(declared, str) or declared.lower() != actual.lower():
            problems.append(f"{name}_mismatch: metadata.{name}={declared!r}, actual={actual}")


def _validate_diagnostic_coverage(
    items: list[Any],
    skipped: list[Any],
    issues: Sequence[Issue],
    report: GroundTruthValidationReport,
    metadata: Mapping[str, Any],
    problems: list[str],
) -> None:
    diagnostic_by_key: dict[NaturalKey, Issue] = {}
    for issue in issues:
        key = _natural_key_from_issue(issue)
        if key in diagnostic_by_key:
            problems.append(f"duplicate_diagnostic_natural_key: {key!r}")
        diagnostic_by_key[key] = issue

    for name, entries in (("items", items), ("skipped", skipped)):
        for index, entry in enumerate(entries):
            if not isinstance(entry, Mapping):
                continue
            key = natural_key_from_mapping(entry)
            diagnostic_issue = diagnostic_by_key.get(key)
            location = f"{name}[{index}]"
            if diagnostic_issue is None:
                problems.append(f"entry_without_diagnostic_issue: {location}: {key!r}")
            elif entry["issue_id"] != diagnostic_issue.id:
                problems.append(
                    f"stale_issue_id: {location}: {entry['issue_id']!r} != {diagnostic_issue.id!r}"
                )

    diagnostic_keys = set(diagnostic_by_key)
    covered_keys = report.item_keys | report.skipped_keys
    for key in sorted(diagnostic_keys - covered_keys):
        problems.append(f"missing_diagnostic_issue: {key!r}")

    declared_total = metadata.get("total_diagnostic_issues")
    if (
        isinstance(declared_total, bool)
        or not isinstance(declared_total, int)
        or declared_total != len(issues)
    ):
        problems.append(
            "declared_diagnostic_count_mismatch: "
            f"metadata.total_diagnostic_issues={declared_total!r}, actual={len(issues)}"
        )
    if report.total_items + report.total_skipped != len(issues):
        problems.append(
            "diagnostic_coverage_count_mismatch: "
            f"items_plus_skipped={report.total_items + report.total_skipped}, actual={len(issues)}"
        )


def _validate_system_properties(items: list[Any], skipped: list[Any], problems: list[str]) -> None:
    for name, entries in (("items", items), ("skipped", skipped)):
        for index, entry in enumerate(entries):
            if (
                isinstance(entry, Mapping)
                and entry.get("issue_type") == "system_unclassified"
                and entry.get("check_property") != ""
            ):
                problems.append(
                    f"system_unclassified_requires_empty_check_property: {name}[{index}]"
                )


def _natural_key_from_issue(issue: Issue) -> NaturalKey:
    return (
        issue.element_guid,
        issue.issue_type,
        str(issue.context.get("check_property") or ""),
    )


def _validate_item_semantics(
    entries: list[Any], issues: Sequence[Issue], problems: list[str]
) -> None:
    issue_by_key = {_natural_key_from_issue(issue): issue for issue in issues}
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            continue
        location = f"items[{index}]"
        notes = entry.get("notes")
        if not isinstance(notes, str) or not notes.strip():
            problems.append(f"blank_notes: {location}")
            notes = ""

        alternatives = entry.get("accepted_alternatives", [])
        if not isinstance(alternatives, list):
            problems.append(f"accepted_alternatives_must_be_list: {location}")
            alternatives = []
        key = natural_key_from_mapping(entry)
        diagnostic_issue = issue_by_key.get(key)
        _validate_item_value(
            entry.get("expected_value"), entry, diagnostic_issue, notes, location, problems
        )
        for alternative_index, value in enumerate(alternatives):
            _validate_item_value(
                value,
                entry,
                diagnostic_issue,
                notes,
                f"{location}.accepted_alternatives[{alternative_index}]",
                problems,
            )


def _validate_item_value(
    value: Any,
    entry: Mapping[str, Any],
    diagnostic_issue: Issue | None,
    notes: str,
    location: str,
    problems: list[str],
) -> None:
    issue_type = entry.get("issue_type")
    property_name = entry.get("check_property")
    if issue_type == "system_unclassified":
        values = (
            SLAB_SYSTEM_VALUES
            if diagnostic_issue
            and diagnostic_issue.element_class in {"IfcSlab", "IfcSlabStandardCase"}
            else WALL_SYSTEM_VALUES
        )
        if not isinstance(value, str) or value not in values:
            problems.append(f"invalid_system_value: {location}: {value!r}")
        return

    if property_name == "ThermalTransmittance":
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            problems.append(f"invalid_thermal_transmittance: {location}: {value!r}")
        if "W/(m\u00b2\u00b7K)" not in notes:
            problems.append(f"thermal_notes_missing_unit: {location}")
        return
    if property_name in {"LoadBearing", "IsLoadBearing"}:
        if type(value) is not bool:
            problems.append(f"invalid_boolean_value: {location}: {value!r}")
        return
    if property_name == "Category":
        if not isinstance(value, str) or value not in CATEGORY_VALUES:
            problems.append(f"invalid_category_value: {location}: {value!r}")
        return
    if property_name == "FireRating":
        if not isinstance(value, str) or FIRE_RATING_PATTERN.fullmatch(value) is None:
            problems.append(f"invalid_fire_rating: {location}: {value!r}")
        return
    problems.append(f"unsupported_item_property: {location}: {property_name!r}")


def _validate_skip_reasons(entries: list[Any], problems: list[str]) -> None:
    for index, entry in enumerate(entries):
        if isinstance(entry, Mapping) and (
            not isinstance(entry.get("reason"), str) or not entry["reason"].strip()
        ):
            problems.append(f"blank_skip_reason: skipped[{index}]")


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
