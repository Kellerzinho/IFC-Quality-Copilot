"""Envelope de rascunho de curadoria (amostra da E1); rascunhos SINTÉTICOS em ``tmp_path``.

Um rascunho pendente de revisão nunca fornece conteúdo publicável: o carregador
recusa propostas em estado incompatível com o envelope, sem promover nem corrigir
estados em silêncio. A amostra real de Daiane é testada em ``test_daiane_sample.py``.
"""

from pathlib import Path
from typing import Any

import pytest

from src.domain_catalog.canonical import canonical_json_bytes
from src.domain_catalog.content import CatalogContent, validate_content
from src.domain_catalog.drafts import DraftFormatError, DraftStateError, load_draft
from src.domain_catalog.errors import CatalogValidationError
from src.domain_catalog.models import LifecycleState
from tests.domain_catalog import factories as f

_BASE = {"synthetic": "1"}


def _proposals(lifecycle: LifecycleState = "draft") -> dict[str, Any]:
    """Propostas sintéticas no estado pedido, sem as assertivas de fonte."""
    data = f.minimal_content(lifecycle=lifecycle).model_dump(mode="json")
    data.pop("source_artifacts")
    data.pop("source_assertions")
    return data


def _write(tmp_path: Path, entities: dict[str, Any] | None = None, **envelope: object) -> Path:
    document: dict[str, object] = {
        "format": "ifcqc-catalog-draft",
        "format_version": 1,
        "status": "draft_pending_review",
        "title": "Rascunho SINTÉTICO de teste",
        "based_on": _BASE,
        "review_questions": ["Pergunta sintética pendente"],
        "entities": _proposals() if entities is None else entities,
    }
    document.update(envelope)
    path = tmp_path / "rascunho-sintetico.json"
    path.write_bytes(canonical_json_bytes(document))
    return path


def _load(path: Path) -> CatalogContent:
    source = f.minimal_content()
    return load_draft(
        path,
        source_artifacts=source.source_artifacts,
        source_assertions=source.source_assertions,
        expected_base=_BASE,
    )


def test_pending_draft_with_draft_proposals_loads_but_is_never_publishable(
    tmp_path: Path,
) -> None:
    content = _load(_write(tmp_path))

    validate_content(content, for_release=False)
    with pytest.raises(CatalogValidationError) as exc:
        f.build_synthetic_release(content)
    assert {issue.code for issue in exc.value.issues} == {"lifecycle_not_publishable"}


@pytest.mark.parametrize("lifecycle", ["approved", "deprecated", "reviewed"])
def test_pending_draft_refuses_proposals_in_another_state(
    tmp_path: Path, lifecycle: LifecycleState
) -> None:
    # Revisão E1-03: envelope pendente com filhos aprovados fornecia conteúdo publicável.
    path = _write(tmp_path, _proposals(lifecycle))

    with pytest.raises(DraftStateError, match=lifecycle):
        _load(path)


def test_state_error_is_a_draft_format_error(tmp_path: Path) -> None:
    with pytest.raises(DraftFormatError):
        _load(_write(tmp_path, _proposals("approved")))


def _decision_only() -> dict[str, Any]:
    decision = (
        f.resolution_content()
        .reconciliation_decisions[0]
        .model_copy(update={"affected_binding_ids": ()})
    )
    return {"reconciliation_decisions": [decision.model_dump(mode="json")]}


@pytest.mark.parametrize(
    "entities", [{}, _decision_only()], ids=["sem-propostas", "somente-decisao"]
)
def test_pending_draft_without_a_draft_proposal_is_refused(
    tmp_path: Path, entities: dict[str, Any]
) -> None:
    # Sem nenhuma proposta em draft, o conteúdo devolvido passaria pela validação de release.
    with pytest.raises(DraftStateError):
        _load(_write(tmp_path, entities))


@pytest.mark.parametrize("version", [True, 1.0], ids=["booleano", "float"])
def test_draft_format_version_must_be_the_integer_one(tmp_path: Path, version: object) -> None:
    # Revisão E1-09, negativo do rascunho.
    with pytest.raises(DraftFormatError, match="format_version"):
        _load(_write(tmp_path, format_version=version))


@pytest.mark.parametrize(
    "payload",
    [
        b'{"a":[' + b"1" * 5000 + b"]}\n",
        b'{"a":' + b"[" * 5000 + b"0" + b"]" * 5000 + b"}\n",
        b'{"a":"\xff"}\n',
    ],
    ids=["inteiro-excessivo", "aninhamento-excessivo", "nao-utf8"],
)
def test_unreadable_draft_is_a_draft_format_error(tmp_path: Path, payload: bytes) -> None:
    # Revisão E1-04, negativo do rascunho: antes escapavam ValueError, RecursionError e
    # UnicodeDecodeError.
    path = tmp_path / "rascunho-ilegivel.json"
    path.write_bytes(payload)

    with pytest.raises(DraftFormatError):
        _load(path)
