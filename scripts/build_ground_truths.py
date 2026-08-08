"""Constroi ground truths canonicos de predio e casa sem participacao de LLM."""

# ruff: noqa: E402 -- execucao direta exige incluir a raiz antes dos imports locais.

from __future__ import annotations

import argparse
import math
import os
import sys
import tempfile
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import ifcopenshell.util.element as ue
import yaml

from src.config import get_settings
from src.experiment.evaluator import GroundTruth, GroundTruthItem
from src.experiment.ground_truth_audit import (
    AuditDecision,
    ThermalEvidence,
    audit_canonical_item,
    audit_legacy_item,
    derive_casa_decision,
)
from src.experiment.ground_truth_validation import (
    sha256_file,
    validate_ground_truth_against_issues,
)
from src.experiment.gt_extractor import GTExtractionResult, SkippedIssue
from src.ifc_analyzer.material_reader import read_material_layers
from src.models import Issue
from src.pipeline import QualityPipeline

IDS_PATH = PROJECT_ROOT / "data" / "ids_templates" / "residencial_nbr15575.ids"
RATIFIED_LEGACY_SHA256 = "7d1b1dc8b4756e5a48cd28925d3dceb53a83ab401c31ae0fcf80914ddf85bccb"
IDS_SHA256 = "f698f2c020d79140bb314f077f8de680f492fd7ba42867e4000a4cead5d20905"
EXPECTED_INPUT_IFC_SHA256 = {
    "predio": "a71c8be30d82760218f5b3f3a1c476b49e3f30e608b0065916b9d5206a1a6dd0",
    "casa": "3b84789c7396449f2c8a3d2f4a66468d81e59f8351ebd4b71fad161fa06112f2",
}
THERMAL_UNIT = (
    "W/(m²·K) (unidade semântica de IfcThermalTransmittanceMeasure; Unit IFC não declarada)"
)

# SHA-256 dos artefatos canônicos revisados na Task 5; necessário para reuso fechado.
EXPECTED_GROUND_TRUTH_SHA256: dict[str, str] = {
    "predio": "2594d7efee7c29b662e7b9253cb5fe06867a046192f12b62d1acdf00d0199800",
    "casa": "5903db9a3e3904f16a82df38b10d09f13769e7d88f3b61f52730a27dc8627c59",
}


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    ifc_path: Path
    ground_truth_path: Path
    building_context: dict[str, str]


DATASETS: dict[str, DatasetSpec] = {
    "predio": DatasetSpec(
        key="predio",
        ifc_path=PROJECT_ROOT / "data" / "evaluation" / "predio" / "predio_v1.ifc",
        ground_truth_path=(PROJECT_ROOT / "data" / "evaluation" / "predio" / "ground_truth.yaml"),
        building_context={
            "building_type": "Residencial multifamiliar",
            "bioclimatic_zone": "4A",
        },
    ),
    "casa": DatasetSpec(
        key="casa",
        ifc_path=PROJECT_ROOT / "data" / "evaluation" / "casa" / "casa_v1.ifc",
        ground_truth_path=(PROJECT_ROOT / "data" / "evaluation" / "casa" / "ground_truth.yaml"),
        building_context={
            "building_type": "Residencial unifamiliar",
            "bioclimatic_zone": "4A",
        },
    ),
}

def build_dataset(
    spec: DatasetSpec,
    *,
    legacy_gt_path: Path | None = None,
) -> tuple[GTExtractionResult, list[Issue]]:
    """Diagnostica um IFC e particiona cada issue em item auditado ou abstencao."""
    expected_ifc_sha256 = EXPECTED_INPUT_IFC_SHA256.get(spec.key)
    if expected_ifc_sha256 is None:
        raise ValueError(f"dataset desconhecido: {spec.key}")
    _require_input(spec.ifc_path, "IFC", expected_sha256=expected_ifc_sha256)
    _require_input(IDS_PATH, "IDS", expected_sha256=IDS_SHA256)

    predio_source: tuple[dict[str, Any], str, bool] | None = None
    if spec.key == "predio":
        source_path = Path(legacy_gt_path or spec.ground_truth_path)
        source_sha256 = (
            RATIFIED_LEGACY_SHA256
            if legacy_gt_path is not None
            else EXPECTED_GROUND_TRUTH_SHA256.get(spec.key, RATIFIED_LEGACY_SHA256)
        )
        predio_source = _read_predio_source(
            source_path,
            spec,
            expected_sha256=source_sha256,
        )

    with _persistent_suggestion_cache_disabled():
        pipeline: QualityPipeline | None = None
        try:
            pipeline = QualityPipeline(
                str(spec.ifc_path),
                spec.building_context,
                ids_path=str(IDS_PATH),
            )
            report = pipeline.diagnose()
            issues = list(report.issues)
            if spec.key == "predio":
                assert predio_source is not None
                result = _build_predio(issues, *predio_source)
            elif spec.key == "casa":
                result = _build_casa(issues, pipeline.ifc_file)
            else:
                raise ValueError(f"dataset desconhecido: {spec.key}")
        finally:
            if pipeline is not None:
                pipeline.close()

    _require_exact_partition(result, issues)
    result.ground_truth.metadata = _metadata(spec, issues, result)
    return result, issues


def canonical_ground_truth_bytes(
    result: GTExtractionResult,
    issues: Sequence[Issue],
    spec: DatasetSpec,
) -> bytes:
    """Serializa o candidato em bytes YAML estaveis, sem tocar no sistema de arquivos."""
    _require_exact_partition(result, issues)
    metadata = _metadata(spec, issues, result)
    items = sorted(result.ground_truth.items, key=_item_sort_key)
    skipped = sorted(result.skipped, key=_skip_sort_key)
    payload = {
        "metadata": metadata,
        "items": [item.model_dump(exclude_none=True, exclude_defaults=False) for item in items],
        "skipped": [entry.model_dump(exclude_none=True) for entry in skipped],
    }
    text = yaml.safe_dump(
        payload,
        allow_unicode=True,
        sort_keys=False,
        width=100,
    )
    return text.encode("utf-8")


def write_canonical_ground_truth(
    result: GTExtractionResult,
    issues: Sequence[Issue],
    spec: DatasetSpec,
) -> Path:
    """Valida um temporario no mesmo diretorio e so entao substitui o YAML."""
    candidate = canonical_ground_truth_bytes(result, issues, spec)
    output = spec.ground_truth_path
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output.parent,
        prefix=f".{output.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(candidate)
            stream.flush()
            os.fsync(stream.fileno())
        validate_ground_truth_against_issues(
            temporary,
            issues,
            ifc_path=spec.ifc_path,
            ids_path=IDS_PATH,
        )
        temporary.replace(output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Constroi ground_truth.yaml canonico para predio e casa."
    )
    parser.add_argument("--dataset", choices=("predio", "casa", "all"), default="all")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Valida e compara os bytes sem criar ou alterar arquivos.",
    )
    args = parser.parse_args(argv)
    selected = list(DATASETS) if args.dataset == "all" else [args.dataset]
    status = 0

    for key in selected:
        spec = DATASETS[key]
        try:
            result, issues = build_dataset(spec)
            candidate = canonical_ground_truth_bytes(result, issues, spec)
            if args.check:
                if not _check_candidate(spec, candidate, issues):
                    print(f"DRIFT {key}: {spec.ground_truth_path}", file=sys.stderr)
                    status = 1
                    continue
                print(f"OK {key}: {len(issues)} issues; sem drift")
                continue

            output = write_canonical_ground_truth(result, issues, spec)
            print(
                f"OK {key}: {len(issues)} issues, "
                f"{len(result.ground_truth.items)} itens, {len(result.skipped)} skips; "
                f"IFC sha256={sha256_file(spec.ifc_path)}; {output}"
            )
        except Exception as error:
            print(f"ERRO {key}: {error}", file=sys.stderr)
            status = 1
    return status


def _read_predio_source(
    path: Path,
    spec: DatasetSpec,
    *,
    expected_sha256: str = RATIFIED_LEGACY_SHA256,
) -> tuple[dict[str, Any], str, bool]:
    _require_file_present(
        path,
        "ground truth legado/canonico do predio",
        expected_sha256=expected_sha256,
    )
    raw_bytes = path.read_bytes()
    digest = _sha256_bytes(raw_bytes)
    try:
        document = yaml.safe_load(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as error:
        raise ValueError(f"ground truth do predio invalido: {error}") from error
    if not isinstance(document, dict):
        raise ValueError("ground truth do predio deve ter mapeamento na raiz")

    metadata = document.get("metadata")
    protocol = metadata.get("protocol") if isinstance(metadata, Mapping) else None
    canonical = protocol == "evidence-audited-v1"
    if canonical:
        assert isinstance(metadata, Mapping)
        if metadata.get("previous_gt_sha256") != RATIFIED_LEGACY_SHA256:
            raise ValueError("previous_gt_sha256 canonico diverge da base ratificada")
        expected = EXPECTED_GROUND_TRUTH_SHA256.get(spec.key)
        if expected is None:
            raise ValueError(f"hash canonico de {spec.key} nao congelado")
        if digest.lower() != expected.lower():
            raise ValueError(
                f"hash canonico de {spec.key} diverge: esperado {expected}, obtido {digest}"
            )
    elif digest != RATIFIED_LEGACY_SHA256:
        raise ValueError(
            "hash do ground truth legado diverge da base ratificada: "
            f"esperado {RATIFIED_LEGACY_SHA256}, obtido {digest}"
        )
    return document, digest, canonical


def _build_predio(
    issues: Sequence[Issue],
    document: dict[str, Any],
    source_digest: str,
    canonical: bool,
) -> GTExtractionResult:
    ground_truth = GroundTruth.model_validate(document)
    item_by_key = {
        item.natural_key: item for item in ground_truth.items if item.natural_key is not None
    }
    skip_by_key = _skips_by_key(document.get("skipped", []))
    items: list[GroundTruthItem] = []
    skipped: list[SkippedIssue] = []

    for issue in issues:
        key = _issue_key(issue)
        prior_item = item_by_key.get(key)
        prior_skip = skip_by_key.get(key)
        if canonical:
            if prior_item is not None:
                expected_canonical_sha256 = EXPECTED_GROUND_TRUTH_SHA256.get("predio")
                if expected_canonical_sha256 is None:
                    raise ValueError("hash canonico de predio nao congelado")
                decision = audit_canonical_item(
                    issue,
                    prior_item,
                    canonical_source_sha256=source_digest,
                    expected_canonical_sha256=expected_canonical_sha256,
                )
                _append_decision(issue, decision, items, skipped)
            elif prior_skip is not None:
                skipped.append(prior_skip.model_copy(update={"issue_id": issue.id}))
            else:
                skipped.append(_skip_for_issue(issue, "issue ausente no GT canonico anterior"))
            continue

        if prior_item is not None:
            decision = audit_legacy_item(
                issue,
                prior_item,
                legacy_source_sha256=source_digest,
            )
            _append_decision(issue, decision, items, skipped)
        elif prior_skip is not None:
            skipped.append(prior_skip.model_copy(update={"issue_id": issue.id}))
        else:
            skipped.append(_skip_for_issue(issue, "issue ausente na base autoral legada"))
    return _result(items, skipped)


def _build_casa(issues: Sequence[Issue], model: Any) -> GTExtractionResult:
    authored = _collect_authored_thermal(issues, model)
    items: list[GroundTruthItem] = []
    skipped: list[SkippedIssue] = []
    for issue in issues:
        try:
            element = model.by_guid(issue.element_guid)
        except RuntimeError:
            element = None
        if element is None:
            decision = AuditDecision(skip_reason="GlobalId ausente no IFC canonico")
        else:
            type_key, type_name = _element_type_identity(element)
            decision = derive_casa_decision(
                issue,
                element_type_key=type_key,
                element_type_name=type_name,
                element_long_name=getattr(element, "LongName", None),
                authored_thermal_by_type=authored,
                material_reading=read_material_layers(element),
            )
        _append_decision(issue, decision, items, skipped)
    return _result(items, skipped)


def _collect_authored_thermal(
    issues: Sequence[Issue], model: Any
) -> dict[tuple[str, str], ThermalEvidence]:
    classes = {
        issue.element_class
        for issue in issues
        if issue.issue_type == "pset_missing"
        and issue.context.get("check_property") == "ThermalTransmittance"
    }
    readings: dict[tuple[str, str], list[tuple[str, float]]] = defaultdict(list)
    for ifc_class in sorted(classes):
        for element in model.by_type(ifc_class):
            value = _authored_thermal_value(element)
            if value is None:
                continue
            key, type_name = _element_type_identity(element)
            evidence_key = key if key[1] else (key[0], type_name)
            if not evidence_key[1]:
                continue
            guid = str(getattr(element, "GlobalId", "") or "").strip()
            if guid:
                readings[evidence_key].append((guid, value))

    evidence: dict[tuple[str, str], ThermalEvidence] = {}
    for key, values in readings.items():
        ordered = sorted(values, key=lambda pair: (pair[0], pair[1]))
        numeric = [value for _, value in ordered]
        conflicted = max(numeric) > min(numeric) * 1.01
        evidence[key] = ThermalEvidence(
            value=ordered[0][1],
            donor_guids=tuple(sorted({guid for guid, _ in ordered})),
            unit=THERMAL_UNIT,
            conflicted=conflicted,
        )
    return evidence


def _authored_thermal_value(element: Any) -> float | None:
    try:
        psets = ue.get_psets(element)
    except Exception:
        return None
    found: list[float] = []
    for properties in psets.values():
        if not isinstance(properties, Mapping):
            continue
        raw = properties.get("ThermalTransmittance")
        if (
            not isinstance(raw, bool)
            and isinstance(raw, (int, float))
            and math.isfinite(raw)
            and raw > 0
        ):
            found.append(float(raw))
    if not found or any(value != found[0] for value in found[1:]):
        return None
    return found[0]


def _element_type_identity(element: Any) -> tuple[tuple[str, str], str]:
    element_class = str(element.is_a())
    try:
        element_type = ue.get_type(element)
    except Exception:
        element_type = None
    if element_type is None:
        return (element_class, ""), ""
    type_guid = str(getattr(element_type, "GlobalId", "") or "").strip()
    type_name = str(getattr(element_type, "Name", "") or "")
    return (element_class, type_guid), type_name


def _append_decision(
    issue: Issue,
    decision: AuditDecision,
    items: list[GroundTruthItem],
    skipped: list[SkippedIssue],
) -> None:
    if decision.skip_reason is not None:
        skipped.append(_skip_for_issue(issue, decision.skip_reason))
        return
    items.append(
        GroundTruthItem(
            element_guid=issue.element_guid,
            issue_type=issue.issue_type,
            check_property=_literal_check_property(issue),
            issue_id=issue.id,
            expected_value=decision.expected_value,
            accepted_alternatives=decision.accepted_alternatives,
            verified=True,
            notes=decision.notes,
        )
    )


def _skip_for_issue(issue: Issue, reason: str) -> SkippedIssue:
    return SkippedIssue(
        issue_id=issue.id,
        element_guid=issue.element_guid,
        issue_type=issue.issue_type,
        check_property=_literal_check_property(issue),
        reason=reason,
    )


def _skips_by_key(raw_entries: Any) -> dict[tuple[str, str, str], SkippedIssue]:
    if not isinstance(raw_entries, list):
        raise ValueError("skipped do ground truth deve ser lista")
    indexed: dict[tuple[str, str, str], SkippedIssue] = {}
    for raw in raw_entries:
        entry = SkippedIssue.model_validate(raw)
        key = (entry.element_guid, entry.issue_type, entry.check_property)
        if key in indexed:
            raise ValueError(f"chave natural duplicada em skipped: {key!r}")
        indexed[key] = entry
    return indexed


def _result(items: list[GroundTruthItem], skipped: list[SkippedIssue]) -> GTExtractionResult:
    return GTExtractionResult(
        ground_truth=GroundTruth(items=sorted(items, key=_item_sort_key)),
        skipped=sorted(skipped, key=_skip_sort_key),
    )


def _metadata(
    spec: DatasetSpec,
    issues: Sequence[Issue],
    result: GTExtractionResult,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "protocol": "evidence-audited-v1",
        "source_dataset": spec.key,
        "locality": "Deodoro, Rio de Janeiro/RJ",
        "building_type": spec.building_context["building_type"],
        "bioclimatic_context": f"ZB {spec.building_context['bioclimatic_zone']}",
        "bioclimatic_context_status": (
            "public technical source; not a formal conformity declaration"
        ),
        "input_ifc_sha256": sha256_file(spec.ifc_path),
        "ids_sha256": sha256_file(IDS_PATH),
    }
    if spec.key == "predio":
        metadata["previous_gt_sha256"] = RATIFIED_LEGACY_SHA256
        metadata["verified_by"] = (
            "Felipe Keller (revisão autoral de 2026-07-02; base mantida em 2026-08-08)"
        )
    else:
        metadata["verified_by"] = (
            "auditoria determinística por evidência "
            "(protocolo aprovado por Felipe Keller em 2026-08-08)"
        )
    metadata.update(
        {
            "verified_at": "2026-08-08",
            "verification_scope": (
                "expert-annotated benchmark reference; not a performance certificate"
            ),
            "total_diagnostic_issues": len(issues),
            "total_items": len(result.ground_truth.items),
            "total_skipped": len(result.skipped),
        }
    )
    return metadata


def _require_exact_partition(result: GTExtractionResult, issues: Sequence[Issue]) -> None:
    diagnostic_keys = [_issue_key(issue) for issue in issues]
    item_keys = [item.natural_key for item in result.ground_truth.items]
    skip_keys = [
        (entry.element_guid, entry.issue_type, entry.check_property) for entry in result.skipped
    ]
    if (
        len(item_keys) + len(skip_keys) != len(diagnostic_keys)
        or len(set(diagnostic_keys)) != len(diagnostic_keys)
        or set(item_keys) & set(skip_keys)
        or set(item_keys) | set(skip_keys) != set(diagnostic_keys)
    ):
        raise ValueError("items e skipped nao formam particao exata das issues")


def _check_candidate(
    spec: DatasetSpec,
    candidate: bytes,
    issues: Sequence[Issue],
) -> bool:
    path = spec.ground_truth_path
    if not path.is_file():
        return False
    actual = path.read_bytes()
    frozen = EXPECTED_GROUND_TRUTH_SHA256.get(spec.key)
    if frozen is not None and _sha256_bytes(actual).lower() != frozen.lower():
        return False
    if actual != candidate:
        return False
    try:
        validate_ground_truth_against_issues(
            path,
            issues,
            ifc_path=spec.ifc_path,
            ids_path=IDS_PATH,
        )
    except Exception:
        return False
    return True


def _issue_key(issue: Issue) -> tuple[str, str, str]:
    return issue.element_guid, issue.issue_type, _literal_check_property(issue)


def _literal_check_property(issue: Issue) -> str:
    if "check_property" not in issue.context:
        if issue.issue_type == "relation_broken":
            return ""
        raise ValueError(f"issue {issue.id} sem check_property literal")
    value = issue.context["check_property"]
    if not isinstance(value, str):
        raise ValueError(f"issue {issue.id} com check_property nao textual")
    return value


def _item_sort_key(item: GroundTruthItem) -> tuple[str, str, str, str]:
    return (
        item.issue_type or "",
        item.element_guid or "",
        item.check_property,
        item.issue_id or "",
    )


def _skip_sort_key(item: SkippedIssue) -> tuple[str, str, str, str]:
    return item.issue_type, item.element_guid, item.check_property, item.issue_id


def _require_input(path: Path, label: str, *, expected_sha256: str | None = None) -> None:
    _require_file_present(path, label, expected_sha256=expected_sha256)
    if expected_sha256 is None:
        return
    actual_sha256 = sha256_file(path)
    if actual_sha256.lower() != expected_sha256.lower():
        raise ValueError(
            f"hash do {label} diverge: esperado {expected_sha256}, obtido {actual_sha256}"
        )


def _require_file_present(
    path: Path,
    label: str,
    *,
    expected_sha256: str | None = None,
) -> None:
    if not path.is_file():
        expected = f"; SHA-256 esperado: {expected_sha256}" if expected_sha256 else ""
        raise FileNotFoundError(f"{label} ausente: {path}{expected}")


@contextmanager
def _persistent_suggestion_cache_disabled() -> Iterator[None]:
    """Impede que o diagnostico abra ou invalide o SQLite da aplicacao."""
    variable = "SUGGESTION_CACHE_ENABLED"
    previous = os.environ.get(variable)
    try:
        os.environ[variable] = "false"
        get_settings.cache_clear()
        yield
    finally:
        if previous is None:
            os.environ.pop(variable, None)
        else:
            os.environ[variable] = previous
        get_settings.cache_clear()


def _sha256_bytes(content: bytes) -> str:
    import hashlib

    return hashlib.sha256(content).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
