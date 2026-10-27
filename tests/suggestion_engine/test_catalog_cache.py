"""Cache exato de contexto/resultado M3 na autoridade comum (A22).

Chave SHA-256 completa sobre identidade, diagnóstico, contexto, bundle, receita e
condição; corrupção e colisão são falhas, nunca hit vazio. Sem reuso entre análises.
"""

import sqlite3
import uuid
from pathlib import Path

import pytest

pytest.importorskip("ifctester", reason="extra e3 não instalado (ifctester==0.8.5)")

from src.operations.repositories import encode_document
from src.suggestion_engine.catalog_cache import (
    CacheCollisionError,
    CacheIntegrityError,
    CatalogCache,
    cache_components,
    cache_key,
)
from src.suggestion_engine.catalog_context import build_field_context
from src.suggestion_engine.catalog_contracts import RECIPE
from src.suggestion_engine.catalog_evidence import assess_evidence
from src.suggestion_engine.catalog_operations import execute_catalog_operation
from tests.suggestion_engine import m3_helpers as m
from tests.validation import ifc_builders as ib


def _built(tmp_path: Path, catalog=None, value: str = "A"):
    model = ib.model()
    m.slab(model, ("SYN_Legado", "Metodo", value, "IfcLabel"))
    c = m.case(tmp_path, catalog or m.content(), model)
    context = build_field_context(c.snapshot, c.row(), c.reader, c.observations, RECIPE)
    result = execute_catalog_operation(context, assess_evidence(context, c.bundle), c.bundle)
    return c, context, result


def test_every_relevant_component_changes_the_key(tmp_path: Path) -> None:
    c, context, _ = _built(tmp_path / "base")
    base = cache_components(c.snapshot, context, c.bundle)
    key = cache_key(base)

    variants = {
        "identity": {**base, "analysis_identity_sha256": "1" * 64},
        "diagnostic": {**base, "diagnostic_sha256": "2" * 64},
        "context": {**base, "context_sha256": "3" * 64},
        "bundle": {**base, "operation_bundle_sha256": "4" * 64},
        "condition": {**base, "condition_config_sha256": "5" * 64},
        "limits": {**base, "limits": {**base["limits"], "max_context_bytes": 1}},
    }
    keys = {name: cache_key(value) for name, value in variants.items()}
    assert key not in keys.values()
    assert len(set(keys.values())) == len(keys)

    _, alias_context, _ = _built(
        tmp_path / "alias",
        m.content(aliases=(m.alias(term="Metodo", sets=("SYN_Legado", "SYN_X")),)),
    )
    _, value_context, _ = _built(tmp_path / "valor", value="B")
    _, policy_context, _ = _built(tmp_path / "pol", m.content(on_missing="request_human"))
    for other in (alias_context, value_context, policy_context):
        assert other.context_sha256 != context.context_sha256


def _executed(tmp_path: Path):
    """Run real do pipeline: entradas de cache gravadas pela própria conclusão atômica."""
    from src.pipeline import run_catalog_analysis
    from tests.operations import analysis_env as ae
    from tests.operations.adoption_env import apply, prepare
    from tests.operations.e3_env import publish_first

    aenv = ae.make_analysis_env(tmp_path / "env")
    release = publish_first(aenv.env, ae.catalog()).release
    receipt = apply(aenv, prepare(aenv, release, "initial"))
    run_a, run_b = ae.runs_in_pair_order(aenv, receipt.queued_analysis_ids)
    run_catalog_analysis(
        ae.request_for(run_a),
        store=aenv.env.store,
        artifacts=aenv.env.artifacts,
        operation_bundle=ae.operation_bundle(),
    )
    return aenv, run_a, run_b


def test_put_get_corruption_and_collision_in_the_shared_store(tmp_path: Path) -> None:
    aenv, run_a, _ = _executed(tmp_path)
    store = aenv.env.store
    with store.transaction() as uow:
        rows = uow.cache.scan(analysis_id=str(run_a.analysis_id))
    assert rows
    key = rows[0].document["cache_key"]
    components = rows[0].document["key_components"]

    with store.transaction() as uow:
        cached = CatalogCache(uow).get(key)
        assert cached is not None
        CatalogCache(uow).put(key, components, cached.result)  # idempotente
    result = cached.result

    other = result.model_copy(update={"limitations": ("outra",)})
    with pytest.raises(CacheCollisionError), store.transaction() as uow:
        CatalogCache(uow).put(key, components, other)

    with store.transaction() as uow:
        row = uow.cache.get(key)
        assert row is not None
        tampered = {**row.document["result"], "limitations": ["adulterado"]}
        assert tampered != row.document["result"]
        forged = {**row.document, "result": tampered}
    payload, digest = encode_document(forged)
    with sqlite3.connect(store.path) as conn:
        conn.execute("DROP TRIGGER context_cache_immutable")
        conn.execute(
            "UPDATE context_cache SET payload = ?, payload_sha256 = ? WHERE cache_key = ?",
            (payload, digest, key),
        )
    with pytest.raises(CacheIntegrityError), store.transaction() as uow:
        CatalogCache(uow).get(key)


def test_result_of_another_analysis_is_never_stored_or_served(tmp_path: Path) -> None:
    """E3-06: transplantar resultado de outra análise para a chave de uma análise enfileirada."""
    aenv, run_a, run_b = _executed(tmp_path / "pipe")
    c, context, result = _built(tmp_path / "m")
    components = {
        **cache_components(c.snapshot, context, c.bundle),
        "analysis_id": str(run_b.analysis_id),
    }
    key = cache_key(components)
    store = aenv.env.store
    with pytest.raises(CacheIntegrityError), store.transaction() as uow:
        CatalogCache(uow).put(key, components, result)
    with store.transaction() as uow:
        assert uow.cache.get(key) is None

    # Mesmo inserido por fora (re-hasheado e coerente), nunca é hit.
    from src.operations.contracts import canonical_sha256

    with store.transaction() as uow:
        uow.cache.insert(
            {
                "schema_version": 1,
                "cache_key": key,
                "analysis_id": str(run_b.analysis_id),
                "key_components": components,
                "result": result.model_dump(mode="json"),
                "result_sha256": canonical_sha256(result.model_dump(mode="json")),
            }
        )
    with pytest.raises(CacheIntegrityError), store.transaction() as uow:
        CatalogCache(uow).get(key)

    # Componentes da análise certa, resultado de outra: incoerência interna.
    with store.transaction() as uow:
        own = uow.cache.scan(analysis_id=str(run_a.analysis_id))[0].document
    foreign = {**own["key_components"], "context_sha256": context.context_sha256}
    with pytest.raises(CacheIntegrityError), store.transaction() as uow:
        CatalogCache(uow).put(cache_key(foreign), foreign, result)


def test_new_analysis_never_hits_previous_entries(tmp_path: Path) -> None:
    c, context, _ = _built(tmp_path)
    first = cache_components(c.snapshot, context, c.bundle)
    second = {**first, "analysis_id": str(uuid.uuid4())}
    assert cache_key(first) != cache_key(second)


@pytest.mark.parametrize("tamper", ["runtime_only", "dangling_evidence"])
def test_entry_must_match_the_stored_run_and_recomputed_components(
    tmp_path: Path, tamper: str
) -> None:
    """M-03: resultado/componentes coerentes entre si mas diferentes do run gravado."""
    aenv, run_a, _ = _executed(tmp_path)
    store = aenv.env.store
    with store.transaction() as uow:
        rows = uow.cache.scan(analysis_id=str(run_a.analysis_id))
    proposed = next(r.document for r in rows if r.document["result"]["status"] == "proposed")
    components = {**proposed["key_components"], "runtime": "forjado"}
    result = proposed["result"]
    if tamper == "dangling_evidence":
        result = {
            **result,
            "alternatives": [{**result["alternatives"][0], "evidence_refs": ["f" * 64]}],
        }
    from src.suggestion_engine.catalog_contracts import FieldEnrichmentResult

    forged = FieldEnrichmentResult.model_validate(result)
    with pytest.raises(CacheIntegrityError), store.transaction() as uow:
        CatalogCache(uow).put(cache_key(components), components, forged)
