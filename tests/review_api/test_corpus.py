"""Corpus sintético M4: determinismo e correspondência com o manifesto."""

import hashlib
import json
from pathlib import Path
from types import ModuleType

import ifcopenshell

MANIFEST = Path(__file__).resolve().parents[1] / "fixtures" / "m4" / "manifest.json"


def test_generated_files_match_manifest_hashes(corpus_dir: Path) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["generated_with"]["ifcopenshell"] == ifcopenshell.version
    for name, entry in manifest["files"].items():
        digest = hashlib.sha256((corpus_dir / name).read_bytes()).hexdigest()
        assert digest == entry["sha256"], f"{name} divergiu do manifesto"


def test_pair_shares_coordinates_and_one_global_id(
    corpus_dir: Path, generator: ModuleType
) -> None:
    arq = ifcopenshell.open(str(corpus_dir / generator.ARQ_IFC))
    est = ifcopenshell.open(str(corpus_dir / generator.EST_IFC))
    shared = {e.GlobalId for e in arq.by_type("IfcElement")} & {
        e.GlobalId for e in est.by_type("IfcElement")
    }
    assert shared == {generator.guid(generator.SHARED_SLAB_GUID_KEY)}
    assert arq.schema == est.schema == "IFC4"
