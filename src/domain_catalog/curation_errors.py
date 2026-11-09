"""Erros tipados da curadoria e da publicação do catálogo (E2: M1-08/M1-09).

Ficam fora de ``errors.py`` (E1) para não alterar o contrato já revisado. Cada erro
carrega ``code`` estável; nenhum deles significa sucesso parcial: quando um comando
falha, nada do seu efeito fica gravado, e a causa volta explícita para quem chamou.
"""

from collections.abc import Sequence

from src.domain_catalog.errors import CatalogError, ContentIssue


class CurationError(CatalogError):
    """Base dos erros de curadoria e publicação."""

    code = "curation_error"


class ActorContextError(CurationError):
    """Contexto de ator desconhecido, malformado ou com garantia não suportada no MVP."""

    code = "actor_context"


class ActorNotAllowedError(CurationError):
    """Ator sem permissão para a operação (tipo de ator ou responsável não declarado)."""

    code = "actor_not_allowed"


class CommandValidationError(CurationError):
    """Dados do comando inválidos (campo vazio, tipo errado); nada é gravado."""

    code = "invalid_command"


class CurationNotFoundError(CurationError, LookupError):
    """Solicitação, rascunho, revisão, candidato ou publicação inexistente."""

    code = "not_found"


class InvalidTransitionError(CurationError):
    """Transição de estado não permitida a partir do estado atual."""

    code = "invalid_transition"


class RevisionConflictError(CurationError):
    """Revisão esperada difere da atual: nada é sobrescrito, e o trabalho volta a quem chamou."""

    code = "revision_conflict"

    def __init__(self, message: str, *, expected: int, current: int) -> None:
        """Guarda a revisão esperada e a atual para a conciliação explícita."""
        self.expected = expected
        self.current = current
        super().__init__(message)


class ContentHashMismatchError(CurationError):
    """O hash informado não corresponde ao conteúdo exato da revisão."""

    code = "content_hash_mismatch"


class IdempotencyConflictError(CurationError):
    """Mesma chave de comando com operação, ator ou conteúdo diferentes."""

    code = "idempotency_conflict"


class DraftPatchError(CurationError):
    """Patch de rascunho inválido; nenhuma operação do patch é aplicada."""

    code = "invalid_patch"

    def __init__(self, issues: Sequence[ContentIssue]) -> None:
        """Guarda os problemas por entidade e campo."""
        self.issues: tuple[ContentIssue, ...] = tuple(issues)
        lines = [
            f"- {issue.code}: {issue.entity_kind} {issue.entity_id}"
            + (f".{issue.field}" if issue.field else "")
            + f" — {issue.message}"
            for issue in self.issues
        ]
        super().__init__("patch de rascunho inválido:\n" + "\n".join(lines))


class ValidationGateError(CurationError):
    """Validação da revisão com erro bloqueante; a ação pedida não é registrada."""

    code = "validation_failed"


class CandidateMismatchError(CurationError):
    """Versão ou hash do candidato informados não são os do candidato exato."""

    code = "candidate_mismatch"


class PublicationGateError(CurationError):
    """Publicação recusada por um portão (aprovação, base, versão, pendências)."""

    code = "publication_refused"


class BaseSupersededError(PublicationGateError):
    """O release-base não é mais o último publicado do catálogo; nada é publicado sobre ele.

    Exige reconciliação explícita: abandonar a intenção, se houver, e refazer o
    rascunho a partir do release atual. Bytes já gravados são preservados.
    """

    code = "base_superseded"


class PublicationInProgressError(PublicationGateError):
    """Já há publicação em andamento no mesmo catálogo; a linha está reservada para ela.

    A intenção registrada reserva o catálogo até ser concluída ou abandonada.
    """

    code = "publication_in_progress"


class PublicationIncompleteError(CurationError):
    """Publicação interrompida depois da intenção registrada; nada foi disponibilizado.

    O release só existe quando o recibo é gravado. A intenção fica identificável para
    retomada ou abandono explícitos; nenhum estado intermediário vale como publicação.
    """

    code = "publication_incomplete"

    def __init__(self, message: str, *, intent_id: str, phase: str) -> None:
        """Guarda a intenção e a fase em que a publicação parou."""
        self.intent_id = intent_id
        self.phase = phase
        super().__init__(message)
