"""Handoff do staging bSDD para a curadoria E2 (E4, M1-10, Task 5).

Somente fixtures, catálogo e atores SINTÉTICOS, sobre os adaptadores de teste não
operacionais da E2. O staging é gravado, reaberto e verificado antes do handoff; a
curadoria recebe só rascunho. A publicação de teste usa conteúdo sintético para
provar que um payload novo com o mesmo ID não contorna ``_merge_import``.
"""

import json
from pathlib import Path

import pytest

from src.domain_catalog.content import CatalogContent
from src.domain_catalog.curation_errors import CommandValidationError
from src.domain_catalog.curation_models import CommandMeta, DraftHead, content_sha256
from src.domain_catalog.importers.bsdd import (
    import_bsdd_snapshot,
    load_bsdd_snapshot,
    main,
    read_bsdd_staging,
    write_bsdd_staging,
)
from src.domain_catalog.importers.bsdd_models import BSDDImportResult, SnapshotLimits
from src.domain_catalog.models import ApplicabilityRule, IFCBinding, LocalizedText
from src.domain_catalog.package import ComponentTerms
from tests.domain_catalog import factories as f
from tests.domain_catalog.curation_adapters import CurationEnv, make_env
from tests.domain_catalog.test_bsdd_import import FIXTURE, payload, source

TERMS = (ComponentTerms(component="conteúdo", terms="sintético, sem terceiros"),)
RULE_ID = "urn:uuid:00000000-0000-4000-8000-00000000b501"
BINDING_ID = "urn:uuid:00000000-0000-4000-8000-00000000b502"


def _meta(command_id: str, actor: str) -> CommandMeta:
    return CommandMeta(command_id=command_id, actor_context_id=actor)


def _staged(
    tmp_path: Path, document: object | None = None, name: str = "staging"
) -> BSDDImportResult:
    path = tmp_path / f"{name}.json"
    path.write_text(
        json.dumps(document if document is not None else payload(), ensure_ascii=False),
        encoding="utf-8",
    )
    result = import_bsdd_snapshot(
        load_bsdd_snapshot(path, source=source(), limits=SnapshotLimits())
    )
    write_bsdd_staging(result, tmp_path / name)
    return read_bsdd_staging(tmp_path / name)


def _import(
    env: CurationEnv, content: CatalogContent, command_id: str, **extra: object
) -> DraftHead:
    return env.curation.import_draft(
        _meta(command_id, env.importer),
        title="Snapshot bSDD sintético (teste)",
        catalog=f.catalog_identity(),
        content=content,
        source_label="staging bSDD sintético reaberto",
        reason="levar candidatos do staging à curadoria, sem aprovar",
        **extra,
    ).value


def test_reopened_staging_enters_curation_unchanged_and_only_as_draft(tmp_path: Path) -> None:
    staged = _staged(tmp_path)
    assert staged.content is not None
    env = make_env(tmp_path)
    head = _import(env, staged.content, "cmd-bsdd-1")
    stored = env.curation.get_revision(head.draft.draft_id, 1).content

    assert stored == staged.content
    assert head.content_sha256 == content_sha256(staged.content)
    assert {e.lifecycle for _, e in stored.iter_entities() if hasattr(e, "lifecycle")} == {"draft"}
    assert env.publication.list_published() == ()


def test_repeated_command_replays_and_new_command_does_not_duplicate_entities(
    tmp_path: Path,
) -> None:
    staged = _staged(tmp_path)
    assert staged.content is not None
    env = make_env(tmp_path)
    first = _import(env, staged.content, "cmd-bsdd-1")
    events = len(env.curation.events())
    replay = _import(env, staged.content, "cmd-bsdd-1")
    again = _import(env, _staged(tmp_path, name="again").content or staged.content, "cmd-bsdd-2")

    assert replay == first
    assert len(env.curation.events()) > events
    content = env.curation.get_revision(again.draft.draft_id, 1).content
    ids = [getattr(e, "id") for _, e in content.iter_entities()]  # noqa: B009
    assert len(ids) == len(set(ids))
    assert content == staged.content
    assert env.publication.list_published() == ()


def test_replayed_command_writes_no_new_event(tmp_path: Path) -> None:
    staged = _staged(tmp_path)
    assert staged.content is not None
    env = make_env(tmp_path)
    _import(env, staged.content, "cmd-bsdd-1")
    before = env.curation.events()
    _import(env, staged.content, "cmd-bsdd-1")

    assert env.curation.events() == before


def _publish_synthetic(env: CurationEnv, content: CatalogContent) -> None:
    """Publica conteúdo SINTÉTICO aprovado por curador sintético, só para testar a base."""
    concepts = tuple(
        c.model_copy(
            update={
                "definition": c.definition
                or (LocalizedText(lang="pt-BR", text="Definição sintética."),)
            }
        )
        for c in content.concepts
    )
    head = env.curation.import_draft(
        _meta("cmd-base", env.importer),
        title="Base sintética",
        catalog=f.catalog_identity(),
        content=content.model_copy(update={"concepts": concepts}),
        source_label="base sintética",
        reason="base sintética",
    ).value
    env.curation.submit_for_review(
        _meta("cmd-base-sub", env.curator),
        draft_id=head.draft.draft_id,
        revision=1,
        content_sha256=head.content_sha256,
        reason="pronto",
    )
    env.curation.review_draft(
        _meta("cmd-base-apr", env.curator),
        draft_id=head.draft.draft_id,
        revision=1,
        content_sha256=head.content_sha256,
        verdict="approve",
        justification="Conteúdo sintético conferido para o teste.",
    )
    candidate = env.publication.prepare_release(
        _meta("cmd-base-prp", env.curator),
        draft_id=head.draft.draft_id,
        revision=1,
        content_sha256=head.content_sha256,
        version="1.0.0",
        terms=TERMS,
        reason="preparar",
    ).value
    env.publication.publish(
        _meta("cmd-base-pub", env.curator),
        candidate_id=candidate.candidate_id,
        version="1.0.0",
        manifest_sha256=candidate.release.manifest_sha256,
        justification="Publicação sintética de teste.",
    )


def test_new_payload_with_same_id_does_not_bypass_merge_import(tmp_path: Path) -> None:
    staged = _staged(tmp_path)
    assert staged.content is not None
    env = make_env(tmp_path)
    _publish_synthetic(env, staged.content)
    base = env.publication.list_published()[0].release
    changed = staged.content.model_copy(
        update={
            "concepts": tuple(
                c.model_copy(
                    update={"definition": (LocalizedText(lang="pt-BR", text="Outra definição."),)}
                )
                for c in staged.content.concepts
            )
        }
    )

    with pytest.raises(CommandValidationError, match="não altera entidade publicada"):
        _import(env, changed, "cmd-bsdd-colide", base_release=base)
    assert env.publication.list_published()[0].release == base


def test_explicit_synthetic_ifc_mapping_needs_review_and_never_enables_writing(
    tmp_path: Path,
) -> None:
    staged = _staged(tmp_path)
    assert staged.content is not None
    concept = next(c for c in staged.content.concepts if c.labels[0].text == "Acabamento")
    rule = ApplicabilityRule(
        id=RULE_ID,
        entity_classes=("IfcWall",),
        include_subtypes=False,
        lifecycle="draft",
        source_assertion_ids=concept.source_assertion_ids,
    )
    binding = IFCBinding(
        id=BINDING_ID,
        concept_id=concept.id,
        applicability_rule_id=RULE_ID,
        declared_schemas=("IFC4",),
        carrier_kind="property",
        set_name="SYN_Conjunto",
        field_name="SYN_Acabamento",
        set_kind="custom",
        ifc_type="IfcLabel",
        scope="unspecified",
        carrier_status="approved",
        value_set_id=concept.value_set_id,
        lifecycle="draft",
        source_assertion_ids=concept.source_assertion_ids,
        notes="Mapeamento explícito SINTÉTICO escrito pelo teste; o importador não o cria.",
    )
    mapped = staged.content.model_copy(
        update={"applicability_rules": (rule,), "bindings": (binding,)}
    )
    env = make_env(tmp_path)
    head = _import(env, mapped, "cmd-bsdd-map")
    report = env.curation.validate_draft(head.draft.draft_id)
    stored = env.curation.get_revision(head.draft.draft_id, 1).content

    assert stored.bindings[0].write_enabled is False
    assert stored.bindings[0].lifecycle == "draft"
    assert report.content_sha256 == head.content_sha256
    assert staged.content.bindings == ()


def test_cli_writes_verified_staging_and_delta_without_catalog_writes(tmp_path: Path) -> None:
    src = tmp_path / "source.json"
    src.write_text(
        json.dumps(source().model_dump(mode="json"), ensure_ascii=False), encoding="utf-8"
    )
    newer = payload()
    newer["DictionaryVersion"] = "1.1"
    newer["Properties"][2]["Name"] = "Ativo (renomeado)"
    (tmp_path / "v11.json").write_text(json.dumps(newer, ensure_ascii=False), encoding="utf-8")

    assert (
        main(["--input", str(FIXTURE), "--source", str(src), "--out", str(tmp_path / "v10")]) == 0
    )
    assert (
        main(
            [
                "--input",
                str(tmp_path / "v11.json"),
                "--source",
                str(src),
                "--out",
                str(tmp_path / "v11"),
                "--previous",
                str(tmp_path / "v10"),
            ]
        )
        == 0
    )
    reopened = read_bsdd_staging(tmp_path / "v11")

    assert reopened.diff is not None
    assert {c.code_literal for c in reopened.diff.changed} == {"syn-ativo"}
    assert reopened.migrations
    assert all(m.status == "pending_curation" for m in reopened.migrations)
    assert (
        json.loads((tmp_path / "v11" / "report.json").read_text(encoding="utf-8"))[
            "distribution_gate"
        ]
        == "blocked_terms_unknown"
    )
