"""Linha de publicação do catálogo: reserva e base conferida na conclusão (achado E2-01).

O histórico de releases de um catálogo é linear: cada release parte do último publicado.
Duas defesas, e nenhuma depende de chamadas serializadas por quem usa o serviço:

1. **Reserva da linha:** a intenção registrada reserva o catálogo; enquanto ela não for
   concluída ou abandonada, nenhuma outra publicação do mesmo catálogo começa (plano M6
   §7.1: uma reserva por escopo, a segunda recebe conflito).
2. **Conferência na conclusão:** a intenção conserva a identidade do que foi decidido,
   não congela a validade da base. Antes de promover e de novo na transação do recibo,
   a conclusão confere intenção, aprovação exata, base ainda a última publicada e versão
   livre (plano M6 §7.2, passos 4 e 6). Base superada é ``BaseSupersededError`` e exige
   reconciliação explícita; os bytes já gravados são preservados.

Os testes da segunda defesa contornam a reserva de propósito, para simular o que ela
existe para impedir: um armazenamento sem serialização ou uma intenção gravada antes
desta correção. Conteúdo, catálogo e atores SINTÉTICOS; adaptadores de teste não
operacionais.
"""

from pathlib import Path

import pytest

from src.domain_catalog.contracts import CatalogReleaseRef
from src.domain_catalog.curation_errors import (
    BaseSupersededError,
    CurationNotFoundError,
    InvalidTransitionError,
    PublicationGateError,
    PublicationIncompleteError,
    PublicationInProgressError,
)
from src.domain_catalog.curation_models import (
    CommandMeta,
    CommandOutcome,
    PublicationReceipt,
    ReleaseCandidate,
)
from src.domain_catalog.draft_store import CurationTransaction
from src.domain_catalog.package import ComponentTerms
from src.domain_catalog.publication import PublicationService
from tests.domain_catalog import factories as f
from tests.domain_catalog.curation_adapters import CurationEnv, make_env

TERMS = (ComponentTerms(component="conteúdo", terms="sintético, sem terceiros"),)


def _meta(command_id: str, actor: str) -> CommandMeta:
    return CommandMeta(command_id=command_id, actor_context_id=actor)


def _definition(tag: str) -> str:
    return f"Definição sintética {tag}."


def _candidate(env: CurationEnv, tag: str, version: str) -> ReleaseCandidate:
    """Rascunho sintético sem base, com definição própria, aprovado e preparado."""
    concept = f.concept("draft").model_copy(update={"definition": f.pt(_definition(tag))})
    head = env.curation.import_draft(
        _meta(f"cmd-imp-{tag}", env.importer),
        title=f"Proposta sintética {tag}",
        catalog=f.catalog_identity(),
        content=f.minimal_content("draft").model_copy(update={"concepts": (concept,)}),
        source_label="fixture sintética",
        reason="propostas sintéticas",
    ).value
    env.curation.submit_for_review(
        _meta(f"cmd-sub-{tag}", env.curator),
        draft_id=head.draft.draft_id,
        revision=1,
        content_sha256=head.content_sha256,
        reason="pronto",
    )
    env.curation.review_draft(
        _meta(f"cmd-apr-{tag}", env.curator),
        draft_id=head.draft.draft_id,
        revision=1,
        content_sha256=head.content_sha256,
        verdict="approve",
        justification="Conteúdo sintético conferido para o teste.",
    )
    return env.publication.prepare_release(
        _meta(f"cmd-prp-{tag}", env.curator),
        draft_id=head.draft.draft_id,
        revision=1,
        content_sha256=head.content_sha256,
        version=version,
        terms=TERMS,
        reason="preparar",
    ).value


def _publish(
    env: CurationEnv, candidate: ReleaseCandidate, tag: str
) -> CommandOutcome[PublicationReceipt]:
    return env.publication.publish(
        _meta(f"cmd-pub-{tag}", env.curator),
        candidate_id=candidate.candidate_id,
        version=candidate.release.version,
        manifest_sha256=candidate.release.manifest_sha256,
        justification="Publicação sintética de teste.",
    )


def _interrupted(env: CurationEnv, candidate: ReleaseCandidate, tag: str) -> str:
    """Publicação interrompida antes de promover; devolve a intenção que ficou registrada."""
    env.artifacts.fail_at.add("promote")
    with pytest.raises(PublicationIncompleteError) as stopped:
        _publish(env, candidate, tag)
    env.artifacts.fail_at.clear()
    return stopped.value.intent_id


def _without_reservation(
    service: PublicationService, tx: CurationTransaction, candidate: ReleaseCandidate
) -> None:
    """Reserva contornada: simula armazenamento sem serialização ou intenção anterior.

    Aplicada com ``raising=False``: antes da correção não havia reserva a contornar. Se o
    método for renomeado, a reserva volta a valer e os testes falham na publicação de A.
    """


def _published(env: CurationEnv) -> list[CatalogReleaseRef]:
    return [receipt.release for receipt in env.publication.list_published()]


# --- reserva da linha ----------------------------------------------------------------------


def test_pending_publication_reserves_the_catalog_line(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    a = _candidate(env, "a", "1.0.0")
    b = _candidate(env, "b", "2.0.0")
    intent_b = _interrupted(env, b, "b")

    with pytest.raises(PublicationInProgressError) as refused:
        _publish(env, a, "a")

    assert intent_b in str(refused.value)
    assert _published(env) == []
    assert env.publication.get_candidate(a.candidate_id).state == "prepared"
    assert not env.artifacts.release_path(a.release).exists()
    assert env.curation.get_command("cmd-pub-a") is None
    env.publication.resume_publication(
        _meta("cmd-res-b", env.curator), intent_id=intent_b, reason="retomar a publicação"
    )
    assert _published(env) == [b.release]
    with pytest.raises(BaseSupersededError):
        _publish(env, a, "a-2")
    assert _published(env) == [b.release]


def test_abandoning_frees_the_line_and_the_abandoned_intent_cannot_finish(
    tmp_path: Path,
) -> None:
    env = make_env(tmp_path)
    a = _candidate(env, "a", "1.0.0")
    b = _candidate(env, "b", "2.0.0")
    intent_b = _interrupted(env, b, "b")
    env.publication.abandon_publication(
        _meta("cmd-abd-b", env.curator), intent_id=intent_b, reason="desistir de B"
    )

    _publish(env, a, "a")

    with pytest.raises(InvalidTransitionError):
        env.publication.resume_publication(
            _meta("cmd-res-b", env.curator), intent_id=intent_b, reason="retomar B"
        )
    with pytest.raises(InvalidTransitionError, match="abandonada"):
        _publish(env, b, "b")
    with pytest.raises(BaseSupersededError):
        _publish(env, b, "b-2")
    assert _published(env) == [a.release]
    content = env.publication.open_published(a.release).content
    assert content.concepts[0].definition[0].text == _definition("a")


def test_publication_attempted_inside_the_promotion_interval_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = make_env(tmp_path)
    a = _candidate(env, "a", "1.0.0")
    b = _candidate(env, "b", "2.0.0")
    promote = env.artifacts.promote
    outcomes: list[PublicationGateError] = []

    def promote_with_interleaving(candidate_id: str, ref: CatalogReleaseRef) -> Path:
        if candidate_id == b.candidate_id:
            try:
                _publish(env, a, "a")
            except PublicationGateError as exc:
                outcomes.append(exc)
        return promote(candidate_id, ref)

    monkeypatch.setattr(env.artifacts, "promote", promote_with_interleaving)

    receipt = _publish(env, b, "b").value

    assert [type(exc) for exc in outcomes] == [PublicationInProgressError]
    assert receipt.release == b.release
    assert _published(env) == [b.release]
    assert not env.artifacts.release_path(a.release).exists()


# --- conferência na conclusão (reserva contornada de propósito) ------------------------------


@pytest.mark.parametrize("retry", ["resume", "replay"])
def test_completion_refuses_a_base_superseded_while_the_intent_was_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, retry: str
) -> None:
    env = make_env(tmp_path)
    a = _candidate(env, "a", "1.0.0")
    b = _candidate(env, "b", "2.0.0")
    intent_b = _interrupted(env, b, "b")
    with monkeypatch.context() as bypass:
        bypass.setattr(
            PublicationService, "_check_catalog_line_free", _without_reservation, raising=False
        )
        _publish(env, a, "a")

    def complete_b() -> CommandOutcome[PublicationReceipt]:
        if retry == "resume":
            return env.publication.resume_publication(
                _meta("cmd-res-b", env.curator), intent_id=intent_b, reason="retomar B"
            )
        return _publish(env, b, "b")

    with pytest.raises(BaseSupersededError, match="abandon_publication"):
        complete_b()

    assert _published(env) == [a.release]
    assert not env.artifacts.release_path(b.release).exists()
    assert env.artifacts.staged_path(b.candidate_id) is not None
    assert env.publication.get_intent(intent_b).state == "recorded"
    content = env.publication.open_published(a.release).content
    assert content.concepts[0].definition[0].text == _definition("a")
    env.publication.abandon_publication(
        _meta("cmd-abd-b", env.curator), intent_id=intent_b, reason="base superada"
    )
    assert env.publication.inspect().pending_intents == ()
    assert env.artifacts.staged_path(b.candidate_id) is not None


def test_receipt_transaction_refuses_a_base_superseded_during_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = make_env(tmp_path)
    a = _candidate(env, "a", "1.0.0")
    b = _candidate(env, "b", "2.0.0")
    promote = env.artifacts.promote

    def promote_with_interleaving(candidate_id: str, ref: CatalogReleaseRef) -> Path:
        if candidate_id == b.candidate_id:
            _publish(env, a, "a")
        return promote(candidate_id, ref)

    monkeypatch.setattr(env.artifacts, "promote", promote_with_interleaving)
    monkeypatch.setattr(
        PublicationService, "_check_catalog_line_free", _without_reservation, raising=False
    )

    with pytest.raises(BaseSupersededError):
        _publish(env, b, "b")

    assert _published(env) == [a.release]
    final_b = env.artifacts.release_path(b.release)
    assert final_b.is_dir()
    with pytest.raises(CurationNotFoundError):
        env.publication.open_published(b.release)
    (pending,) = env.publication.inspect().pending_intents
    env.publication.abandon_publication(
        _meta("cmd-abd-b", env.curator), intent_id=pending.intent_id, reason="base superada"
    )
    assert not final_b.exists()
    assert len(env.artifacts.quarantined()) == 1
    assert env.publication.inspect().unregistered_releases == ()


def test_completion_refuses_an_approval_altered_outside_the_service(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    b = _candidate(env, "b", "1.0.0")
    intent_b = _interrupted(env, b, "b")
    with env.store.transaction() as tx:
        stored = tx.get("review", b.approval_id)
        assert stored is not None
        tx.replace(
            "review", b.approval_id, stored.version, {**stored.document, "verdict": "reject"}
        )

    with pytest.raises(PublicationGateError, match="aprovação"):
        env.publication.resume_publication(
            _meta("cmd-res-b", env.curator), intent_id=intent_b, reason="retomar B"
        )

    assert _published(env) == []
    assert not env.artifacts.release_path(b.release).exists()
