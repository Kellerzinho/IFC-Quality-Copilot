"""Obrigação M1-13: consumidor rico determinístico do catálogo, sem legado nem LLM.

O enriquecimento recebe snapshot formal, release fixado e observações da mesma
sessão e devolve DTOs ricos tipados — nunca ``BSDDContext``, ``Issue.context``,
``SuggestionSet`` ou strings. Dados SINTÉTICOS; atores não envolvidos.
"""

import json
import os
import socket
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

pytest.importorskip("ifctester", reason="extra e3 não instalado (ifctester==0.8.5)")

from src.suggestion_engine.catalog_contracts import (
    EnrichmentRun,
    FieldEnrichmentResult,
)
from src.suggestion_engine.catalog_service import CatalogEnrichmentService
from src.validation.analysis_service import CatalogUnavailable
from tests.suggestion_engine import m3_helpers as m
from tests.validation import ifc_builders as ib

ROOT = Path(__file__).resolve().parents[2]


def _three_slabs():
    model = ib.model()
    m.slab(model, ("SYN_Legado", "Metodo", "A", "IfcLabel"))
    m.slab(model, ("SYN_Conjunto", "SYN_Metodo", "B", "IfcLabel"))
    conflicted = m.slab(model, ("SYN_Legado", "Metodo", "A", "IfcLabel"))
    slab_type = ib.typed(model, conflicted, "IfcSlabType")
    ib.pset(model, slab_type, "SYN_Legado", [ib.single(model, "Metodo", "IfcLabel", "B")])
    return model


@pytest.fixture
def forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sentinelas: rede e construtores legados/LLM falham se forem chamados."""

    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("chamada proibida no caminho M3 determinístico")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    import src.bsdd.client as bsdd_client
    import src.semantic_registry.registry as registry
    import src.suggestion_engine.ollama_client as ollama
    import src.suggestion_engine.suggestion as suggestion
    import src.suggestion_engine.suggestion_cache as cache
    import src.writer.ifc_writer as writer

    monkeypatch.setattr(bsdd_client.BSDDClient, "__init__", blocked)
    monkeypatch.setattr(ollama.OllamaClient, "__init__", blocked)
    monkeypatch.setattr(suggestion.SuggestionGenerator, "__init__", blocked)
    monkeypatch.setattr(cache.SuggestionCache, "__init__", blocked)
    monkeypatch.setattr(writer.IFCWriter, "__init__", blocked)
    for name in dir(registry):
        target = getattr(registry, name)
        if isinstance(target, type) and target.__module__ == registry.__name__:
            monkeypatch.setattr(target, "__init__", blocked)


def test_every_field_gets_a_typed_result_without_legacy_or_network(
    tmp_path: Path, forbidden: None
) -> None:
    c = m.case(tmp_path, m.content(), _three_slabs())
    run = CatalogEnrichmentService(c.bundle).enrich(
        c.snapshot, observations=c.observations, catalog=c.reader, enrichment_id=uuid.uuid4()
    )

    assert isinstance(run, EnrichmentRun)
    assert all(isinstance(r, FieldEnrichmentResult) for r in run.results)
    assert [(r.status, r.reason) for r in run.results] == [
        ("proposed", None),
        ("not_requested", "already_satisfied"),
        ("abstained", "evidence_conflict"),
    ]
    assert len(run.results) == len([r for r in c.snapshot.requirements if r.element is not None])
    assert EnrichmentRun.model_validate(run.model_dump(mode="json")) == run
    assert run.identity.diagnostic_sha256 == c.snapshot.content_sha256
    assert run.identity.operation_bundle_sha256 == c.bundle.manifest_sha256
    assert [r.state for r in c.snapshot.requirements] == [
        "non_compliant",
        "compliant",
        "non_compliant",
    ]


def test_unavailable_catalog_keeps_formal_results_and_fails_only_enrichment(tmp_path: Path) -> None:
    c = m.case(tmp_path, m.content(), _three_slabs())
    run = CatalogEnrichmentService(c.bundle).enrich(
        c.snapshot,
        observations=c.observations,
        catalog=CatalogUnavailable(state="unavailable", reason="pacote retido ausente"),
        enrichment_id=uuid.uuid4(),
    )
    assert [(r.status, r.reason) for r in run.results] == [
        ("failed", "package_error"),
        ("not_requested", "already_satisfied"),
        ("failed", "package_error"),
    ]
    assert run.contexts == ()


def test_new_consumer_does_not_import_legacy_grounding_or_cache() -> None:
    script = (
        "import json, sys\n"
        "import src.suggestion_engine.catalog_service\n"
        "import src.validation.catalog_analysis\n"
        "loaded = [m for m in sys.modules if m.startswith('src.suggestion_engine.')]\n"
        "print(json.dumps(sorted(loaded)))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    loaded = set(json.loads(result.stdout))
    for legacy in (
        "grounding",
        "suggestion",
        "suggestion_cache",
        "ollama_client",
        "worker",
        "deterministic",
    ):
        assert f"src.suggestion_engine.{legacy}" not in loaded


def test_not_attached_catalog_is_insufficient_context_not_package_failure(
    tmp_path: Path,
) -> None:
    c = m.case(tmp_path, m.content(), _three_slabs())
    run = CatalogEnrichmentService(c.bundle).enrich(
        c.snapshot,
        observations=c.observations,
        catalog=CatalogUnavailable(state="not_attached", reason="sem pin"),
        enrichment_id=uuid.uuid4(),
    )
    assert [(r.status, r.reason) for r in run.results] == [
        ("abstained", "insufficient_context"),
        ("not_requested", "already_satisfied"),
        ("abstained", "insufficient_context"),
    ]


def _proposed_run(tmp_path: Path) -> EnrichmentRun:
    model = ib.model()
    m.slab(model, ("SYN_Legado", "Metodo", "A", "IfcLabel"))
    c = m.case(tmp_path, m.content(), model)
    run = CatalogEnrichmentService(c.bundle).enrich(
        c.snapshot, observations=c.observations, catalog=c.reader, enrichment_id=uuid.uuid4()
    )
    assert [r.status for r in run.results] == ["proposed"]
    return run


def _rehashed(document: dict) -> dict:
    from src.operations.contracts import canonical_sha256

    body = {k: v for k, v in document.items() if k != "content_sha256"}
    return {**body, "content_sha256": canonical_sha256(body)}


@pytest.mark.parametrize(
    "tamper",
    [
        "dangling_evidence",
        "assessment_of_other_context",
        "field_of_other_context",
        "assessment_dangling_admissible",
    ],
)
def test_reopened_run_refuses_references_outside_its_contexts(tmp_path: Path, tamper: str) -> None:
    """E3-06: hash correto não basta; cada referência interna resolve no próprio run."""
    document = _proposed_run(tmp_path).model_dump(mode="json")
    result = document["results"][0]
    if tamper == "dangling_evidence":
        result["alternatives"][0]["evidence_refs"] = ["f" * 64]
    elif tamper == "assessment_dangling_admissible":
        admissible = result["assessment"]["admissible_observation_ids"]
        result["assessment"]["admissible_observation_ids"] = sorted([*admissible, "f" * 64])
    elif tamper == "assessment_of_other_context":
        result["assessment"]["context_sha256"] = "e" * 64
    else:
        result["field"]["concept_id"] = "urn:uuid:00000000-0000-4000-8000-0000000000ff"
    with pytest.raises(ValueError):
        EnrichmentRun.model_validate(_rehashed(document))
