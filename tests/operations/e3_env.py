"""Ambiente E3 de teste com componentes REAIS e atores SINTÉTICOS declarados.

Monta autoridade operacional, adaptador ``CurationStore`` real, resolver de atores,
armazenamento de artefatos e porta de releases reais, e os serviços E2 existentes.
Publicações feitas aqui usam só conteúdo sintético (``synthetic_fixture``) em pastas
temporárias: geram recibo técnico real dos bytes de teste, não aprovação humana de
conteúdo real. Os nomes declarados são rótulos de teste, não pessoas.
"""

import uuid
from dataclasses import dataclass
from pathlib import Path

from src.artifacts.curation_adapter import LocalReleaseArtifactStore
from src.artifacts.storage import LocalArtifactStore
from src.domain_catalog.content import CatalogContent
from src.domain_catalog.contracts import CatalogReleaseRef
from src.domain_catalog.curation import CurationService
from src.domain_catalog.curation_models import (
    CommandMeta,
    DraftPatch,
    PublicationReceipt,
    UpsertEntity,
)
from src.domain_catalog.models import CatalogModel
from src.domain_catalog.package import ComponentTerms
from src.domain_catalog.publication import PublicationService
from src.operations.actor_context import ActorContextService
from src.operations.curation_adapter import SQLiteCurationStore
from src.operations.database import OperationalStore, StorePurpose
from tests.domain_catalog import factories as f
from tests.domain_catalog.curation_adapters import TEST_LIMITS

SYNTHETIC_CURATOR = "Pessoa Curadora Sintética Declarada (teste)"
TERMS = (ComponentTerms(component="conteúdo", terms="sintético, sem terceiros"),)


@dataclass
class RealEnv:
    """Componentes reais sobre uma pasta temporária."""

    base: Path
    store: OperationalStore
    artifacts: LocalArtifactStore
    releases: LocalReleaseArtifactStore
    curation_store: SQLiteCurationStore
    actors: ActorContextService
    curation: CurationService
    publication: PublicationService
    curator: str
    importer: str
    assistant: str


def make_real_env(base: Path, purpose: StorePurpose = "synthetic_test") -> RealEnv:
    """Abre (ou cria) a autoridade em ``base/db`` e os artefatos em ``base/a``."""
    store = OperationalStore.open(base / "db", purpose=purpose)
    artifacts = LocalArtifactStore(base / "a")
    releases = LocalReleaseArtifactStore(artifacts.publication_root())
    curation_store = SQLiteCurationStore(store)
    actors = ActorContextService(store)
    publication = PublicationService(curation_store, actors, releases, limits=TEST_LIMITS)
    curation = CurationService(curation_store, actors, releases=publication)
    return RealEnv(
        base=base,
        store=store,
        artifacts=artifacts,
        releases=releases,
        curation_store=curation_store,
        actors=actors,
        curation=curation,
        publication=publication,
        curator=actors.register(
            actor_kind="human", declared_name=SYNTHETIC_CURATOR
        ).actor_context_id,
        importer=actors.register(actor_kind="service", declared_name=None).actor_context_id,
        assistant=actors.register(actor_kind="assistant", declared_name=None).actor_context_id,
    )


def meta(actor: str) -> CommandMeta:
    """Comando E2 com chave nova (UUID textual) e ator referenciado."""
    return CommandMeta(command_id=str(uuid.uuid4()), actor_context_id=actor)


def approve_and_publish(env: RealEnv, draft_id: str, version: str) -> PublicationReceipt:
    head = env.curation.get_head(draft_id)
    env.curation.submit_for_review(
        meta(env.curator),
        draft_id=draft_id,
        revision=head.revision,
        content_sha256=head.content_sha256,
        reason="revisão sintética",
    )
    env.curation.review_draft(
        meta(env.curator),
        draft_id=draft_id,
        revision=head.revision,
        content_sha256=head.content_sha256,
        verdict="approve",
        justification="Conteúdo sintético conferido apenas para teste técnico.",
    )
    candidate = env.publication.prepare_release(
        meta(env.curator),
        draft_id=draft_id,
        revision=head.revision,
        content_sha256=head.content_sha256,
        version=version,
        terms=TERMS,
        reason="preparar release sintético",
    ).value
    return env.publication.publish(
        meta(env.curator),
        candidate_id=candidate.candidate_id,
        version=candidate.release.version,
        manifest_sha256=candidate.release.manifest_sha256,
        justification="Publicação sintética de teste técnico.",
    ).value


def publish_first(
    env: RealEnv, content: CatalogContent, version: str = "1.0.0"
) -> PublicationReceipt:
    """Importa conteúdo sintético em rascunho (estado ``draft``) e publica pelo serviço E2."""
    head = env.curation.import_draft(
        meta(env.importer),
        title=f"Release sintético {version}",
        catalog=f.catalog_identity(),
        content=content,
        source_label="fixture sintética",
        reason="conteúdo sintético de teste",
    ).value
    return approve_and_publish(env, head.draft.draft_id, version)


def publish_update(
    env: RealEnv,
    base: CatalogReleaseRef,
    changed: tuple[tuple[str, CatalogModel], ...],
    version: str,
) -> PublicationReceipt:
    """Novo release a partir de ``base``, com propostas (``draft``) para as entidades dadas."""
    head = env.curation.create_draft(
        meta(env.curator),
        title=f"Atualização sintética {version}",
        base_release=base,
        reason="atualização sintética",
    ).value
    if changed:
        patch = DraftPatch(
            operations=tuple(
                UpsertEntity(op="upsert", kind=kind, entity=entity.model_dump(mode="json"))  # type: ignore[arg-type]
                for kind, entity in changed
            ),
            reason="mudança sintética",
        )
        env.curation.edit_draft(
            meta(env.curator),
            draft_id=head.draft.draft_id,
            expected_revision=head.revision,
            patch=patch,
        )
    return approve_and_publish(env, head.draft.draft_id, version)
