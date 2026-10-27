"""Erros tipados do catálogo de domínio.

Cada erro carrega ``code`` estável para que consumidores (M2, M3, M4) distingam a
causa sem interpretar mensagens. Falha de catálogo nunca é convertida em
"nenhum resultado": quem chama decide, com a causa explícita, o que pode continuar.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from src.domain_catalog.contracts import CatalogReleaseRef, ResolutionResult


class ContentIssue(BaseModel):
    """Problema de conteúdo localizado por entidade e campo."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    entity_kind: str
    entity_id: str
    field: str | None
    message: str


class CatalogError(Exception):
    """Base dos erros do catálogo."""

    code: str = "catalog_error"


class CatalogValidationError(CatalogError):
    """Conteúdo do catálogo inconsistente; lista todos os problemas encontrados."""

    code = "invalid_content"

    def __init__(self, issues: Sequence[ContentIssue]) -> None:
        """Guarda os problemas e monta uma mensagem legível com cada um."""
        self.issues: tuple[ContentIssue, ...] = tuple(issues)
        lines = [
            f"- {issue.code}: {issue.entity_kind} {issue.entity_id}"
            + (f".{issue.field}" if issue.field else "")
            + f" — {issue.message}"
            for issue in self.issues
        ]
        super().__init__("conteúdo do catálogo inválido:\n" + "\n".join(lines))


class CatalogEntityNotFoundError(CatalogError, LookupError):
    """ID inexistente no release consultado; diferente de ambiguidade ou erro de pacote."""

    code = "entity_not_found"


PackageErrorReason = Literal["not_found", "integrity", "format", "layout", "limit", "content", "io"]
"""Causa da recusa de um pacote; nenhuma delas autoriza fallback ou catálogo vazio.

``io`` é falha do sistema de arquivos durante a abertura (permissão, bloqueio por
outro processo, arquivo removido no meio da leitura); a causa original fica
encadeada em ``__cause__``.
"""


class CatalogPackageError(CatalogError):
    """Pacote ausente, adulterado, malformado ou inconsistente: não é aberto."""

    code = "package_error"

    def __init__(
        self, reason: PackageErrorReason, message: str, issues: Sequence[ContentIssue] = ()
    ) -> None:
        """Guarda a causa estruturada e, se houver, os problemas de conteúdo."""
        self.reason: PackageErrorReason = reason
        self.issues: tuple[ContentIssue, ...] = tuple(issues)
        super().__init__(f"[{reason}] {message}")


ProjectionErrorReason = Literal[
    "release_mismatch",
    "insufficient_context",
    "unresolved_binding",
    "unsupported_carrier",
    "unrepresentable_enum",
    "foreign_reference",
    "unsupported_domain",
]


class CatalogProjectionError(CatalogError):
    """Projeção indisponível, com identidade e resolução original quando obtida."""

    code = "projection_unavailable"

    def __init__(
        self,
        reason: ProjectionErrorReason,
        message: str,
        *,
        catalog: "CatalogReleaseRef",
        resolution: "ResolutionResult | None" = None,
    ) -> None:
        """Guarda a causa sem fabricar resolução ou eliminar candidatos."""
        self.reason = reason
        self.catalog = catalog
        self.resolution = resolution
        super().__init__(f"[{reason}] {message}")


ComparisonErrorReason = Literal[
    "catalog_id_mismatch", "version_hash_collision", "impact_limit_exceeded"
]
"""Recusa da comparação entre releases (E3.2a); nunca acompanha ``CatalogDiff`` parcial."""


class CatalogComparisonError(CatalogError):
    """Comparação recusada: catálogos distintos, colisão de versão ou limite de impacto.

    Distinta de ``CatalogPackageError``: os pacotes abriram íntegros, mas o par não é
    comparável (ou o fechamento excede o limite). Nenhum diff é devolvido.
    """

    code = "comparison_refused"

    def __init__(
        self,
        reason: ComparisonErrorReason,
        message: str,
        *,
        old_ref: "CatalogReleaseRef",
        new_ref: "CatalogReleaseRef",
        limit: int | None = None,
    ) -> None:
        """Guarda motivo, referências exatas e o limite (só em ``impact_limit_exceeded``)."""
        self.reason: ComparisonErrorReason = reason
        self.old_ref = old_ref
        self.new_ref = new_ref
        self.limit = limit
        super().__init__(f"[{reason}] {message}")
