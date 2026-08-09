"""Validação estrutural local para documentos canônicos de ground truth."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.experiment.evaluator import GroundTruthItem
from src.models import Issue

NaturalKey = tuple[str, str, str]
LEGACY_REFERENCE_LOCK_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "evaluation" / "legacy-reference.lock.json"
)

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
ACOUSTIC_RATING_PATTERN = re.compile(r"^Rw [0-9]{2} dB$")
IFC_RELATION_PATTERN = re.compile(r"^IfcRel[A-Za-z0-9_]+$")
EQUIVALENCE_ID_PATTERN = re.compile(r"^eq-[0-9a-f]{16}$")
CONFIDENCE_VALUES = frozenset({"high", "medium", "low"})
SOURCE_KIND_VALUES = frozenset(
    {
        "ifc_literal",
        "ifc_alias",
        "existing_gt",
        "equivalent_donor",
        "calculation",
        "normative_rule",
        "typology",
        "probable",
    }
)


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
    if metadata.get("protocol") == "full-coverage-equivalent-v1":
        _validate_integral_contract(metadata, items, skipped, problems)

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


def _validate_integral_contract(
    metadata: Mapping[str, Any],
    items: list[Any],
    skipped: list[Any],
    problems: list[str],
) -> None:
    if skipped:
        problems.append("integral_protocol_requires_zero_skips")
    if metadata.get("policy_version") != "full-coverage-equivalent-v1":
        problems.append("invalid_integral_policy_version")

    decisions: dict[str, str] = {}
    confidence_counts = {name: 0 for name in ("high", "medium", "low")}
    legacy_count = 0
    for index, entry in enumerate(items):
        if not isinstance(entry, Mapping):
            continue
        location = f"items[{index}]"
        for field in (
            "equivalence_id",
            "confidence",
            "source_kind",
            "legacy_reference",
            "notes",
        ):
            if field not in entry:
                problems.append(f"missing_integral_field: {location}.{field}")

        equivalence_id = entry.get("equivalence_id")
        if (
            not isinstance(equivalence_id, str)
            or EQUIVALENCE_ID_PATTERN.fullmatch(equivalence_id) is None
        ):
            problems.append(f"invalid_equivalence_id: {location}: {equivalence_id!r}")
            continue
        confidence = entry.get("confidence")
        if confidence not in CONFIDENCE_VALUES:
            problems.append(f"invalid_confidence: {location}: {confidence!r}")
        else:
            confidence_counts[str(confidence)] += 1
        source_kind = entry.get("source_kind")
        if source_kind not in SOURCE_KIND_VALUES:
            problems.append(f"invalid_source_kind: {location}: {source_kind!r}")
        legacy_reference = entry.get("legacy_reference")
        if type(legacy_reference) is not bool:
            problems.append(f"invalid_legacy_reference: {location}: {legacy_reference!r}")
        elif legacy_reference:
            legacy_count += 1
        notes = entry.get("notes")
        if confidence == "low" and (
            not isinstance(notes, str) or not notes.startswith("Hipótese congelada:")
        ):
            problems.append(f"low_confidence_without_hypothesis: {location}")

        decision = json.dumps(
            [
                entry.get("expected_value"),
                entry.get("accepted_alternatives", []),
                confidence,
                source_kind,
            ],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        previous = decisions.setdefault(equivalence_id, decision)
        if previous != decision:
            problems.append(f"equivalence_decision_mismatch: {equivalence_id}")

    declared_confidence = metadata.get("confidence_counts")
    if declared_confidence != confidence_counts:
        problems.append(
            "confidence_counts_mismatch: "
            f"declared={declared_confidence!r}, actual={confidence_counts!r}"
        )
    if metadata.get("equivalence_class_count") != len(decisions):
        problems.append(
            "equivalence_class_count_mismatch: "
            f"declared={metadata.get('equivalence_class_count')!r}, actual={len(decisions)}"
        )
    if metadata.get("legacy_reference_count") != legacy_count:
        problems.append(
            "legacy_reference_count_mismatch: "
            f"declared={metadata.get('legacy_reference_count')!r}, actual={legacy_count}"
        )
    if metadata.get("total_diagnostic_issues") != len(items):
        problems.append(
            "integral_diagnostic_count_mismatch: "
            f"declared={metadata.get('total_diagnostic_issues')!r}, actual={len(items)}"
        )


def sha256_file(path: str | Path) -> str:
    """Retorna o SHA-256 hexadecimal do arquivo imut\u00e1vel de entrada."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_legacy_items_sha256(items: Sequence[GroundTruthItem]) -> str:
    """Hash semântico estável dos campos históricos que não podem sofrer drift."""
    payload = [
        {
            "element_guid": item.element_guid,
            "issue_type": item.issue_type,
            "check_property": item.check_property,
            "issue_id": item.issue_id,
            "expected_value": item.expected_value,
            "accepted_alternatives": item.accepted_alternatives,
        }
        for item in sorted(
            items,
            key=lambda entry: (
                entry.element_guid or "",
                entry.issue_type or "",
                entry.check_property,
                entry.issue_id or "",
            ),
        )
    ]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_legacy_reference_lock(
    document: Mapping[str, Any],
    lock_path: str | Path = LEGACY_REFERENCE_LOCK_PATH,
) -> None:
    """Confere count/hash do subconjunto histórico declarado no YAML integral."""
    metadata = document.get("metadata")
    dataset = metadata.get("source_dataset") if isinstance(metadata, Mapping) else None
    if not isinstance(dataset, str) or not dataset:
        raise GroundTruthValidationError("legacy_reference_dataset_missing")
    try:
        lock = json.loads(Path(lock_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GroundTruthValidationError(f"legacy_reference_lock_invalid: {error}") from error
    try:
        record = lock["datasets"][dataset]
        expected_count = record["count"]
        expected_sha256 = record["semantic_sha256"]
    except (KeyError, TypeError) as error:
        raise GroundTruthValidationError(
            f"legacy_reference_lock_missing_dataset: {dataset}"
        ) from error
    raw_items = document.get("items")
    if not isinstance(raw_items, list):
        raise GroundTruthValidationError("legacy_reference_items_invalid")
    try:
        items = [
            GroundTruthItem.model_validate(item)
            for item in raw_items
            if isinstance(item, Mapping) and item.get("legacy_reference") is True
        ]
    except Exception as error:
        raise GroundTruthValidationError(f"legacy_reference_items_invalid: {error}") from error
    actual_sha256 = canonical_legacy_items_sha256(items)
    if expected_count != len(items) or expected_sha256 != actual_sha256:
        raise GroundTruthValidationError(
            "legacy_reference_semantic_drift: "
            f"expected count/hash={expected_count}/{expected_sha256}, "
            f"actual={len(items)}/{actual_sha256}"
        )


def validate_ground_truth_against_issues(
    path: str | Path,
    issues: Sequence[Issue],
    *,
    ifc_path: str | Path,
    ids_path: str | Path,
    legacy_lock_path: str | Path = LEGACY_REFERENCE_LOCK_PATH,
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
    if metadata.get("protocol") == "full-coverage-equivalent-v1":
        try:
            validate_legacy_reference_lock(document, legacy_lock_path)
        except GroundTruthValidationError as error:
            problems.append(str(error))

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
    if property_name in {
        "LoadBearing",
        "IsLoadBearing",
        "IsExternal",
        "HasNonSkidSurface",
    }:
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
    if property_name == "AcousticRating":
        if not isinstance(value, str) or ACOUSTIC_RATING_PATTERN.fullmatch(value) is None:
            problems.append(f"invalid_acoustic_rating: {location}: {value!r}")
        return
    if property_name == "SolarHeatGainCoefficient":
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 <= value <= 1
        ):
            problems.append(f"invalid_solar_heat_gain_coefficient: {location}: {value!r}")
        return
    if issue_type == "relation_broken":
        if not isinstance(value, str) or IFC_RELATION_PATTERN.fullmatch(value) is None:
            problems.append(f"invalid_ifc_relation: {location}: {value!r}")
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
