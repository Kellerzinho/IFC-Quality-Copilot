"""Aceite vertical E3 pelo pipeline público ``run_catalog_analysis`` (A05, A14, A23, A24).

Autoridade SQLite, artefatos retidos, curadoria/publicação E2, adoção, backend IDS,
leitor de observações e as duas operações M3 são os componentes REAIS. Projeto,
atores, catálogo, IFC e IDS são SINTÉTICOS e declarados; publicar aqui gera recibo
técnico de bytes de teste, não aprovação curatorial de conteúdo real.
"""

import hashlib
import json
import os
import socket
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

pytest.importorskip("ifctester", reason="extra e3 não instalado (ifctester==0.8.5)")

from src.domain_catalog.curation_models import PublicationReceipt
from src.domain_catalog.migration_contracts import AdoptionReceipt, MigrationError
from src.ifc_analyzer.observations import TextValue
from src.operations.contracts import SourceArtifactRef
from src.pipeline import run_catalog_analysis
from src.validation.analysis_identity import AnalysisRun
from src.validation.catalog_analysis import (
    CatalogAnalysisReceipt,
    PersistedAnalysis,
    load_analysis,
)
from tests.operations import analysis_env as ae
from tests.operations.adoption_env import AdoptionEnv, apply, prepare
from tests.operations.e3_env import publish_first, publish_update
from tests.suggestion_engine import m3_helpers as m

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sentinelas: rede, LLM, writer, pipeline/registry/cache legados falham se usados."""

    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("chamada proibida no pipeline E3 determinístico")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    import src.bsdd.client as bsdd_client
    import src.pipeline as pipeline
    import src.semantic_registry.registry as registry
    import src.suggestion_engine.issue_store as issue_store
    import src.suggestion_engine.ollama_client as ollama
    import src.suggestion_engine.suggestion as suggestion
    import src.suggestion_engine.suggestion_cache as cache
    import src.suggestion_engine.worker as worker
    import src.writer.ifc_writer as writer

    for target in (
        bsdd_client.BSDDClient,
        ollama.OllamaClient,
        suggestion.SuggestionGenerator,
        cache.SuggestionCache,
        worker.SuggestionWorker,
        issue_store.IssueStore,
        writer.IFCWriter,
        pipeline.QualityPipeline,
    ):
        monkeypatch.setattr(target, "__init__", blocked)
    for name in dir(registry):
        item = getattr(registry, name)
        if isinstance(item, type) and item.__module__ == registry.__name__:
            monkeypatch.setattr(item, "__init__", blocked)


def _execute(aenv: AdoptionEnv, run: AnalysisRun) -> CatalogAnalysisReceipt:
    return run_catalog_analysis(
        ae.request_for(run),
        store=aenv.env.store,
        artifacts=aenv.env.artifacts,
        operation_bundle=ae.operation_bundle(),
    )


def _runs(aenv: AdoptionEnv, adoption: AdoptionReceipt) -> list[AnalysisRun]:
    return ae.runs_in_pair_order(aenv, adoption.queued_analysis_ids)


def _source_hashes(aenv: AdoptionEnv, runs: list[AnalysisRun]) -> dict[str, str]:
    refs: list[SourceArtifactRef] = [r.identity.ifc for r in runs] + [r.identity.ids for r in runs]
    return {
        ref.storage_key: hashlib.sha256(
            aenv.env.artifacts.read_verified_source(ref).read_bytes()
        ).hexdigest()
        for ref in refs
    }


def _outcome(stored: PersistedAnalysis) -> list[tuple[str | None, int, str, str | None, list]]:
    assert stored.enrichment is not None
    return [
        (
            r.field.target_field_name,
            r.field.element.express_id,
            r.status,
            r.reason,
            [a.value for a in r.alternatives],
        )
        for r in stored.enrichment.results
    ]


def _summary(stored: PersistedAnalysis) -> list[tuple[str | None, str, str | None, list]]:
    return [(name, status, reason, values) for name, _, status, reason, values in _outcome(stored)]


def _by_pair(
    aenv: AdoptionEnv, receipts: list[CatalogAnalysisReceipt]
) -> dict[str, PersistedAnalysis]:
    disciplines = {0: "A", 1: "B"}
    order = {pair: index for index, pair in enumerate(aenv.pairs)}
    result = {}
    for receipt in receipts:
        stored = load_analysis(aenv.env.store, receipt.analysis_id)
        result[disciplines[order[stored.run.identity.pair_id]]] = stored
    return result


def _cache_keys(aenv: AdoptionEnv, analysis_id: uuid.UUID) -> set[str]:
    with aenv.env.store.transaction() as uow:
        return {row.document["cache_key"] for row in uow.cache.scan(analysis_id=str(analysis_id))}


def _reopen_in_subprocess(aenv: AdoptionEnv, ids: list[uuid.UUID]) -> dict[str, list[str]]:
    script = (
        "import json, sys, uuid\n"
        "from pathlib import Path\n"
        "from src.operations.database import OperationalStore\n"
        "from src.validation.catalog_analysis import load_analysis\n"
        "store = OperationalStore.open(Path(sys.argv[1]))\n"
        "out = {}\n"
        "for a in sys.argv[2:]:\n"
        "    s = load_analysis(store, uuid.UUID(a))\n"
        "    out[a] = [s.run.identity.digest(), s.snapshot.content_sha256,\n"
        "              s.enrichment.content_sha256, str(s.receipt.operational.receipt_id)]\n"
        "print(json.dumps(out))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(aenv.env.store.root), *map(str, ids)],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return json.loads(result.stdout)


def test_vertical_release_update_and_rollback_over_two_real_pairs(
    tmp_path: Path, forbidden: None
) -> None:
    aenv = ae.make_analysis_env(tmp_path / "env")

    published = publish_first(aenv.env, ae.catalog())
    adoption1 = apply(aenv, prepare(aenv, published.release, "initial"))
    runs1 = _runs(aenv, adoption1)
    before = _source_hashes(aenv, runs1)
    assert isinstance(published, PublicationReceipt)
    assert isinstance(adoption1, AdoptionReceipt)
    assert adoption1.operational.operation == "apply_catalog_adoption"
    assert [r.state for r in runs1] == ["queued", "queued"]

    receipts1 = [_execute(aenv, run) for run in runs1]
    assert {r.state for r in receipts1} == {"completed"}
    assert {r.operational.operation for r in receipts1} == {"execute_analysis"}
    first = _by_pair(aenv, receipts1)
    assert _summary(first["A"]) == [
        ("SYN_Metodo", "proposed", None, [TextValue(value="A")]),
        ("SYN_Metodo", "abstained", "evidence_conflict", []),
        ("SYN_Codigo", "proposed", None, [TextValue(value="Café")]),
        ("SYN_Codigo", "abstained", "no_evidence", []),
    ]
    assert _summary(first["B"]) == [
        ("SYN_Metodo", "not_requested", "already_satisfied", []),
        ("SYN_Codigo", "proposed", None, [TextValue(value="Outro")]),
    ]
    snapshot_a = first["A"].snapshot
    assert snapshot_a is not None
    assert [r.state for r in snapshot_a.requirements] == ["non_compliant"] * 4
    assert snapshot_a.source_check.signature_before == snapshot_a.source_check.signature_after
    methods = {
        alternative.method
        for result in first["A"].enrichment.results  # type: ignore[union-attr]
        for alternative in result.alternatives
    }
    assert methods == {"exact_recovery", "code_standardization"}

    reopened = _reopen_in_subprocess(aenv, [r.analysis_id for r in receipts1])
    for receipt in receipts1:
        assert reopened[str(receipt.analysis_id)] == [
            receipt.identity_sha256,
            receipt.diagnostic_sha256,
            receipt.enrichment_sha256,
            str(receipt.operational.receipt_id),
        ]

    revised = publish_update(
        aenv.env,
        published.release,
        (
            ("aliases", ae.draft_entity(m.alias(sets=("SYN_Antigo",)))),
            ("evidence_policies", ae.code_policy(on_missing="request_human", lifecycle="draft")),
        ),
        "1.1.0",
    )
    adoption2 = apply(aenv, prepare(aenv, revised.release, "update"))
    second = _by_pair(aenv, [_execute(aenv, run) for run in _runs(aenv, adoption2)])
    assert _summary(second["A"])[0] == ("SYN_Metodo", "abstained", "no_evidence", [])
    assert _summary(second["A"])[2] == ("SYN_Codigo", "proposed", None, [TextValue(value="Café")])
    absent_code = second["A"].enrichment.results[3]  # type: ignore[union-attr]
    assert absent_code.assessment is not None
    assert absent_code.assessment.action == "request_human"
    assert not _cache_keys(aenv, first["A"].run.analysis_id) & _cache_keys(
        aenv, second["A"].run.analysis_id
    )
    contexts1 = {c.context_sha256 for c in first["A"].enrichment.contexts}  # type: ignore[union-attr]
    contexts2 = {c.context_sha256 for c in second["A"].enrichment.contexts}  # type: ignore[union-attr]
    assert not contexts1 & contexts2

    adoption3 = apply(aenv, prepare(aenv, published.release, "rollback"))
    runs3 = _runs(aenv, adoption3)
    third = _by_pair(aenv, [_execute(aenv, run) for run in runs3])
    for pair in ("A", "B"):
        assert _summary(third[pair]) == _summary(first[pair])
        assert third[pair].run.analysis_id != first[pair].run.analysis_id
        assert third[pair].run.identity.pin_revision == 3
        assert not _cache_keys(aenv, first[pair].run.analysis_id) & _cache_keys(
            aenv, third[pair].run.analysis_id
        )
        assert load_analysis(aenv.env.store, first[pair].run.analysis_id) == first[pair]
        assert load_analysis(aenv.env.store, second[pair].run.analysis_id) == second[pair]
    assert _source_hashes(aenv, runs3) == before


def test_one_pair_failing_keeps_the_other_and_errors_use_no_forbidden_path(
    tmp_path: Path, forbidden: None
) -> None:
    aenv = ae.make_analysis_env(tmp_path / "env")
    release = publish_first(aenv.env, ae.catalog()).release
    run_a, run_b = _runs(aenv, apply(aenv, prepare(aenv, release, "initial")))
    path = aenv.env.artifacts.read_verified_source(run_a.identity.ifc)
    os.chmod(path, 0o644)
    with path.open("ab") as handle:
        handle.write(b"/* adulterado */\n")

    failed = _execute(aenv, run_a)
    completed = _execute(aenv, run_b)

    assert (failed.state, failed.snapshot_id, failed.enrichment_id) == ("failed", None, None)
    assert [p.code for p in failed.problems] == ["artifact_integrity_error"]
    assert completed.state == "completed"
    stored_a = load_analysis(aenv.env.store, run_a.analysis_id)
    assert stored_a.run.state == "failed"
    assert stored_a.receipt == failed
    assert _execute(aenv, run_a) == failed
    stored_b = load_analysis(aenv.env.store, run_b.analysis_id)
    assert _summary(stored_b)[1] == ("SYN_Codigo", "proposed", None, [TextValue(value="Outro")])


def test_synthetic_release_is_refused_in_an_operational_store(tmp_path: Path) -> None:
    aenv = ae.make_analysis_env(tmp_path / "env", purpose="operational")
    release = publish_first(aenv.env, ae.catalog()).release
    with pytest.raises(MigrationError) as refused:
        prepare(aenv, release, "initial")
    assert refused.value.reason == "synthetic_catalog_forbidden"
    assert aenv.adoption.list_runs(aenv.project_id) == []
