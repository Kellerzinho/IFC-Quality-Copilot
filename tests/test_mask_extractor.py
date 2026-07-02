"""Testes do masking de nomes de espaços (Fase C.3)."""

from __future__ import annotations

from pathlib import Path

import ifcopenshell

from src.experiment.evaluator import GroundTruth
from src.experiment.gt_extractor import GTExtractionResult, write_ground_truth_yaml
from src.experiment.mask_extractor import mask_space_names
from src.ifc_analyzer.space_diagnostics import diagnose_spaces


class TestMaskSpaceNames:
    def test_masks_only_functional_names(self, ifc_with_spaces):
        """Só espaços com nome funcional são mascarados; genéricos ficam como estão."""
        f, meta = ifc_with_spaces  # Room 1, Room 2, Cozinha, Room

        items = mask_space_names(f)

        assert len(items) == 1
        assert items[0].expected_value == "Cozinha"
        assert items[0].element_guid == meta["space3_guid"]
        assert items[0].issue_type == "space_unnamed"
        assert items[0].verified is False

    def test_masked_space_loses_long_name(self, ifc_with_spaces):
        f, meta = ifc_with_spaces

        mask_space_names(f)

        space3 = f.by_guid(meta["space3_guid"])
        assert not space3.LongName

    def test_masked_space_triggers_space_unnamed_issue(self, ifc_with_spaces):
        """Após o masking, o diagnóstico passa a apontar o espaço mascarado."""
        f, meta = ifc_with_spaces

        before = {i.element_guid for i in diagnose_spaces(f)}
        assert meta["space3_guid"] not in before

        mask_space_names(f)

        after = {i.element_guid for i in diagnose_spaces(f)}
        assert meta["space3_guid"] in after

    def test_gt_matches_masked_issue_by_natural_key(self, ifc_with_spaces):
        """O GT gerado casa com a issue do modelo mascarado pela chave natural."""
        f, meta = ifc_with_spaces

        items = mask_space_names(f)
        gt = GroundTruth(items=items)
        issues = diagnose_spaces(f)
        masked_issue = next(
            i for i in issues if i.element_guid == meta["space3_guid"]
        )

        item = gt.get_for_issue(masked_issue)
        assert item is not None
        assert item.expected_value == "Cozinha"

    def test_yaml_roundtrip(self, ifc_with_spaces, tmp_path: Path):
        f, _ = ifc_with_spaces
        items = mask_space_names(f)
        result = GTExtractionResult(
            ground_truth=GroundTruth(items=items, metadata={"protocol": "masking"}),
            skipped=[],
        )
        output = tmp_path / "ground_truth_spaces.yaml"

        write_ground_truth_yaml(result, output)
        loaded = GroundTruth.from_yaml(output)

        assert len(loaded.items) == 1
        assert loaded.metadata["protocol"] == "masking"

    def test_masked_model_survives_disk_roundtrip(self, ifc_with_spaces, tmp_path: Path):
        """O modelo mascarado salvo em disco preserva a remoção do LongName."""
        f, meta = ifc_with_spaces
        mask_space_names(f)
        path = tmp_path / "masked.ifc"
        f.write(str(path))

        reloaded = ifcopenshell.open(str(path))
        space3 = reloaded.by_guid(meta["space3_guid"])
        assert not space3.LongName
        # Name "Cozinha" também é funcional → mascarado junto
        assert not space3.Name
