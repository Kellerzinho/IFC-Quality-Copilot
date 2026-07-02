"""Testes do extrator de ground truth por diff (Fase C.2, passo 3).

O modelo "enriquecido" é produzido pelas próprias operações do IFCWriter,
garantindo simetria entre onde o pipeline escreve e onde o extractor lê.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.experiment.evaluator import GroundTruth
from src.experiment.gt_extractor import (
    GTExtractionResult,
    extract_ground_truth,
    extract_value_for_issue,
    write_ground_truth_yaml,
)
from src.models import Issue
from src.writer.ifc_writer import IFCWriter


def _make_issue(
    guid: str,
    issue_type: str = "pset_missing",
    element_class: str = "IfcWall",
    element_name: str | None = None,
    context: dict | None = None,
) -> Issue:
    return Issue(
        element_guid=guid,
        element_class=element_class,
        element_name=element_name,
        issue_type=issue_type,  # type: ignore[arg-type]
        severity="medium",
        description="issue de teste",
        context=context or {},
    )


def _pset_issue(guid: str, check_property: str = "ThermalTransmittance") -> Issue:
    return _make_issue(
        guid,
        context={"check_pset": "Pset_WallCommon", "check_property": check_property},
    )


# ---------------------------------------------------------------------------
# pset_missing
# ---------------------------------------------------------------------------


class TestPsetExtraction:
    def test_pset_value_extracted_from_enriched_model(self, ifc_with_walls):
        """Valor preenchido pelo IFCWriter no pset esperado é extraído."""
        f, meta = ifc_with_walls
        writer = IFCWriter(f)
        writer.preencher_pset(
            meta["wall1_guid"], "Pset_WallCommon", {"ThermalTransmittance": 2.5}
        )

        value, note, skip = extract_value_for_issue(f, _pset_issue(meta["wall1_guid"]))

        assert skip is None
        assert note is None
        assert value == pytest.approx(2.5)

    def test_pset_value_found_in_other_pset_gets_note(self, ifc_with_walls):
        """Propriedade preenchida em pset diferente do esperado gera nota de fallback."""
        f, meta = ifc_with_walls
        writer = IFCWriter(f)
        writer.preencher_pset(
            meta["wall3_guid"], "Pset_Custom", {"ThermalTransmittance": 1.8}
        )

        value, note, skip = extract_value_for_issue(f, _pset_issue(meta["wall3_guid"]))

        assert skip is None
        assert value == pytest.approx(1.8)
        assert note is not None
        assert "Pset_Custom" in note

    def test_pset_value_missing_in_gt_is_skipped(self, ifc_with_walls):
        """Propriedade não enriquecida no GT vira skip com motivo, nunca valor inventado."""
        f, meta = ifc_with_walls

        value, _, skip = extract_value_for_issue(f, _pset_issue(meta["wall1_guid"]))

        assert value is None
        assert skip is not None
        assert "não enriquecida" in skip

    def test_boolean_property_preserved(self, ifc_with_walls):
        """Booleanos extraídos permanecem bool (IsExternal=True da fixture)."""
        f, meta = ifc_with_walls
        issue = _pset_issue(meta["wall1_guid"], check_property="IsExternal")

        value, _, skip = extract_value_for_issue(f, issue)

        assert skip is None
        assert value is True


# ---------------------------------------------------------------------------
# space_unnamed
# ---------------------------------------------------------------------------


class TestSpaceNameExtraction:
    def test_renamed_space_long_name_is_extracted(self, ifc_with_spaces):
        """LongName renomeado pelo IFCWriter é o valor de GT."""
        f, meta = ifc_with_spaces
        writer = IFCWriter(f)
        writer.renomear_espaco(meta["space1_guid"], "Lavabo Suíte")
        issue = _make_issue(
            meta["space1_guid"],
            issue_type="space_unnamed",
            element_class="IfcSpace",
            element_name="Room 1",
        )

        value, _, skip = extract_value_for_issue(f, issue)

        assert skip is None
        assert value == "Lavabo Suíte"

    def test_space_not_enriched_is_skipped(self, ifc_with_spaces):
        """Nome no GT igual ao genérico da v1 conta como não enriquecido."""
        f, meta = ifc_with_spaces
        issue = _make_issue(
            meta["space2_guid"],
            issue_type="space_unnamed",
            element_class="IfcSpace",
            element_name="Room 2",
        )

        value, _, skip = extract_value_for_issue(f, issue)

        assert value is None
        assert skip is not None
        assert "não enriquecido" in skip

    def test_space_with_empty_names_is_skipped(self, ifc_with_spaces):
        """Espaço sem LongName cai no Name; se igual ao genérico, skip."""
        f, meta = ifc_with_spaces
        issue = _make_issue(
            meta["space4_guid"],
            issue_type="space_unnamed",
            element_class="IfcSpace",
            element_name="Room",
        )

        value, _, skip = extract_value_for_issue(f, issue)

        assert value is None
        assert skip is not None


# ---------------------------------------------------------------------------
# system_unclassified
# ---------------------------------------------------------------------------


class TestSystemClassificationExtraction:
    def test_classified_system_is_extracted(self, ifc_with_walls):
        """Classificação escrita por classificar_sistema é lida de volta."""
        f, meta = ifc_with_walls
        writer = IFCWriter(f)
        writer.classificar_sistema(
            meta["wall1_guid"], "Alvenaria de vedação em bloco cerâmico"
        )
        issue = _make_issue(meta["wall1_guid"], issue_type="system_unclassified")

        value, note, skip = extract_value_for_issue(f, issue)

        assert skip is None
        assert note is None
        assert value == "Alvenaria de vedação em bloco cerâmico"

    def test_classification_in_other_system_gets_note(self, ifc_with_walls):
        """Referência em outro IfcClassification é aceita com nota de fallback."""
        f, meta = ifc_with_walls
        writer = IFCWriter(f)
        writer.classificar_sistema(
            meta["wall2_guid"], "Concreto moldado in loco", classification_name="Outro Sistema"
        )
        issue = _make_issue(meta["wall2_guid"], issue_type="system_unclassified")

        value, note, skip = extract_value_for_issue(f, issue)

        assert skip is None
        assert value == "Concreto moldado in loco"
        assert note is not None
        assert "Outro Sistema" in note

    def test_unclassified_element_is_skipped(self, ifc_with_walls):
        f, meta = ifc_with_walls
        issue = _make_issue(meta["wall3_guid"], issue_type="system_unclassified")

        value, _, skip = extract_value_for_issue(f, issue)

        assert value is None
        assert skip is not None
        assert "sem classificação" in skip


# ---------------------------------------------------------------------------
# Cobertura de tipos e GUIDs
# ---------------------------------------------------------------------------


class TestCoverageGuards:
    def test_guid_missing_in_gt_model_is_skipped(self, ifc_with_walls):
        f, _ = ifc_with_walls
        issue = _pset_issue("0" * 22)

        value, _, skip = extract_value_for_issue(f, issue)

        assert value is None
        assert skip is not None
        assert "GlobalId ausente" in skip

    def test_unsupported_issue_type_is_skipped(self, ifc_with_walls):
        f, meta = ifc_with_walls
        issue = _make_issue(meta["wall1_guid"], issue_type="relation_broken")

        value, _, skip = extract_value_for_issue(f, issue)

        assert value is None
        assert skip is not None
        assert "fora das 3 tarefas" in skip


# ---------------------------------------------------------------------------
# Conjunto completo + YAML round-trip
# ---------------------------------------------------------------------------


class TestExtractGroundTruth:
    def _enriched_model_and_issues(self, ifc_with_walls, ifc_with_spaces=None):
        f, meta = ifc_with_walls
        writer = IFCWriter(f)
        writer.preencher_pset(
            meta["wall1_guid"], "Pset_WallCommon", {"ThermalTransmittance": 2.5}
        )
        writer.classificar_sistema(
            meta["wall2_guid"], "Concreto moldado in loco"
        )
        issues = [
            _pset_issue(meta["wall1_guid"]),
            _make_issue(meta["wall2_guid"], issue_type="system_unclassified"),
            _pset_issue(meta["wall3_guid"]),  # não enriquecida → skip
            _make_issue(meta["wall1_guid"], issue_type="relation_broken"),  # skip
        ]
        return f, issues

    def test_extract_ground_truth_splits_items_and_skips(self, ifc_with_walls):
        f, issues = self._enriched_model_and_issues(ifc_with_walls)

        result = extract_ground_truth(issues, f)

        assert isinstance(result, GTExtractionResult)
        assert result.extracted_count == 2
        assert len(result.skipped) == 2
        assert all(item.verified is False for item in result.ground_truth.items)

    def test_extracted_items_match_issues_by_natural_key(self, ifc_with_walls):
        """GroundTruth.get_for_issue encontra os itens extraídos pela chave natural."""
        f, issues = self._enriched_model_and_issues(ifc_with_walls)

        result = extract_ground_truth(issues, f)
        gt = result.ground_truth

        pset_item = gt.get_for_issue(issues[0])
        assert pset_item is not None
        assert pset_item.expected_value == pytest.approx(2.5)

        system_item = gt.get_for_issue(issues[1])
        assert system_item is not None
        assert system_item.expected_value == "Concreto moldado in loco"

    def test_yaml_roundtrip_is_loadable_by_ground_truth(
        self, ifc_with_walls, tmp_path: Path
    ):
        """O YAML gerado carrega via GroundTruth.from_yaml com os mesmos itens."""
        f, issues = self._enriched_model_and_issues(ifc_with_walls)
        result = extract_ground_truth(issues, f)
        output = tmp_path / "ground_truth.yaml"

        write_ground_truth_yaml(result, output)
        loaded = GroundTruth.from_yaml(output)

        assert len(loaded.items) == 2
        assert loaded.metadata["protocol"] == "gt-by-diff"
        assert loaded.metadata["verified_by"] is None
        assert loaded.metadata["total_items"] == 2
        assert loaded.metadata["total_skipped"] == 2
        item = loaded.get_for_issue(issues[0])
        assert item is not None
        assert item.expected_value == pytest.approx(2.5)
        assert item.verified is False

    def test_yaml_records_source_hashes_when_paths_given(
        self, ifc_with_walls, tmp_path: Path
    ):
        """Hashes SHA256 dos arquivos de origem entram no metadata quando fornecidos."""
        f, issues = self._enriched_model_and_issues(ifc_with_walls)
        result = extract_ground_truth(issues, f)
        gt_ifc = tmp_path / "gt.ifc"
        f.write(str(gt_ifc))
        output = tmp_path / "ground_truth.yaml"

        write_ground_truth_yaml(result, output, gt_ifc_path=gt_ifc)
        loaded = GroundTruth.from_yaml(output)

        assert loaded.metadata["gt_ifc_sha256"] is not None
        assert len(loaded.metadata["gt_ifc_sha256"]) == 64
        assert loaded.metadata["input_ifc_sha256"] is None
