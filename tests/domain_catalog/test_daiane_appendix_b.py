"""Contrato e transcrição auditável do Apêndice B de Daiane (E4, M1-04).

Os testes negativos usam inventários SINTÉTICOS mínimos gravados em ``tmp_path``
(``synthetic_inventory``); nada deles vem da dissertação. Os testes da transcrição
real leem ``data/catalogs/sources/daiane-2025/appendix-b-v1.json`` e conferem os
denominadores contados na conferência visual das páginas PDF 172–186 (registrada no
próprio arquivo), não os 133 requisitos do IDS de 2026, que é outra fonte.
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from src.domain_catalog.canonical import canonical_json_text
from src.domain_catalog.importers.daiane_b import (
    APPENDIX_B_PATH,
    AppendixBFormatError,
    appendix_b_check_level,
    appendix_b_totals,
    load_appendix_b,
)
from src.domain_catalog.models import SourceAssertion
from src.domain_catalog.profile_models import AppendixBInventory

PDF_SHA256 = "82ead7b5f06fd06247f9f057727bab071ab1c08de4fe42412bebeb9e0c06877a"
OTHER_SHA256 = "0" * 64
SPECS = tuple(f"E{n:02d}" for n in range(1, 11))


def _record(
    record_id: str, spec: str | None, order: int, page: int, **changes: Any
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": record_id,
        "specification": spec,
        "role": "requirement",
        "locator": {
            "pdf_pages": [page],
            "printed_pages": [page - 1],
            "block": "requirements",
            "block_kind": "item",
            "order": order,
            "source_lines": 1,
        },
        "text_literal": "TER atributo SYN_Nome",
        "structured_json": canonical_json_text(
            {
                "attribute_name_literal": "SYN_Nome",
                "facet_literal": "atributo",
                "modality_literal": "TER",
                "parse_status": "parsed",
            }
        ),
        "facet_literal": "atributo",
        "category": "attribute",
        "transcription_state": "transcribed",
        "transcription_status": "registered",
        "doubts": [],
        "not_projectable_reason": None,
        "continuation_of": None,
    }
    data.update(changes)
    return data


def synthetic_inventory() -> dict[str, Any]:
    """Dez especificações sintéticas, uma por página, com um requisito e uma aplicabilidade."""
    records: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    for index, spec in enumerate(SPECS):
        page = 173 + index
        applicability = _record(
            f"dai2025:B-{spec}-0001",
            spec,
            1,
            page,
            role="applicability",
            locator={
                "pdf_pages": [page],
                "printed_pages": [page - 1],
                "block": "applicability",
                "block_kind": "item",
                "order": 1,
                "source_lines": 1,
            },
            text_literal="classe IFC IFCSYNTHETIC",
            structured_json=canonical_json_text(
                {
                    "entity_literal": "IFCSYNTHETIC",
                    "facet_literal": "classe IFC",
                    "parse_status": "parsed",
                }
            ),
            facet_literal="classe IFC",
            category="entity",
        )
        requirement = _record(f"dai2025:B-{spec}-0002", spec, 2, page)
        records.extend([applicability, requirement])
        pages.append(
            {
                "pdf_page": page,
                "printed_page": page - 1,
                "report_page": f"{index + 2}/15",
                "furniture": [],
                "record_ids": [applicability["id"], requirement["id"]],
            }
        )
    for page in (172, *range(183, 187)):
        pages.append(
            {
                "pdf_page": page,
                "printed_page": page - 1,
                "report_page": None,
                "furniture": [],
                "record_ids": [],
            }
        )
    pages.sort(key=lambda item: item["pdf_page"])
    return {
        "format": "ifcqc-daiane-b-transcription-1",
        "format_version": 1,
        "revision": "synthetic-r1",
        "content_origin": "synthetic_fixture",
        "source": {
            "artifact_id": "dai2025:dissertacao",
            "pdf_sha256": PDF_SHA256,
            "pdf_size_bytes": 11380259,
            "pdf_pages": [172, 186],
            "printed_pages": [171, 185],
            "excluded_pages": [{"pdf_page": 187, "reason": "sintético: página fora do relatório"}],
        },
        "method": "inventário sintético de teste; nenhum literal real",
        "reviews": [],
        "specifications": [
            {"code": spec, "title_literal": f"{spec} - IfcSynthetic", "pdf_pages": [173 + i]}
            for i, spec in enumerate(SPECS)
        ],
        "pages": pages,
        "records": records,
        "changes": [],
    }


def _write(tmp_path: Path, document: dict[str, Any], name: str = "b.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path


def _load(tmp_path: Path, document: dict[str, Any]) -> AppendixBInventory:
    return load_appendix_b(_write(tmp_path, document), expected_pdf_sha256=PDF_SHA256)


def test_synthetic_inventory_loads_and_projects_representable_records(tmp_path: Path) -> None:
    inventory = _load(tmp_path, synthetic_inventory())

    assert len(inventory.records) == 20
    projected = [record.assertion for record in inventory.records if record.assertion]
    assert len(projected) == 20
    assert all(isinstance(item, SourceAssertion) for item in projected)


def test_pdf_hash_other_than_expected_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path, synthetic_inventory())

    with pytest.raises(AppendixBFormatError, match="pdf_sha256"):
        load_appendix_b(path, expected_pdf_sha256=OTHER_SHA256)


def test_declared_pdf_hash_other_than_expected_is_refused(tmp_path: Path) -> None:
    document = synthetic_inventory()
    document["source"]["pdf_sha256"] = OTHER_SHA256

    with pytest.raises(AppendixBFormatError, match="pdf_sha256"):
        _load(tmp_path, document)


def test_duplicate_record_id_is_refused(tmp_path: Path) -> None:
    document = synthetic_inventory()
    clone = copy.deepcopy(document["records"][1])
    document["records"].append(clone)

    with pytest.raises(AppendixBFormatError, match="duplicado"):
        _load(tmp_path, document)


def test_duplicate_json_key_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "dup.json"
    path.write_text('{"format": "a", "format": "b"}', encoding="utf-8")

    with pytest.raises(AppendixBFormatError, match="duplicada"):
        load_appendix_b(path, expected_pdf_sha256=PDF_SHA256)


def test_page_outside_appendix_b_is_refused(tmp_path: Path) -> None:
    document = synthetic_inventory()
    document["records"][0]["locator"]["pdf_pages"] = [188]
    document["records"][0]["locator"]["printed_pages"] = [187]

    with pytest.raises(AppendixBFormatError, match="fora do Apêndice B"):
        _load(tmp_path, document)


def test_record_without_location_is_refused(tmp_path: Path) -> None:
    document = synthetic_inventory()
    del document["records"][0]["locator"]

    with pytest.raises(AppendixBFormatError, match="locator"):
        _load(tmp_path, document)


def test_record_with_empty_page_list_is_refused(tmp_path: Path) -> None:
    document = synthetic_inventory()
    document["records"][0]["locator"]["pdf_pages"] = []
    document["records"][0]["locator"]["printed_pages"] = []

    with pytest.raises(AppendixBFormatError, match="pdf_pages"):
        _load(tmp_path, document)


def test_record_missing_from_its_page_inventory_is_refused(tmp_path: Path) -> None:
    document = synthetic_inventory()
    document["pages"][1]["record_ids"] = document["pages"][1]["record_ids"][:1]

    with pytest.raises(AppendixBFormatError, match="inventário da página"):
        _load(tmp_path, document)


def test_missing_specification_is_refused(tmp_path: Path) -> None:
    document = synthetic_inventory()
    document["specifications"] = [s for s in document["specifications"] if s["code"] != "E05"]

    with pytest.raises(AppendixBFormatError, match="E05"):
        _load(tmp_path, document)


def test_record_of_undeclared_specification_is_refused(tmp_path: Path) -> None:
    document = synthetic_inventory()
    document["records"][0]["specification"] = "E10"

    with pytest.raises(AppendixBFormatError, match="prefixo"):
        _load(tmp_path, document)


def test_unclassifiable_text_is_preserved_without_projection(tmp_path: Path) -> None:
    document = synthetic_inventory()
    document["records"][1].update(
        role="unclassified",
        text_literal="Texto solto que não é requisito reconhecível",
        structured_json=canonical_json_text({"parse_status": "unparsed"}),
        facet_literal=None,
        category=None,
        transcription_state="transcribed_with_doubt",
        doubts=["linha sem modalidade/faceta reconhecível"],
        not_projectable_reason="texto não classificável; preservado sem projeção",
    )

    inventory = _load(tmp_path, document)
    record = inventory.record("dai2025:B-E01-0002")

    assert record.assertion is None
    assert record.text_literal == "Texto solto que não é requisito reconhecível"
    assert appendix_b_totals(inventory).by_role["unclassified"] == 1


def test_record_without_category_requires_reason(tmp_path: Path) -> None:
    document = synthetic_inventory()
    document["records"][1]["category"] = None

    with pytest.raises(AppendixBFormatError, match="not_projectable_reason"):
        _load(tmp_path, document)


def test_absent_modality_stays_distinct_from_printed_zero(tmp_path: Path) -> None:
    document = synthetic_inventory()
    without = {
        "attribute_name_literal": "SYN_A",
        "facet_literal": "atributo",
        "parse_status": "partial",
    }
    with_zero = {**without, "modality_literal": "0"}
    document["records"][1]["structured_json"] = canonical_json_text(without)
    document["records"][3]["structured_json"] = canonical_json_text(with_zero)

    inventory = _load(tmp_path, document)
    totals = appendix_b_totals(inventory)

    assert (
        json.loads(inventory.record("dai2025:B-E01-0002").structured_json).get("modality_literal")
        is None
    )
    assert "modality_literal" not in json.loads(
        inventory.record("dai2025:B-E01-0002").structured_json
    )
    assert totals.by_modality["nao_impressa"] == 1
    assert totals.by_modality["0"] == 1


def test_continuation_is_not_counted_twice(tmp_path: Path) -> None:
    document = synthetic_inventory()
    continuation = _record(
        "dai2025:B-E01-0003",
        "E01",
        3,
        174,
        text_literal="continuação do requisito na página seguinte",
        continuation_of="dai2025:B-E01-0002",
        category=None,
        not_projectable_reason="continuação: o registro principal já é projetado",
    )
    document["records"].append(continuation)
    document["pages"][2]["record_ids"].append(continuation["id"])
    document["specifications"][0]["pdf_pages"] = [173, 174]

    inventory = _load(tmp_path, document)
    totals = appendix_b_totals(inventory)

    assert totals.records == 21
    assert totals.continuations == 1
    assert totals.by_role["requirement"] == 10
    assert inventory.record(continuation["id"]).assertion is None


def test_continuation_of_other_specification_is_refused(tmp_path: Path) -> None:
    document = synthetic_inventory()
    continuation = _record(
        "dai2025:B-E02-0003",
        "E02",
        3,
        174,
        continuation_of="dai2025:B-E01-0002",
        category=None,
        not_projectable_reason="continuação",
    )
    document["records"].append(continuation)
    document["pages"][2]["record_ids"].append(continuation["id"])

    with pytest.raises(AppendixBFormatError, match="continuação"):
        _load(tmp_path, document)


def test_research_check_requires_both_recorded_checks(tmp_path: Path) -> None:
    document = synthetic_inventory()
    document["records"][1]["transcription_status"] = "checked_by_research"

    with pytest.raises(AppendixBFormatError, match="checked_by_research"):
        _load(tmp_path, document)


def test_curator_check_is_never_accepted_from_an_assistant_review(tmp_path: Path) -> None:
    document = synthetic_inventory()
    document["reviews"] = [
        {
            "review_id": "curadoria-falsa",
            "kind": "curator_check",
            "reviewer_kind": "assistant",
            "reviewer_label": "assistente",
            "date": "2026-10-22",
            "pdf_pages": [172, 186],
            "outcome": "no_divergence",
            "notes": "tentativa de autoaprovação",
        }
    ]
    document["records"][1]["transcription_status"] = "checked_by_curator"

    with pytest.raises(AppendixBFormatError, match="curator"):
        _load(tmp_path, document)


def test_boolean_format_version_is_refused(tmp_path: Path) -> None:
    document = synthetic_inventory()
    document["format_version"] = True

    with pytest.raises(AppendixBFormatError, match="format_version"):
        _load(tmp_path, document)


def test_unknown_field_is_refused(tmp_path: Path) -> None:
    document = synthetic_inventory()
    document["records"][0]["inferred_cardinality"] = "required"

    with pytest.raises(AppendixBFormatError, match="inferred_cardinality"):
        _load(tmp_path, document)


def test_non_canonical_structured_literal_is_refused(tmp_path: Path) -> None:
    document = synthetic_inventory()
    document["records"][1]["structured_json"] = '{"parse_status": "parsed"}'

    with pytest.raises(AppendixBFormatError, match="canônico"):
        _load(tmp_path, document)


# --- Transcrição real -----------------------------------------------------------------


@pytest.fixture(scope="module")
def real() -> AppendixBInventory:
    return load_appendix_b(APPENDIX_B_PATH, expected_pdf_sha256=PDF_SHA256)


@pytest.mark.external_data
def test_real_transcription_covers_every_specification_and_page(real: AppendixBInventory) -> None:
    assert tuple(spec.code for spec in real.specifications) == SPECS
    assert tuple(page.pdf_page for page in real.pages) == tuple(range(172, 187))
    assert tuple(page.printed_page for page in real.pages) == tuple(range(171, 186))
    assert tuple(page.report_page for page in real.pages) == tuple(f"{n}/15" for n in range(1, 16))
    assert real.source.excluded_pages[0].pdf_page == 187


@pytest.mark.external_data
def test_real_transcription_denominators_come_from_the_visual_count(
    real: AppendixBInventory,
) -> None:
    # Contagem visual por página (conferência registrada em ``reviews``), não o IDS de 2026.
    totals = appendix_b_totals(real)
    requirements = {
        "E01": 22,
        "E02": 28,
        "E03": 24,
        "E04": 20,
        "E05": 17,
        "E06": 22,
        "E07": 16,
        "E08": 14,
        "E09": 15,
        "E10": 6,
    }

    assert {
        spec: totals.by_specification_role[spec]["requirement"] for spec in SPECS
    } == requirements
    assert {
        spec: totals.by_specification_role[spec]["applicability"] for spec in SPECS
    } == dict.fromkeys(SPECS, 1)
    assert totals.by_role["requirement"] == 184 != 133
    assert totals.continuations == 0


@pytest.mark.external_data
def test_real_property_requirements_stay_unprojected_without_category(
    real: AppendixBInventory,
) -> None:
    properties = [record for record in real.records if record.facet_literal == "propriedades"]
    assert properties
    assert all(record.category is None and record.assertion is None for record in properties)
    assert all(record.not_projectable_reason for record in properties)


@pytest.mark.external_data
def test_real_prohibition_keeps_its_modality_in_the_assertion(real: AppendixBInventory) -> None:
    record = real.record("dai2025:B-E01-0012")
    assert record.assertion is not None
    domain = record.assertion.domain_literal

    assert record.assertion.category == "attribute"
    assert record.assertion.target_literal == "PartitioningType"
    assert domain["modality_literal"] == "NÃO TER"
    assert domain["value_literal"] == "NOTDEFINED"


@pytest.mark.external_data
def test_real_transcription_has_no_curator_check(real: AppendixBInventory) -> None:
    assert all(record.transcription_status != "checked_by_curator" for record in real.records)
    assert all(review.kind != "curator_check" for review in real.reviews)


@pytest.mark.external_data
def test_real_cover_contact_is_redacted_explicitly(real: AppendixBInventory) -> None:
    redacted = [record for record in real.records if record.transcription_state == "redacted"]

    assert len(redacted) == 1
    assert "@" not in redacted[0].text_literal
    assert redacted[0].doubts


@pytest.mark.external_data
def test_real_transcription_records_both_checks_and_its_corrections(
    real: AppendixBInventory,
) -> None:
    kinds = {review.kind: review.outcome for review in real.reviews}

    assert kinds == {
        "assisted_extraction": "completed",
        "visual_check": "divergences_resolved",
        "independent_second_check": "divergences_resolved",
    }
    assert all(review.reviewer_kind == "assistant" for review in real.reviews)
    assert {record.transcription_status for record in real.records} == {"checked_by_research"}
    corrected = {record_id for change in real.changes for record_id in change.record_ids}
    assert real.revision == "2026-10-22-r2"
    assert {"dai2025:B-E07-0007", "dai2025:B-E07-0017", "dai2025:B-E03-0005"} <= corrected
    assert "system_and_code_literal" in real.record("dai2025:B-E07-0007").structured
    assert "system_literal" not in real.record("dai2025:B-E07-0007").structured


# --- Retomada 23/10: alvo, alterações, páginas e conferências (M15–M18) -----------------


def test_categorized_record_without_printed_target_is_refused(tmp_path: Path) -> None:
    """M15: sem alvo impresso, a assertiva não recebe o literal ``"None"``."""
    document = synthetic_inventory()
    record = document["records"][1]
    record["structured_json"] = canonical_json_text(
        {"modality_literal": "TER", "parse_status": "parsed"}
    )
    record["facet_literal"] = None

    with pytest.raises(AppendixBFormatError, match="alvo"):
        _load(tmp_path, document)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"revision": "synthetic-r1", "record_ids": ["dai2025:B-E01-0099"]}, "inexistente"),
        ({"revision": "synthetic-r9", "record_ids": ["dai2025:B-E01-0002"]}, "revisão"),
        (
            {"revision": "synthetic-r1", "record_ids": ["dai2025:B-E01-0002"] * 2},
            "repetido",
        ),
    ],
)
def test_transcription_change_must_cite_existing_records_and_known_revision(
    tmp_path: Path, change: dict[str, Any], message: str
) -> None:
    """M16: alteração cita registros existentes e revisão não posterior à do inventário."""
    document = synthetic_inventory()
    document["changes"] = [{**change, "description": "correção sintética"}]

    with pytest.raises(AppendixBFormatError, match=message):
        _load(tmp_path, document)


def test_transcription_change_of_an_earlier_revision_is_kept(tmp_path: Path) -> None:
    document = synthetic_inventory()
    document["revision"] = "2026-10-23-r3"
    document["changes"] = [
        {
            "revision": "2026-10-22-r2",
            "record_ids": ["dai2025:B-E01-0002"],
            "description": "correção da revisão anterior",
        },
        {
            "revision": "2026-10-23-r3",
            "record_ids": ["dai2025:B-E02-0002"],
            "description": "correção desta revisão",
        },
    ]

    assert len(_load(tmp_path, document).changes) == 2


def test_later_dated_revision_change_is_refused(tmp_path: Path) -> None:
    document = synthetic_inventory()
    document["revision"] = "2026-10-22-r2"
    document["changes"] = [
        {
            "revision": "2026-10-22-r10",
            "record_ids": ["dai2025:B-E01-0002"],
            "description": "revisão posterior à do inventário",
        }
    ]

    with pytest.raises(AppendixBFormatError, match="revisão"):
        _load(tmp_path, document)


@pytest.mark.parametrize("pages", [[174], [173, 174]])
def test_specification_pages_must_match_its_records(tmp_path: Path, pages: list[int]) -> None:
    """M17: páginas da especificação conferidas contra as páginas dos seus registros."""
    document = synthetic_inventory()
    document["specifications"][0]["pdf_pages"] = pages

    with pytest.raises(AppendixBFormatError, match="especificação"):
        _load(tmp_path, document)


def _checks(visual_label: str, second_label: str) -> list[dict[str, Any]]:
    base = {
        "reviewer_kind": "assistant",
        "date": "2026-10-22",
        "pdf_pages": [172, 186],
        "outcome": "no_divergence",
        "notes": "conferência sintética",
    }
    return [
        {**base, "review_id": "visual", "kind": "visual_check", "reviewer_label": visual_label},
        {
            **base,
            "review_id": "segunda",
            "kind": "independent_second_check",
            "reviewer_label": second_label,
        },
    ]


def test_second_check_by_the_same_declared_reviewer_is_not_independent(tmp_path: Path) -> None:
    """M18: o mesmo revisor declarado (módulo caixa/espaços) não cumpre as duas conferências."""
    document = synthetic_inventory()
    document["reviews"] = _checks("Sessão  A", " sessão a")
    document["records"][1]["transcription_status"] = "checked_by_research"

    with pytest.raises(AppendixBFormatError, match="mesmo revisor"):
        _load(tmp_path, document)


def test_distinct_declared_reviewers_satisfy_the_research_check(tmp_path: Path) -> None:
    document = synthetic_inventory()
    document["reviews"] = _checks("sessão A", "subagente B")
    for record in document["records"]:
        record["transcription_status"] = "checked_by_research"
    inventory = _load(tmp_path, document)

    assert appendix_b_check_level(inventory) == "assistant_only"


@pytest.mark.parametrize(
    ("kinds", "status", "level"),
    [
        (("assistant", "assistant"), "registered", "not_checked"),
        (("assistant", "assistant"), "checked_by_research", "assistant_only"),
        (("assistant", "human"), "checked_by_research", "includes_human"),
    ],
)
def test_check_level_is_explicit(
    tmp_path: Path, kinds: tuple[str, str], status: str, level: str
) -> None:
    document = synthetic_inventory()
    document["reviews"] = _checks("sessão A", "pessoa B")
    for review, kind in zip(document["reviews"], kinds, strict=True):
        review["reviewer_kind"] = kind
    for record in document["records"]:
        record["transcription_status"] = status

    assert appendix_b_check_level(_load(tmp_path, document)) == level


@pytest.mark.external_data
def test_real_transcription_check_level_is_assistant_only(real: AppendixBInventory) -> None:
    assert appendix_b_check_level(real) == "assistant_only"


def test_partial_page_human_review_does_not_raise_the_check_level(tmp_path: Path) -> None:
    """Menor 2: só conferências sobre todo o apêndice, aprovadas, contam para o nível."""
    document = synthetic_inventory()
    document["reviews"] = [
        *_checks("sessão A", "subagente B"),
        {
            "review_id": "humana-parcial",
            "kind": "visual_check",
            "reviewer_kind": "human",
            "reviewer_label": "pessoa C",
            "date": "2026-10-23",
            "pdf_pages": [173, 173],
            "outcome": "no_divergence",
            "notes": "uma página só",
        },
    ]
    for record in document["records"]:
        record["transcription_status"] = "checked_by_research"

    assert appendix_b_check_level(_load(tmp_path, document)) == "assistant_only"


def test_curator_level_requires_every_record_checked_by_a_human_curator(tmp_path: Path) -> None:
    document = synthetic_inventory()
    document["reviews"] = [
        {
            "review_id": "curadoria",
            "kind": "curator_check",
            "reviewer_kind": "human",
            "reviewer_label": "curador",
            "date": "2026-10-23",
            "pdf_pages": [172, 186],
            "outcome": "no_divergence",
            "notes": "curadoria sintética",
        }
    ]
    for record in document["records"]:
        record["transcription_status"] = "checked_by_curator"

    assert appendix_b_check_level(_load(tmp_path, document)) == "curator"
