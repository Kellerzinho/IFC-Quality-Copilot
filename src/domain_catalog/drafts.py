"""Arquivo de rascunho de curadoria para revisão humana (amostra da E1).

Um rascunho reúne propostas (conceitos, usos, regras, políticas, decisões) que citam
assertivas de fonte por ID. Ele declara sobre qual revisão da fonte foi feito; se a
fonte mudar, o rascunho é recusado até ser revisto. Rascunho nunca vira release: o
estado pendente do envelope precisa coincidir com o estado de cada proposta, de modo
que o conteúdo devolvido seja sempre recusado pela validação de release. O
armazenamento e o fluxo de curadoria duráveis pertencem à M1-08/M1-09.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from src.domain_catalog.canonical import CanonicalJSONError, parse_json_strict
from src.domain_catalog.content import ENTITY_KINDS, CatalogContent, validate_content
from src.domain_catalog.models import (
    FormatVersionOne,
    NonEmptyText,
    SourceArtifact,
    SourceAssertion,
)

_SOURCE_KINDS = frozenset({"source_artifacts", "source_assertions"})
_PROPOSAL_KINDS = frozenset(ENTITY_KINDS) - _SOURCE_KINDS

DraftStatus = Literal["draft_pending_review"]
_PROPOSAL_LIFECYCLES: dict[str, frozenset[str]] = {"draft_pending_review": frozenset({"draft"})}
"""Estados cadastrais admitidos nas propostas de cada estado de envelope."""


class DraftFormatError(ValueError):
    """Rascunho ilegível, de formato desconhecido ou com entidade inválida."""


class DraftBaseMismatchError(DraftFormatError):
    """Rascunho feito sobre outra revisão da fonte; precisa ser revisto antes do uso."""


class DraftStateError(DraftFormatError):
    """Propostas em estado incompatível com o envelope; nada é promovido nem corrigido."""


class DraftDocument(BaseModel):
    """Envelope do rascunho: estado, base de fonte, perguntas de revisão e propostas."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format: Literal["ifcqc-catalog-draft"]
    format_version: FormatVersionOne
    status: DraftStatus
    title: NonEmptyText
    based_on: dict[str, str]
    review_questions: tuple[NonEmptyText, ...]
    entities: dict[str, list[dict[str, Any]]]


def _read_document(path: Path) -> DraftDocument:
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DraftFormatError(f"rascunho {path.name} não é UTF-8: {exc}") from exc
    try:
        return DraftDocument.model_validate(parse_json_strict(text))
    except (CanonicalJSONError, ValidationError) as exc:
        raise DraftFormatError(f"rascunho inválido em {path.name}: {exc}") from exc


def _check_proposal_states(document: DraftDocument, proposals: CatalogContent, name: str) -> None:
    """Toda proposta com estado cadastral está no estado do envelope, e há ao menos uma.

    Um rascunho pendente que trouxesse entidades aprovadas (copiadas de um release ou
    com estado antigo), ou nenhuma proposta em ``draft``, devolveria conteúdo aceito
    pela validação de release. Recusa em vez de rebaixar o estado em silêncio.
    """
    allowed = _PROPOSAL_LIFECYCLES[document.status]
    states = [
        (kind, str(getattr(entity, "id", "")), lifecycle)
        for kind, entity in proposals.iter_entities()
        if (lifecycle := getattr(entity, "lifecycle", None)) is not None
    ]
    wrong = [item for item in states if item[2] not in allowed]
    if wrong:
        listed = "; ".join(
            f"{kind} {entity_id} em {lifecycle}" for kind, entity_id, lifecycle in wrong
        )
        raise DraftStateError(
            f"{name} está em {document.status}, que só admite propostas em "
            f"{sorted(allowed)}: {listed}"
        )
    if not states:
        raise DraftStateError(f"{name} está em {document.status} sem nenhuma proposta em draft")


def load_draft(
    path: Path,
    *,
    source_artifacts: Sequence[SourceArtifact],
    source_assertions: Sequence[SourceAssertion],
    expected_base: Mapping[str, str],
) -> CatalogContent:
    """Monta conteúdo de rascunho com as assertivas citadas e valida as referências.

    O conteúdo devolvido tem ao menos uma proposta e todas em ``draft``; por isso a
    validação de release (``validate_content(for_release=True)``) sempre o recusa.
    """
    document = _read_document(path)
    if document.based_on != dict(expected_base):
        raise DraftBaseMismatchError(
            f"rascunho baseado em {document.based_on}, fonte atual {dict(expected_base)}"
        )
    unknown = sorted(set(document.entities) - _PROPOSAL_KINDS)
    if unknown:
        raise DraftFormatError(f"tipos não aceitos em rascunho: {unknown}")
    try:
        proposals = CatalogContent.model_validate(document.entities)
    except ValidationError as exc:
        raise DraftFormatError(f"proposta inválida em {path.name}: {exc}") from exc
    _check_proposal_states(document, proposals, path.name)
    cited = {
        assertion_id
        for _, entity in proposals.iter_entities()
        for assertion_id in getattr(entity, "source_assertion_ids", ())
    }
    assertions = tuple(a for a in source_assertions if a.id in cited)
    artifact_ids = {a.source_artifact_id for a in assertions} | {
        a.transcription_artifact_id for a in assertions if a.transcription_artifact_id
    }
    content = proposals.model_copy(
        update={
            "source_artifacts": tuple(a for a in source_artifacts if a.id in artifact_ids),
            "source_assertions": assertions,
        }
    )
    validate_content(content, for_release=False)
    return content
