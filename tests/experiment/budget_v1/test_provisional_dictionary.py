"""Dicionário provisório (fck, cobrimento, CAA) no formato aproximado do catálogo M1."""

import json
from pathlib import Path

import pytest

from src.experiment.budget_v1 import context_format as cf
from src.experiment.budget_v1 import provisional_dictionary as pd

URN = r"^urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


@pytest.fixture(scope="module")
def raw() -> dict:
    """Arquivo bruto."""
    return json.loads(pd.DEFAULT_DICTIONARY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def vocab() -> pd.Vocabulary:
    """Vocabulário derivado."""
    return pd.load_vocabulary()


def test_file_is_marked_provisional(raw: dict) -> None:
    assert raw["x_status"].startswith("PROVISÓRIO")
    assert "Juliana" in raw["x_status"]
    assert raw["manifest"]["catalog"]["namespace_status"] == "provisional"
    assert raw["manifest"]["content_origin"] == "synthetic_fixture"


def test_has_the_catalog_package_sections(raw: dict) -> None:
    for key in (
        "manifest", "source_artifacts", "source_assertions", "concepts", "units", "value_sets",
        "applicability_rules", "bindings", "aliases",
    ):  # fmt: skip
        assert key in raw, key


def test_ids_follow_catalog_patterns_and_are_unique(raw: dict) -> None:
    import re

    ids = [
        e["id"]
        for k in ("concepts", "units", "value_sets", "applicability_rules", "bindings", "aliases")
        for e in raw[k]
    ]
    assert len(ids) == len(set(ids))
    assert all(re.match(URN, i) for i in ids)
    codes = [c["code"] for c in raw["concepts"]]
    assert all(re.match(r"^[A-Z][A-Z0-9_.-]*$", c) for c in codes)


def test_every_reference_resolves(raw: dict) -> None:
    ids = {
        e["id"]
        for k in ("concepts", "units", "value_sets", "applicability_rules", "bindings")
        for e in raw[k]
    }
    assertions = {a["id"] for a in raw["source_assertions"]}
    artifacts = {a["id"] for a in raw["source_artifacts"]}
    for c in raw["concepts"]:
        assert c.get("unit_id") in ids | {None}
        assert c.get("value_set_id") in ids | {None}
        assert set(c["source_assertion_ids"]) <= assertions
    for b in raw["bindings"]:
        assert b["concept_id"] in ids
        assert b["applicability_rule_id"] in ids
    for a in raw["aliases"]:
        assert (a["target_concept_id"] or a["target_binding_id"]) in ids
    assert {a["source_artifact_id"] for a in raw["source_assertions"]} <= artifacts


def test_resolution_aliases_are_scoped_and_target_a_binding(raw: dict) -> None:
    """Mesma regra do AliasMapping do M1: alias de resolução exige escopo e binding alvo."""
    for a in raw["aliases"]:
        assert (a["target_concept_id"] is None) != (a["target_binding_id"] is None)
        if a["purpose"] in {"historical_spelling", "representation_match", "approved_equivalence"}:
            assert any(a["scope"][k] for k in ("set_names", "entity_classes", "schemas")), a["term"]
            assert a["target_binding_id"] is not None


def test_nothing_is_approved_or_writable(raw: dict) -> None:
    for k in ("concepts", "units", "value_sets", "applicability_rules", "bindings", "aliases"):
        assert all(e["lifecycle"] == "draft" for e in raw[k]), k
    assert not any(b["write_enabled"] for b in raw["bindings"])
    assert all(b["carrier_status"] == "pending_reconciliation" for b in raw["bindings"])


def test_standard_names_are_in_eb_orcamento(vocab: pd.Vocabulary) -> None:
    assert vocab.standard_name == {
        "fck": "EB_Orçamento.Concreto_fck_MPa",
        "cobrimento": "EB_Orçamento.Cobrimento_Nominal_mm",
        "caa": "EB_Orçamento.Classe_Agressividade",
    }


def test_sources_cite_nbr6118_and_nbr8953_with_section(raw: dict) -> None:
    by_source = {a["id"]: a for a in raw["source_assertions"]}
    fck = next(c for c in raw["concepts"] if c["code"] == "CONCRETO_FCK")
    assert any(i.startswith("abnt:nbr8953") for i in fck["source_assertion_ids"])
    cover = next(c for c in raw["concepts"] if c["code"] == "COBRIMENTO_NOMINAL")
    assert by_source[cover["source_assertion_ids"][0]]["locator"]["table"] == "Tabela 7.2"
    caa = next(c for c in raw["concepts"] if c["code"] == "CLASSE_AGRESSIVIDADE_AMBIENTAL")
    assert by_source[caa["source_assertion_ids"][0]]["locator"]["table"] == "Tabela 6.1"


def test_fcd_is_never_an_alias_of_fck(raw: dict, vocab: pd.Vocabulary) -> None:
    """M1 §2.2: fck e fcd não são sinônimos."""
    assert not any(a["term"].lower() == "fcd" for a in raw["aliases"])
    assert "fcd" in vocab.non_synonyms["fck"]
    assert all("fcd" not in names for e in vocab.exporters.values() for names in e.values())


def test_exposure_class_is_related_not_equivalent(raw: dict) -> None:
    exposure = next(b for b in raw["bindings"] if b["field_name"] == "ExposureClass")
    assert exposure["x_relacao"] == "relacionado_nao_equivalente"


def test_strength_class_is_a_derivation_with_value_set(raw: dict, vocab: pd.Vocabulary) -> None:
    strength = next(b for b in raw["bindings"] if b["field_name"] == "StrengthClass")
    assert strength["x_relacao"] == "derivacao"
    assert strength["value_set_id"]
    assert vocab.fck_classes == (20, 25, 30, 35, 40, 45, 50)
    assert "StrengthClass" in vocab.class_terms


def test_vocabulary_matches_concepts(vocab: pd.Vocabulary) -> None:
    assert vocab.concepts == ("fck", "cobrimento", "caa")
    assert vocab.target_unit == {"fck": "MPa", "cobrimento": "mm", "caa": None}
    assert vocab.codes["caa"] == ("I", "II", "III", "IV")
    assert vocab.cover_by_caa["III"]["viga_pilar"] == 40
    assert set(vocab.exporters) == {"revit_br", "tqs", "eberick", "tekla", "generico_en"}


def test_generator_follows_an_edited_dictionary(tmp_path: Path, raw: dict) -> None:
    """Trocar o arquivo muda os casos: os termos não estão fixos no código."""
    edited = json.loads(json.dumps(raw))
    for alias in edited["aliases"]:
        if alias["purpose"] == "representation_match":
            alias["term"] = "ZZ_" + alias["term"]
    path = tmp_path / "dic.json"
    path.write_text(json.dumps(edited, ensure_ascii=False), encoding="utf-8")
    vocab = pd.build_vocabulary(pd.load_dictionary(path))
    cases = cf.generate_cases(seed=1, per_kind=1, vocab=vocab)
    sources = [c.gold.source for c in cases if c.gold.source]
    assert sources
    assert all(".ZZ_" in s for s in sources)


def test_invalid_relation_is_refused(tmp_path: Path, raw: dict) -> None:
    edited = json.loads(json.dumps(raw))
    edited["bindings"][0]["x_relacao"] = "sinonimo_total"
    path = tmp_path / "dic.json"
    path.write_text(json.dumps(edited, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="x_relacao"):
        pd.load_dictionary(path)
