"""Contrato do construtor deterministico dos ground truths canonicos."""

from __future__ import annotations

import hashlib
import sqlite3
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import ifcopenshell
import pytest
import yaml

from scripts import build_ground_truths as builder
from src.config import get_settings
from src.experiment.evaluator import GroundTruth, GroundTruthItem
from src.experiment.ground_truth_validation import GroundTruthValidationError
from src.experiment.gt_extractor import GTExtractionResult, SkippedIssue
from src.ifc_analyzer.material_reader import MaterialReading
from src.models import Issue, Suggestion
from src.suggestion_engine.suggestion_cache import SuggestionCache

RATIFIED_LF_SHA256 = "7d1b1dc8b4756e5a48cd28925d3dceb53a83ab401c31ae0fcf80914ddf85bccb"


def _issue(
    guid: str = "GUID-A",
    *,
    property_name: str = "Category",
    issue_type: str = "pset_missing",
    element_class: str = "IfcSpace",
) -> Issue:
    return Issue(
        element_guid=guid,
        element_class=element_class,
        element_name="Elemento",
        issue_type=issue_type,
        severity="medium",
        description="Ausente",
        context={"check_property": property_name},
    )


def _result(issue: Issue, *, value: Any = "BEDROOM") -> GTExtractionResult:
    return GTExtractionResult(
        ground_truth=GroundTruth(
            items=[
                GroundTruthItem(
                    element_guid=issue.element_guid,
                    issue_type=issue.issue_type,
                    check_property=issue.context["check_property"],
                    issue_id=issue.id,
                    expected_value=value,
                    verified=True,
                    notes="Category derivada exclusivamente do LongName.",
                )
            ],
            metadata={},
        )
    )


def _spec(tmp_path: Path, key: str = "casa") -> builder.DatasetSpec:
    ifc_path = tmp_path / f"{key}.ifc"
    ifc_path.write_bytes(b"synthetic ifc")
    return builder.DatasetSpec(
        key=key,
        ifc_path=ifc_path,
        ground_truth_path=tmp_path / "ground_truth.yaml",
        building_context={
            "building_type": (
                "Residencial multifamiliar" if key == "predio" else "Residencial unifamiliar"
            ),
            "bioclimatic_zone": "4A",
        },
    )


def _install_fake_pipeline(monkeypatch: pytest.MonkeyPatch, issues: list[Issue]) -> None:
    class FakeModel:
        def by_guid(self, guid: str):
            return SimpleNamespace(
                GlobalId=guid,
                Name="Tipo",
                ObjectType="Tipo",
                LongName="Quarto",
                is_a=lambda: next(i.element_class for i in issues if i.element_guid == guid),
            )

        def by_type(self, _ifc_class: str):
            return []

    class FakePipeline:
        closed = False

        def __init__(self, ifc_path: str, context: dict[str, str], *, ids_path: str):
            self.ifc_file = FakeModel()

        def diagnose(self):
            return SimpleNamespace(issues=issues)

        def close(self):
            type(self).closed = True

    monkeypatch.setattr(builder, "QualityPipeline", FakePipeline)


def _install_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ids_path = tmp_path / "requirements.ids"
    ids_path.write_bytes(b"synthetic ids")
    monkeypatch.setattr(builder, "IDS_PATH", ids_path)
    monkeypatch.setattr(builder, "IDS_SHA256", hashlib.sha256(b"synthetic ids").hexdigest())
    return ids_path


def _cache_canary_snapshot(path: Path) -> tuple[int, dict[str, tuple[str, int, int]]]:
    with sqlite3.connect(
        f"file:{path.as_posix()}?mode=ro&immutable=1", uri=True
    ) as connection:
        row_count = int(connection.execute("SELECT COUNT(*) FROM suggestion_cache").fetchone()[0])
    files: dict[str, tuple[str, int, int]] = {}
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        if candidate.exists():
            content = candidate.read_bytes()
            files[candidate.name] = (
                hashlib.sha256(content).hexdigest(),
                len(content),
                candidate.stat().st_mtime_ns,
            )
    return row_count, files


def test_dataset_registry_has_predio_and_casa_only():
    """Adicionar ou omitir dataset do contrato deve quebrar este teste."""
    assert set(builder.DATASETS) == {"predio", "casa"}
    assert builder.DATASETS["predio"].building_context == {
        "building_type": "Residencial multifamiliar",
        "bioclimatic_zone": "4A",
    }
    assert builder.DATASETS["casa"].building_context == {
        "building_type": "Residencial unifamiliar",
        "bioclimatic_zone": "4A",
    }


def test_ratified_legacy_snapshot_is_lf_and_matches_frozen_hash():
    """O GT canônico preserva a proveniência da base autoral ratificada em LF."""
    path = builder.DATASETS["predio"].ground_truth_path
    content = path.read_bytes()
    document = yaml.safe_load(content.decode("utf-8"))

    assert b"\r\n" not in content
    assert document["metadata"]["protocol"] == "evidence-audited-v1"
    assert document["metadata"]["previous_gt_sha256"] == RATIFIED_LF_SHA256
    assert builder.RATIFIED_LEGACY_SHA256 == RATIFIED_LF_SHA256


def test_ground_truth_yaml_has_lf_git_attribute():
    """Checkout futuro nao pode voltar a materializar os GTs canonicos em CRLF."""
    completed = subprocess.run(
        [
            "git",
            "check-attr",
            "text",
            "eol",
            "--",
            "data/evaluation/predio/ground_truth.yaml",
        ],
        cwd=builder.PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert ": text: set" in completed.stdout
    assert ": eol: lf" in completed.stdout


def test_build_preserves_literal_check_property(tmp_path, monkeypatch):
    """Coagir o campo literal da issue deve quebrar este teste."""
    issue = _issue(property_name="LoadBearing", element_class="IfcWall")
    _install_ids(tmp_path, monkeypatch)
    _install_fake_pipeline(monkeypatch, [issue])
    monkeypatch.setattr(
        builder,
        "derive_casa_decision",
        lambda *args, **kwargs: builder.AuditDecision(
            expected_value=False,
            notes="Intencionalidade declarada no modelo.",
        ),
    )

    result, returned_issues = builder.build_dataset(_spec(tmp_path))

    assert returned_issues == [issue]
    assert result.ground_truth.items[0].check_property == "LoadBearing"


def test_build_rejects_ids_that_does_not_match_frozen_profile(tmp_path, monkeypatch):
    """Gerar metadata para outro IDS em vez de falhar deve quebrar este teste."""
    issue = _issue()
    ids_path = _install_ids(tmp_path, monkeypatch)
    _install_fake_pipeline(monkeypatch, [issue])
    monkeypatch.setattr(builder, "IDS_SHA256", "0" * 64)

    with pytest.raises(ValueError, match="hash do IDS"):
        builder.build_dataset(_spec(tmp_path))

    assert ids_path.read_bytes() == b"synthetic ids"


def test_cli_missing_ifc_reports_its_dataset_path_and_frozen_hash(tmp_path, monkeypatch, capsys):
    """Instalação incompleta precisa identificar qual IFC canônico obter."""
    spec = builder.DatasetSpec(
        key="casa",
        ifc_path=tmp_path / "missing-casa.ifc",
        ground_truth_path=tmp_path / "ground_truth.yaml",
        building_context={},
    )

    monkeypatch.setattr(builder, "DATASETS", {"casa": spec})

    assert builder.main(["--dataset", "casa"]) == 1
    stderr = capsys.readouterr().err
    assert str(spec.ifc_path) in stderr
    assert builder.EXPECTED_INPUT_IFC_SHA256["casa"] in stderr


def test_cli_missing_ids_reports_its_path_and_frozen_hash(tmp_path, monkeypatch, capsys):
    """Instalação incompleta precisa identificar qual IDS canônico obter."""
    spec = _spec(tmp_path, "casa")
    missing_ids = tmp_path / "missing-requirements.ids"
    monkeypatch.setattr(builder, "IDS_PATH", missing_ids)
    monkeypatch.setattr(builder, "DATASETS", {"casa": spec})

    assert builder.main(["--dataset", "casa"]) == 1
    stderr = capsys.readouterr().err
    assert str(missing_ids) in stderr
    assert builder.IDS_SHA256 in stderr


def test_missing_legacy_predio_reports_ratified_hash(tmp_path):
    """A fonte legada ausente permanece identificável pela identidade ratificada."""
    spec = _spec(tmp_path, "predio")
    missing_legacy = tmp_path / "missing-legacy.yaml"

    with pytest.raises(FileNotFoundError) as error:
        builder._read_predio_source(missing_legacy, spec)

    assert str(missing_legacy) in str(error.value)
    assert builder.RATIFIED_LEGACY_SHA256 in str(error.value)


def test_build_partitions_every_issue_into_item_or_skip(tmp_path, monkeypatch):
    """Perder ou duplicar issue entre item/skip deve quebrar este teste."""
    accepted = _issue("GUID-A")
    skipped = _issue("GUID-B")
    _install_ids(tmp_path, monkeypatch)
    _install_fake_pipeline(monkeypatch, [accepted, skipped])

    def decide(issue, **_kwargs):
        if issue.element_guid == "GUID-A":
            return builder.AuditDecision(
                expected_value="BEDROOM",
                notes="Category derivada exclusivamente do LongName.",
            )
        return builder.AuditDecision(skip_reason="evidencia insuficiente")

    monkeypatch.setattr(builder, "derive_casa_decision", decide)

    result, issues = builder.build_dataset(_spec(tmp_path))

    assert len(result.ground_truth.items) == 1
    assert len(result.skipped) == 1
    assert len(result.ground_truth.items) + len(result.skipped) == len(issues) == 2
    assert {result.ground_truth.items[0].issue_id, result.skipped[0].issue_id} == {
        accepted.id,
        skipped.id,
    }


def test_build_orders_output_deterministically(tmp_path, monkeypatch):
    """Depender da ordem do diagnostico deve quebrar este teste."""
    first = _issue("GUID-Z")
    second = _issue("GUID-A")
    _install_ids(tmp_path, monkeypatch)
    _install_fake_pipeline(monkeypatch, [first, second])
    monkeypatch.setattr(
        builder,
        "derive_casa_decision",
        lambda *args, **kwargs: builder.AuditDecision(
            expected_value="BEDROOM",
            notes="Category derivada exclusivamente do LongName.",
        ),
    )
    spec = _spec(tmp_path)

    result, issues = builder.build_dataset(spec)
    first_path = builder.write_canonical_ground_truth(result, issues, spec)
    first_bytes = first_path.read_bytes()
    result_again, issues_again = builder.build_dataset(spec)
    second_path = builder.write_canonical_ground_truth(result_again, issues_again, spec)

    document = yaml.safe_load(second_path.read_text(encoding="utf-8"))
    assert [item["element_guid"] for item in document["items"]] == ["GUID-A", "GUID-Z"]
    assert second_path.read_bytes() == first_bytes


def test_build_refuses_to_overwrite_without_valid_output(tmp_path, monkeypatch):
    """Substituir o YAML antes da validacao deve quebrar este teste."""
    issue = _issue()
    _install_ids(tmp_path, monkeypatch)
    spec = _spec(tmp_path)
    spec.ground_truth_path.write_bytes(b"original ground truth")
    monkeypatch.setattr(
        builder,
        "validate_ground_truth_against_issues",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            GroundTruthValidationError("invalid candidate")
        ),
    )

    with pytest.raises(GroundTruthValidationError, match="invalid candidate"):
        builder.write_canonical_ground_truth(_result(issue), [issue], spec)

    assert spec.ground_truth_path.read_bytes() == b"original ground truth"
    assert not list(tmp_path.glob("*.tmp"))


def test_check_mode_never_writes(tmp_path, monkeypatch):
    """Criar temporario ou alterar destino no modo check deve quebrar este teste."""
    issue = _issue()
    _install_ids(tmp_path, monkeypatch)
    spec = _spec(tmp_path)
    result = _result(issue)
    expected = builder.canonical_ground_truth_bytes(result, [issue], spec)
    spec.ground_truth_path.write_bytes(expected)
    before = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in tmp_path.iterdir()
    }
    monkeypatch.setattr(builder, "DATASETS", {"casa": spec})
    monkeypatch.setattr(builder, "EXPECTED_GROUND_TRUTH_SHA256", {})
    monkeypatch.setattr(builder, "build_dataset", lambda _spec: (result, [issue]))
    monkeypatch.setattr(builder, "validate_ground_truth_against_issues", lambda *a, **k: None)

    exit_code = builder.main(["--dataset", "casa", "--check"])

    after = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in tmp_path.iterdir()}
    assert exit_code == 0
    assert after == before


def test_check_mode_returns_nonzero_on_drift(tmp_path, monkeypatch):
    """Aceitar bytes divergentes no modo check deve quebrar este teste."""
    issue = _issue()
    _install_ids(tmp_path, monkeypatch)
    spec = _spec(tmp_path)
    spec.ground_truth_path.write_bytes(b"semantic drift")
    monkeypatch.setattr(builder, "DATASETS", {"casa": spec})
    monkeypatch.setattr(builder, "build_dataset", lambda _spec: (_result(issue), [issue]))

    assert builder.main(["--dataset", "casa", "--check"]) == 1
    assert spec.ground_truth_path.read_bytes() == b"semantic drift"


def test_check_mode_never_touches_persistent_suggestion_cache(tmp_path, monkeypatch):
    """Abrir o SQLite da aplicacao durante --check deve quebrar este teste."""
    issue = _issue()
    ids_path = _install_ids(tmp_path, monkeypatch)
    spec = _spec(tmp_path)
    ifc_file = ifcopenshell.file(schema="IFC4")
    ifc_file.write(str(spec.ifc_path))

    expected = GTExtractionResult(
        ground_truth=GroundTruth(items=[]),
        skipped=[
            SkippedIssue(
                issue_id=issue.id,
                element_guid=issue.element_guid,
                issue_type=issue.issue_type,
                check_property="Category",
                reason="GlobalId ausente no IFC canonico",
            )
        ],
    )
    spec.ground_truth_path.write_bytes(
        builder.canonical_ground_truth_bytes(expected, [issue], spec)
    )
    output_before = (
        spec.ground_truth_path.read_bytes(),
        spec.ground_truth_path.stat().st_mtime_ns,
    )

    cache_path = tmp_path / "suggestion_cache.db"
    cache = SuggestionCache(cache_path)
    try:
        cache.set(
            "canary-signature",
            [
                Suggestion(
                    label="canary",
                    value="canary",
                    justification="linha sentinela",
                    confidence="alta",
                )
            ],
            model_version="canary-model",
            prompt_version="obsolete-prompt",
        )
    finally:
        cache.close()
    cache_before = _cache_canary_snapshot(cache_path)

    monkeypatch.setenv("SUGGESTION_CACHE_ENABLED", "true")
    monkeypatch.setenv("SUGGESTION_CACHE_PATH", str(cache_path))
    get_settings.cache_clear()
    monkeypatch.setattr(builder, "DATASETS", {"casa": spec})
    monkeypatch.setattr(builder, "EXPECTED_GROUND_TRUTH_SHA256", {})
    monkeypatch.setattr(
        builder.QualityPipeline,
        "diagnose",
        lambda _self: SimpleNamespace(issues=[issue]),
    )

    exit_code = builder.main(["--dataset", "casa", "--check"])

    assert exit_code == 0
    assert _cache_canary_snapshot(cache_path) == cache_before
    assert (
        spec.ground_truth_path.read_bytes(),
        spec.ground_truth_path.stat().st_mtime_ns,
    ) == output_before
    assert get_settings().suggestion_cache_enabled is True
    assert get_settings().suggestion_cache_path == str(cache_path)
    assert ids_path.read_bytes() == b"synthetic ids"


def test_build_hashes_legacy_file_bytes_and_rejects_tampering(tmp_path, monkeypatch):
    """Repassar constante sem hashear os bytes adulterados deve quebrar este teste."""
    issue = _issue()
    _install_ids(tmp_path, monkeypatch)
    _install_fake_pipeline(monkeypatch, [issue])
    legacy_path = tmp_path / "legacy.yaml"
    legacy_path.write_text(
        yaml.safe_dump(
            {
                "metadata": {"protocol": "norm-derived-draft"},
                "items": [
                    {
                        "element_guid": issue.element_guid,
                        "issue_type": issue.issue_type,
                        "check_property": "Category",
                        "issue_id": issue.id,
                        "expected_value": "BEDROOM",
                        "verified": True,
                        "notes": "Revisado pelo autor.",
                    }
                ],
                "skipped": [],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    initial_digest = hashlib.sha256(legacy_path.read_bytes()).hexdigest()
    monkeypatch.setattr(builder, "RATIFIED_LEGACY_SHA256", initial_digest)
    observed_digests: list[str] = []

    def audit_with_observed_digest(issue, _legacy, *, legacy_source_sha256):
        observed_digests.append(legacy_source_sha256)
        return builder.AuditDecision(
            expected_value="BEDROOM",
            notes="Revisado pelo autor.",
        )

    monkeypatch.setattr(builder, "audit_legacy_item", audit_with_observed_digest)
    spec = _spec(tmp_path, "predio")

    result, _ = builder.build_dataset(spec, legacy_gt_path=legacy_path)
    assert result.ground_truth.items[0].expected_value == "BEDROOM"
    assert observed_digests == [initial_digest]

    legacy_path.write_bytes(legacy_path.read_bytes() + b"\n# adulterado")
    with pytest.raises(ValueError, match=r"hash.*legado"):
        builder.build_dataset(spec, legacy_gt_path=legacy_path)


def test_frozen_canonical_hash_prevents_reuse_laundering(tmp_path, monkeypatch):
    """Reutilizar YAML canonical adulterado apesar do hash congelado deve quebrar este teste."""
    issue = _issue()
    _install_ids(tmp_path, monkeypatch)
    _install_fake_pipeline(monkeypatch, [issue])
    spec = _spec(tmp_path, "predio")
    canonical = {
        "metadata": {
            "protocol": "evidence-audited-v1",
            "previous_gt_sha256": builder.RATIFIED_LEGACY_SHA256,
        },
        "items": [],
        "skipped": [
            {
                "issue_id": issue.id,
                "element_guid": issue.element_guid,
                "issue_type": issue.issue_type,
                "check_property": "Category",
                "reason": "abstencao",
            }
        ],
    }
    spec.ground_truth_path.write_text(
        yaml.safe_dump(canonical, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    monkeypatch.setitem(builder.EXPECTED_GROUND_TRUTH_SHA256, "predio", "0" * 64)

    with pytest.raises(ValueError, match="hash canonico"):
        builder.build_dataset(spec, legacy_gt_path=spec.ground_truth_path)


def test_canonical_reuse_requires_frozen_hash_pin(tmp_path, monkeypatch):
    """Ausencia do pin canonical nao pode transformar o proprio YAML em autoridade."""
    issue = _issue()
    _install_ids(tmp_path, monkeypatch)
    _install_fake_pipeline(monkeypatch, [issue])
    spec = _spec(tmp_path, "predio")
    spec.ground_truth_path.write_text(
        yaml.safe_dump(
            {
                "metadata": {
                    "protocol": "evidence-audited-v1",
                    "previous_gt_sha256": builder.RATIFIED_LEGACY_SHA256,
                },
                "items": [],
                "skipped": [
                    {
                        "issue_id": issue.id,
                        "element_guid": issue.element_guid,
                        "issue_type": issue.issue_type,
                        "check_property": "Category",
                        "reason": "abstencao",
                    }
                ],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.delitem(builder.EXPECTED_GROUND_TRUTH_SHA256, "predio", raising=False)

    with pytest.raises(ValueError, match=r"hash canonico.*nao congelado"):
        builder.build_dataset(spec, legacy_gt_path=spec.ground_truth_path)


def test_casa_thermal_group_preserves_smallest_donor_value_and_honest_unit(tmp_path, monkeypatch):
    """Calcular media ou ocultar a unidade IFC ausente deve quebrar este teste."""
    issue = _issue(
        "TARGET",
        property_name="ThermalTransmittance",
        element_class="IfcWall",
    )

    class Element:
        def __init__(self, guid, value=None):
            self.GlobalId = guid
            self.LongName = None
            self.psets = (
                {"Pset_WallCommon": {"ThermalTransmittance": value}} if value is not None else {}
            )
            self.type = SimpleNamespace(GlobalId="TYPE-1", Name="Parede exata")

        def is_a(self):
            return "IfcWall"

    target = Element("TARGET")
    donors = [Element("DONOR-B", 1.69), Element("DONOR-A", 1.6875)]

    class Model:
        def by_guid(self, _guid):
            return target

        def by_type(self, ifc_class):
            return donors if ifc_class == "IfcWall" else []

    class Pipeline:
        def __init__(self, *_args, **_kwargs):
            self.ifc_file = Model()

        def diagnose(self):
            return SimpleNamespace(issues=[issue])

        def close(self):
            pass

    _install_ids(tmp_path, monkeypatch)
    monkeypatch.setattr(builder, "QualityPipeline", Pipeline)
    monkeypatch.setattr(builder.ue, "get_type", lambda element: element.type)
    monkeypatch.setattr(builder.ue, "get_psets", lambda element: element.psets)
    monkeypatch.setattr(builder, "read_material_layers", lambda _element: MaterialReading())

    result, _ = builder.build_dataset(_spec(tmp_path))

    item = result.ground_truth.items[0]
    assert item.expected_value == 1.6875
    assert "DONOR-A, DONOR-B" in item.notes
    assert builder.THERMAL_UNIT in item.notes


def test_casa_thermal_group_marks_values_over_one_percent_as_conflicted(tmp_path, monkeypatch):
    """Propagar doadores que divergem mais de 1% deve quebrar este teste."""
    issue = _issue(
        "TARGET",
        property_name="ThermalTransmittance",
        element_class="IfcWall",
    )

    class Element:
        def __init__(self, guid, value=None):
            self.GlobalId = guid
            self.LongName = None
            self.psets = (
                {"Pset_WallCommon": {"ThermalTransmittance": value}} if value is not None else {}
            )
            self.type = SimpleNamespace(GlobalId="TYPE-1", Name="Parede exata")

        def is_a(self):
            return "IfcWall"

    target = Element("TARGET")
    donors = [Element("DONOR-A", 1.0), Element("DONOR-B", 1.02)]

    class Model:
        def by_guid(self, _guid):
            return target

        def by_type(self, ifc_class):
            return donors if ifc_class == "IfcWall" else []

    class Pipeline:
        def __init__(self, *_args, **_kwargs):
            self.ifc_file = Model()

        def diagnose(self):
            return SimpleNamespace(issues=[issue])

        def close(self):
            pass

    _install_ids(tmp_path, monkeypatch)
    monkeypatch.setattr(builder, "QualityPipeline", Pipeline)
    monkeypatch.setattr(builder.ue, "get_type", lambda element: element.type)
    monkeypatch.setattr(builder.ue, "get_psets", lambda element: element.psets)
    monkeypatch.setattr(builder, "read_material_layers", lambda _element: MaterialReading())

    result, _ = builder.build_dataset(_spec(tmp_path))

    assert result.ground_truth.items == []
    assert "conflito" in result.skipped[0].reason


def test_predio_reuses_canonical_item_without_reauditing_or_repeating_note(tmp_path, monkeypatch):
    """Reauditar o canonical e duplicar a nota autoral deve quebrar este teste."""
    issue = _issue()
    _install_ids(tmp_path, monkeypatch)
    _install_fake_pipeline(monkeypatch, [issue])
    spec = _spec(tmp_path, "predio")
    note = "Category derivada exclusivamente do LongName."
    spec.ground_truth_path.write_text(
        yaml.safe_dump(
            {
                "metadata": {
                    "protocol": "evidence-audited-v1",
                    "previous_gt_sha256": builder.RATIFIED_LEGACY_SHA256,
                },
                "items": [
                    {
                        "element_guid": issue.element_guid,
                        "issue_type": issue.issue_type,
                        "check_property": "Category",
                        "issue_id": issue.id,
                        "expected_value": "BEDROOM",
                        "accepted_alternatives": [],
                        "verified": True,
                        "notes": note,
                    }
                ],
                "skipped": [],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setitem(
        builder.EXPECTED_GROUND_TRUTH_SHA256,
        "predio",
        hashlib.sha256(spec.ground_truth_path.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(
        builder,
        "audit_legacy_item",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("reauditou")),
    )

    result, _ = builder.build_dataset(spec)

    assert result.ground_truth.items[0].notes == note
