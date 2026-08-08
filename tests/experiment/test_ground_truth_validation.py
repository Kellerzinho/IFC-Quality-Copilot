"""Contratos estruturais do documento canônico de ground truth."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

import pytest
import yaml

from src.experiment.evaluator import GroundTruth
from src.experiment.ground_truth_validation import (
    GroundTruthValidationError,
    validate_ground_truth_against_issues,
    validate_ground_truth_document,
)
from src.models import Issue


def _valid_document() -> dict[str, Any]:
    """Documento mínimo, completo e independente do validador."""
    return {
        "metadata": {"total_items": 2, "total_skipped": 1},
        "items": [
            {
                "element_guid": "GUID_WALL_01",
                "issue_type": "pset_missing",
                "check_property": "ThermalTransmittance",
                "issue_id": "issue-wall-01",
                "expected_value": 2.5,
                "verified": True,
            },
            {
                "element_guid": "GUID_SPACE_01",
                "issue_type": "pset_missing",
                "check_property": "ThermalTransmittance",
                "issue_id": "issue-space-01",
                "expected_value": "Lavabo",
                "verified": True,
            },
        ],
        "skipped": [
            {
                "element_guid": "GUID_SKIP_01",
                "issue_type": "pset_missing",
                "check_property": "ThermalTransmittance",
                "issue_id": "issue-skip-01",
                "reason": "Fora do escopo",
            }
        ],
    }


def _write_document(tmp_path, document: dict[str, Any]):
    path = tmp_path / "ground_truth.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _assert_invariant(path, invariant: str) -> None:
    with pytest.raises(GroundTruthValidationError) as error:
        validate_ground_truth_document(path)
    assert invariant in str(error.value)


def test_rejects_unverified_item(tmp_path):
    """Impede que uma correção não confirmada entre no ground truth canônico."""
    document = _valid_document()
    document["items"][0]["verified"] = False

    _assert_invariant(_write_document(tmp_path, document), "unverified_item")


def test_rejects_null_expected_value(tmp_path):
    """Impede que uma correção canônica não tenha valor esperado."""
    document = _valid_document()
    document["items"][0]["expected_value"] = None

    _assert_invariant(_write_document(tmp_path, document), "null_expected_value")


def test_rejects_empty_check_property_for_pset_missing(tmp_path):
    """Impede pset_missing sem a propriedade que deve ser preenchida."""
    document = _valid_document()
    document["items"][0]["check_property"] = ""

    _assert_invariant(_write_document(tmp_path, document), "pset_missing_requires_check_property")


def test_rejects_duplicate_natural_key(tmp_path):
    """Impede duas correções para a mesma chave natural."""
    document = _valid_document()
    document["items"][1]["element_guid"] = "GUID_WALL_01"

    _assert_invariant(_write_document(tmp_path, document), "duplicate_natural_key")


def test_reports_each_duplicate_natural_key_with_its_entry_index(tmp_path):
    """Mantém cada colisão de chave natural localizável no erro agregado."""
    document = _valid_document()
    document["metadata"]["total_items"] = 3
    document["items"][1]["element_guid"] = "GUID_WALL_01"
    third_item = deepcopy(document["items"][0])
    third_item["issue_id"] = "issue-wall-03"
    document["items"].append(third_item)

    with pytest.raises(GroundTruthValidationError) as error:
        validate_ground_truth_document(_write_document(tmp_path, document))

    message = str(error.value)
    assert "duplicate_natural_key: items[1]" in message
    assert "duplicate_natural_key: items[2]" in message


def test_rejects_duplicate_issue_id(tmp_path):
    """Impede que o fallback por issue_id fique ambíguo."""
    document = _valid_document()
    document["items"][1]["issue_id"] = "issue-wall-01"

    _assert_invariant(_write_document(tmp_path, document), "duplicate_issue_id")


def test_rejects_item_and_skip_overlap(tmp_path):
    """Impede que a mesma issue seja avaliada e ignorada simultaneamente."""
    document = _valid_document()
    document["skipped"][0]["element_guid"] = "GUID_WALL_01"

    _assert_invariant(_write_document(tmp_path, document), "item_and_skip_overlap")


def test_rejects_declared_count_mismatch(tmp_path):
    """Impede metadados de contagem divergentes do conteúdo real."""
    document = _valid_document()
    document["metadata"]["total_items"] = 3

    _assert_invariant(_write_document(tmp_path, document), "declared_count_mismatch")


def test_accepts_empty_check_property_for_system_unclassified(tmp_path):
    """Permite a chave sem propriedade para classificações sem Pset."""
    document = _valid_document()
    document["items"][1]["issue_type"] = "system_unclassified"
    document["items"][1]["check_property"] = ""

    report = validate_ground_truth_document(_write_document(tmp_path, document))

    assert ("GUID_SPACE_01", "system_unclassified", "") in report.item_keys


def test_accepts_valid_document(tmp_path):
    """Aceita documento íntegro e mantém skips fora do loader de avaliação."""
    path = _write_document(tmp_path, deepcopy(_valid_document()))

    report = validate_ground_truth_document(path)
    ground_truth = GroundTruth.from_yaml(path)

    assert report.total_items == 2
    assert report.total_skipped == 1
    assert report.item_keys == {
        ("GUID_WALL_01", "pset_missing", "ThermalTransmittance"),
        ("GUID_SPACE_01", "pset_missing", "ThermalTransmittance"),
    }
    assert report.skipped_keys == {("GUID_SKIP_01", "pset_missing", "ThermalTransmittance")}
    assert len(ground_truth.items) == 2
    assert {item.issue_id for item in ground_truth.items} == {"issue-wall-01", "issue-space-01"}


# ---------------------------------------------------------------------------
# Valida\u00e7\u00e3o contra o diagn\u00f3stico e sem\u00e2ntica do protocolo
# ---------------------------------------------------------------------------


def _diagnostic_issue(
    issue_id: str,
    element_guid: str,
    issue_type: str,
    check_property: str = "",
    element_class: str = "IfcWall",
) -> Issue:
    """Cria uma issue real com a chave natural usada pelo diagn\u00f3stico."""
    context: dict[str, object] = {}
    if check_property:
        context["check_property"] = check_property
    return Issue(
        id=issue_id,
        element_guid=element_guid,
        element_class=element_class,
        issue_type=issue_type,  # type: ignore[arg-type]
        severity="medium",
        description="Issue sint\u00e9tica de diagn\u00f3stico",
        context=context,
    )


def _external_document() -> tuple[dict[str, Any], list[Issue]]:
    """Fixture literal com todos os ramos v\u00e1lidos do protocolo externo."""
    issues = [
        _diagnostic_issue("issue-thermal", "GUID_THERMAL", "pset_missing", "ThermalTransmittance"),
        _diagnostic_issue(
            "issue-category", "GUID_CATEGORY", "pset_missing", "Category", "IfcSpace"
        ),
        _diagnostic_issue("issue-system", "GUID_SYSTEM", "system_unclassified"),
        _diagnostic_issue("issue-fire", "GUID_FIRE", "pset_missing", "FireRating"),
    ]
    return (
        {
            "metadata": {"total_items": 3, "total_skipped": 1, "total_diagnostic_issues": 4},
            "items": [
                {
                    "element_guid": "GUID_THERMAL",
                    "issue_type": "pset_missing",
                    "check_property": "ThermalTransmittance",
                    "issue_id": "issue-thermal",
                    "expected_value": 2.5,
                    "accepted_alternatives": [3.0],
                    "notes": (
                        "Evid\u00eancia: c\u00e1lculo t\u00e9rmico do envolt\u00f3rio "
                        "em W/(m\u00b2\u00b7K)."
                    ),
                    "verified": True,
                },
                {
                    "element_guid": "GUID_CATEGORY",
                    "issue_type": "pset_missing",
                    "check_property": "Category",
                    "issue_id": "issue-category",
                    "expected_value": "BEDROOM",
                    "accepted_alternatives": ["OFFICE"],
                    "notes": "Decis\u00e3o: uso funcional registrado na planta arquitet\u00f4nica.",
                    "verified": True,
                },
                {
                    "element_guid": "GUID_SYSTEM",
                    "issue_type": "system_unclassified",
                    "check_property": "",
                    "issue_id": "issue-system",
                    "expected_value": "Concreto armado moldado in loco",
                    "accepted_alternatives": ["Concreto pr\u00e9-moldado"],
                    "notes": "Evid\u00eancia: especifica\u00e7\u00e3o estrutural da parede.",
                    "verified": True,
                },
            ],
            "skipped": [
                {
                    "element_guid": "GUID_FIRE",
                    "issue_type": "pset_missing",
                    "check_property": "FireRating",
                    "issue_id": "issue-fire",
                    "reason": (
                        "Sem documenta\u00e7\u00e3o t\u00e9cnica suficiente para "
                        "definir a resist\u00eancia."
                    ),
                }
            ],
        },
        issues,
    )


def _write_external_document(tmp_path, document: dict[str, Any]):
    """Escreve entradas e congela hashes com hashlib, independente do validador."""
    ifc_path = tmp_path / "input.ifc"
    ids_path = tmp_path / "requirements.ids"
    ifc_path.write_bytes(b"IFC synthetic input")
    ids_path.write_bytes(b"IDS synthetic input")
    document["metadata"].setdefault(
        "input_ifc_sha256", hashlib.sha256(ifc_path.read_bytes()).hexdigest().upper()
    )
    document["metadata"].setdefault(
        "ids_sha256", hashlib.sha256(ids_path.read_bytes()).hexdigest().upper()
    )
    return _write_document(tmp_path, document), ifc_path, ids_path


def _assert_external_invariant(
    tmp_path, document: dict[str, Any], issues: list[Issue], invariant: str
) -> None:
    path, ifc_path, ids_path = _write_external_document(tmp_path, document)
    with pytest.raises(GroundTruthValidationError) as error:
        validate_ground_truth_against_issues(path, issues, ifc_path=ifc_path, ids_path=ids_path)
    assert invariant in str(error.value)


def test_rejects_item_without_matching_diagnostic_issue(tmp_path):
    """Impede item que inventa uma chave natural ausente no diagn\u00f3stico."""
    document, issues = _external_document()
    document["items"][0]["element_guid"] = "GUID_UNKNOWN"

    _assert_external_invariant(tmp_path, document, issues, "entry_without_diagnostic_issue")


def test_rejects_ifc_hash_mismatch(tmp_path):
    """Impede usar GT curado para outro arquivo IFC."""
    document, issues = _external_document()
    document["metadata"]["input_ifc_sha256"] = "0" * 64

    _assert_external_invariant(tmp_path, document, issues, "input_ifc_sha256_mismatch")


def test_rejects_ids_hash_mismatch(tmp_path):
    """Impede misturar GT e especifica\u00e7\u00e3o IDS de execu\u00e7\u00e3o diferente."""
    document, issues = _external_document()
    document["metadata"]["ids_sha256"] = "0" * 64

    _assert_external_invariant(tmp_path, document, issues, "ids_sha256_mismatch")


def test_rejects_missing_diagnostic_issue(tmp_path):
    """Impede cobertura parcial quando uma issue n\u00e3o entra nem em item nem skip."""
    document, issues = _external_document()
    document["metadata"]["total_skipped"] = 0
    document["skipped"] = []

    _assert_external_invariant(tmp_path, document, issues, "missing_diagnostic_issue")


def test_rejects_stale_issue_id(tmp_path):
    """Impede que uma chave correta aponte para id de issue desatualizado."""
    document, issues = _external_document()
    document["items"][0]["issue_id"] = "stale-id"

    _assert_external_invariant(tmp_path, document, issues, "stale_issue_id")


def test_rejects_blank_notes(tmp_path):
    """Exige evid\u00eancia ou decis\u00e3o humana para cada valor can\u00f4nico."""
    document, issues = _external_document()
    document["items"][0]["notes"] = "   "

    _assert_external_invariant(tmp_path, document, issues, "blank_notes")


@pytest.mark.parametrize(
    ("issue_type", "check_property", "element_class", "value"),
    [
        ("pset_missing", "ThermalTransmittance", "IfcWall", 2.5),
        ("pset_missing", "LoadBearing", "IfcWall", True),
        ("pset_missing", "IsLoadBearing", "IfcSlab", False),
        ("pset_missing", "Category", "IfcSpace", "KITCHEN"),
        ("pset_missing", "FireRating", "IfcWall", "REI 120"),
        ("system_unclassified", "", "IfcSlab", "Piso vin\u00edlico / laminado"),
        ("system_unclassified", "", "IfcWall", "Drywall / Steel frame"),
    ],
)
def test_accepts_semantic_values_for_expected_value_and_alternatives(
    tmp_path, issue_type, check_property, element_class, value
):
    """Aceita os tipos e vocabul\u00e1rios previstos tanto no principal quanto nas alternativas."""
    issue = _diagnostic_issue(
        "issue-semantic", "GUID_SEMANTIC", issue_type, check_property, element_class
    )
    document = {
        "metadata": {"total_items": 1, "total_skipped": 0, "total_diagnostic_issues": 1},
        "items": [
            {
                "element_guid": "GUID_SEMANTIC",
                "issue_type": issue_type,
                "check_property": check_property,
                "issue_id": "issue-semantic",
                "expected_value": value,
                "accepted_alternatives": [value],
                "notes": (
                    "Evid\u00eancia e decis\u00e3o humana documentadas em W/(m\u00b2\u00b7K)."
                    if check_property == "ThermalTransmittance"
                    else "Evid\u00eancia e decis\u00e3o humana documentadas."
                ),
                "verified": True,
            }
        ],
        "skipped": [],
    }
    path, ifc_path, ids_path = _write_external_document(tmp_path, document)

    report = validate_ground_truth_against_issues(
        path, [issue], ifc_path=ifc_path, ids_path=ids_path
    )

    assert report.item_keys == {("GUID_SEMANTIC", issue_type, check_property)}


@pytest.mark.parametrize(
    ("issue_type", "check_property", "element_class", "invalid_value", "invariant"),
    [
        ("pset_missing", "ThermalTransmittance", "IfcWall", True, "invalid_thermal_transmittance"),
        ("pset_missing", "ThermalTransmittance", "IfcWall", 0, "invalid_thermal_transmittance"),
        ("pset_missing", "LoadBearing", "IfcWall", "true", "invalid_boolean_value"),
        ("pset_missing", "IsLoadBearing", "IfcSlab", 1, "invalid_boolean_value"),
        ("pset_missing", "Category", "IfcSpace", "HALL", "invalid_category_value"),
        ("pset_missing", "FireRating", "IfcWall", "REI120", "invalid_fire_rating"),
        ("system_unclassified", "", "IfcSlab", "Estrutura met\u00e1lica", "invalid_system_value"),
        (
            "system_unclassified",
            "",
            "IfcWall",
            "Laje maci\u00e7a de concreto armado",
            "invalid_system_value",
        ),
    ],
)
def test_rejects_invalid_semantic_alternative(
    tmp_path, issue_type, check_property, element_class, invalid_value, invariant
):
    """Protege alternativas contra o mesmo valor semanticamente inv\u00e1lido do principal."""
    issue = _diagnostic_issue(
        "issue-semantic", "GUID_SEMANTIC", issue_type, check_property, element_class
    )
    valid_value = "Concreto armado moldado in loco" if issue_type == "system_unclassified" else 2.5
    if check_property in {"LoadBearing", "IsLoadBearing"}:
        valid_value = True
    elif check_property == "Category":
        valid_value = "BEDROOM"
    elif check_property == "FireRating":
        valid_value = "REI 60"
    document = {
        "metadata": {"total_items": 1, "total_skipped": 0, "total_diagnostic_issues": 1},
        "items": [
            {
                "element_guid": "GUID_SEMANTIC",
                "issue_type": issue_type,
                "check_property": check_property,
                "issue_id": "issue-semantic",
                "expected_value": valid_value,
                "accepted_alternatives": [invalid_value],
                "notes": "Evid\u00eancia e decis\u00e3o humana documentadas.",
                "verified": True,
            }
        ],
        "skipped": [],
    }

    _assert_external_invariant(tmp_path, document, [issue], invariant)


def test_rejects_system_issue_with_property_and_skip_without_reason(tmp_path):
    """Exige chave vazia para sistema e justificativa concreta para qualquer skip."""
    document, issues = _external_document()
    document["items"][2]["check_property"] = "System"
    document["skipped"][0]["reason"] = ""

    path, ifc_path, ids_path = _write_external_document(tmp_path, document)
    with pytest.raises(GroundTruthValidationError) as error:
        validate_ground_truth_against_issues(path, issues, ifc_path=ifc_path, ids_path=ids_path)

    message = str(error.value)
    assert "system_unclassified_requires_empty_check_property" in message
    assert "blank_skip_reason" in message


def test_rejects_skipped_system_issue_with_property(tmp_path):
    """Exige propriedade vazia tamb\u00e9m quando a issue de sistema \u00e9 pulada."""
    issue = _diagnostic_issue("issue-system", "GUID_SYSTEM", "system_unclassified")
    document = {
        "metadata": {"total_items": 0, "total_skipped": 1, "total_diagnostic_issues": 1},
        "items": [],
        "skipped": [
            {
                "element_guid": "GUID_SYSTEM",
                "issue_type": "system_unclassified",
                "check_property": "System",
                "issue_id": "issue-system",
                "reason": "Classifica\u00e7\u00e3o indispon\u00edvel para a revis\u00e3o.",
            }
        ],
    }

    _assert_external_invariant(
        tmp_path, document, [issue], "system_unclassified_requires_empty_check_property"
    )


def test_rejects_item_with_unsupported_property(tmp_path):
    """Impede ampliar silenciosamente o protocolo para propriedades sem regra sem\u00e2ntica."""
    issue = _diagnostic_issue("issue-other", "GUID_OTHER", "pset_missing", "IsExternal")
    document = {
        "metadata": {"total_items": 1, "total_skipped": 0, "total_diagnostic_issues": 1},
        "items": [
            {
                "element_guid": "GUID_OTHER",
                "issue_type": "pset_missing",
                "check_property": "IsExternal",
                "issue_id": "issue-other",
                "expected_value": True,
                "notes": "Evid\u00eancia da propriedade n\u00e3o suportada.",
                "verified": True,
            }
        ],
        "skipped": [],
    }

    _assert_external_invariant(tmp_path, document, [issue], "unsupported_item_property")


def test_accepts_matching_issues_and_hashes(tmp_path):
    """Aceita cobertura completa de diagn\u00f3stico com hashes congelados e valores curados."""
    document, issues = _external_document()
    path, ifc_path, ids_path = _write_external_document(tmp_path, document)

    report = validate_ground_truth_against_issues(
        path, issues, ifc_path=ifc_path, ids_path=ids_path
    )

    assert report.total_items == 3
    assert report.total_skipped == 1


def test_accepts_system_issue_with_none_check_property(tmp_path):
    """Casa a chave vazia do YAML quando o diagnóstico representa a propriedade como None."""
    document, issues = _external_document()
    issues[2].context["check_property"] = None
    path, ifc_path, ids_path = _write_external_document(tmp_path, document)

    report = validate_ground_truth_against_issues(
        path, issues, ifc_path=ifc_path, ids_path=ids_path
    )

    assert ("GUID_SYSTEM", "system_unclassified", "") in report.item_keys
