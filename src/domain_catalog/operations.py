"""Registro de capacidades de operação (M1-05).

O cadastro referencia operações apenas por ID e versão. Quem declara que uma
operação existe é o código que a implementa e testa (M2/M3), ao registrar sua
``OperationSpec``. O registro informa disponibilidade; nunca importa, avalia ou
executa nada. Nesta etapa nenhuma operação do novo fluxo está implementada: o
registro padrão é vazio e toda política fica indisponível, sem fallback para
inferência livre.
"""

from collections.abc import Iterable
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from src.domain_catalog.contracts import OperationCapability
from src.domain_catalog.models import NonEmptyText

OperationId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_.]*$")]


class OperationSpec(BaseModel):
    """Operação implementada no código, com insumos, precondições e testes que a sustentam."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: OperationId
    version: NonEmptyText
    description: NonEmptyText
    inputs: tuple[NonEmptyText, ...]
    output: NonEmptyText
    preconditions: tuple[NonEmptyText, ...] = ()
    implementation: NonEmptyText
    """Referência documental ao código (``módulo:função``); o registro não a importa."""
    tests: tuple[NonEmptyText, ...] = Field(min_length=1)


class OperationRegistry:
    """Operações disponíveis nesta instalação, indexadas por ID."""

    def __init__(self, specs: Iterable[OperationSpec] = ()) -> None:
        """Indexa as especificações; ID repetido é erro de registro."""
        self._specs: dict[str, OperationSpec] = {}
        for spec in specs:
            if spec.operation_id in self._specs:
                raise ValueError(f"operação duplicada no registro: {spec.operation_id}")
            self._specs[spec.operation_id] = spec

    @property
    def operation_ids(self) -> tuple[str, ...]:
        """IDs registrados em ordem estável."""
        return tuple(sorted(self._specs))

    def capability(self, operation_id: str, version: str | None = None) -> OperationCapability:
        """Disponibilidade da operação; ausente ou de outra versão não está disponível."""
        spec = self._specs.get(operation_id)
        if spec is None:
            return OperationCapability(
                operation_id=operation_id,
                requested_version=version,
                status="unsupported",
                available_version=None,
                reason="operação não implementada no código; sem enriquecimento até existir "
                "implementação versionada e testada",
            )
        if version is not None and version != spec.version:
            return OperationCapability(
                operation_id=operation_id,
                requested_version=version,
                status="version_mismatch",
                available_version=spec.version,
                reason=f"versão {version} pedida; registrada {spec.version}",
            )
        return OperationCapability(
            operation_id=operation_id,
            requested_version=version,
            status="available",
            available_version=spec.version,
            reason=f"implementação registrada: {spec.implementation}",
        )


DEFAULT_OPERATION_REGISTRY = OperationRegistry()
"""Registro desta instalação: vazio até M2/M3 registrarem operações testadas."""
