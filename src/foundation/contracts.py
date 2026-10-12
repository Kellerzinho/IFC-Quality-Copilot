"""Contratos (Protocols) da fundação semântica.

Cada contrato marca uma fronteira da plataforma. As classes atuais que já têm a
forma certa estão citadas no docstring e verificadas em
``tests/foundation/test_contracts.py``. Forma não é aprovação: contrato descrito
como local só é cumprido por implementação que respeite ``src.foundation.locality``.
"""

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from src.bsdd.models import BSDDClassData, BSDDPropertyData
from src.foundation.review import ElementReviewItem, ReviewDecision
from src.models import (
    AuditEntry,
    BSDDContext,
    IDSContext,
    IDSSpecification,
    IFCElement,
    Issue,
)


@runtime_checkable
class SemanticCatalog(Protocol):
    """Catálogo semântico local, com classes e propriedades no formato do bSDD.

    ``BSDDClient`` tem esta forma, mas consulta a API pública do bSDD quando o cache
    não tem a resposta; por isso não cumpre a política de localidade. A plataforma
    precisa de uma implementação servida por snapshot local do dicionário.
    """

    def search_classes_text(self, query: str, domain: str = "IFC") -> list[BSDDClassData]:
        """Busca classes por texto livre."""
        ...

    def get_class_metadata(self, class_uri: str) -> BSDDClassData:
        """Metadados de uma classe pela URI canônica."""
        ...

    def resolve_property(self, property_uri: str) -> BSDDPropertyData:
        """Propriedade pela URI canônica, com tipo de dado e valores permitidos."""
        ...


@runtime_checkable
class ModelInspector(Protocol):
    """Leitura programática do modelo IFC. Atendido por ``IFCAnalyzer``."""

    def get_element(self, guid: str) -> IFCElement | None:
        """Elemento pelo GlobalId, ou ``None`` se não existir no modelo."""
        ...

    def get_model_summary(self) -> dict[str, Any]:
        """Resumo do modelo (contagens por classe, schema, metadados)."""
        ...


@runtime_checkable
class RequirementSource(Protocol):
    """Requisitos computáveis do IDS. Atendido por ``IDSFileRequirementSource``."""

    def specifications(self) -> list[IDSSpecification]:
        """Especificações IDS aplicáveis."""
        ...


@runtime_checkable
class GroundingContextBuilder(Protocol):
    """Contexto técnico (grounding) de uma issue para o LLM local.

    ``BSDDContextBuilder`` tem esta forma; os termos precisam vir do catálogo local.
    """

    def build(self, issue: Issue, ids_context: IDSContext | None = None) -> BSDDContext:
        """Monta o contexto da issue a partir do catálogo e do IDS."""
        ...


@runtime_checkable
class LocalLanguageModel(Protocol):
    """LLM servido localmente ou no servidor interno do IME.

    Atendido por ``OllamaClient``; valide o endpoint com ``require_local_model``.
    """

    base_url: str
    model: str

    def is_available(self) -> bool:
        """Se o servidor local responde."""
        ...

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Texto gerado e métricas do servidor."""
        ...


@runtime_checkable
class ElementReviewQueue(Protocol):
    """Fila da revisão visual por elemento. Sem implementação nesta etapa."""

    def pending(self, limit: int = 50) -> list[ElementReviewItem]:
        """Elementos com decisão pendente, em ordem de prioridade."""
        ...

    def record(self, decision: ReviewDecision) -> None:
        """Registra a decisão do engenheiro."""
        ...


@runtime_checkable
class IssueExporter(Protocol):
    """Exportação das issues para colaboração. Atendido por ``BCFExporter``."""

    def export(self, issues: list[Issue], output_path: Path) -> Path:
        """Grava o artefato e devolve o caminho final."""
        ...


@runtime_checkable
class AuditTrail(Protocol):
    """Trilha de auditoria separada do log técnico. Atendido por ``AuditLogger``."""

    def log(self, entry: AuditEntry) -> None:
        """Registra uma entrada; cada escrita no IFC gera uma."""
        ...

    def get_entries_for_element(self, guid: str) -> list[AuditEntry]:
        """Histórico de um elemento."""
        ...


@runtime_checkable
class EvaluationSuite(Protocol):
    """Métricas da avaliação científica. Atendido por ``IssueMetricsEvaluation``."""

    def evaluate(self, issues: list[Issue]) -> dict[str, Any]:
        """Métricas agregadas das issues revisadas."""
        ...
