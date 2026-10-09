"""Modelos da revisão humana por elemento IFC, base da revisão visual.

A decisão do engenheiro é a única porta para escrita no IFC: só ``accepted`` e
``edited`` autorizam escrita, sempre com revisor identificado.
"""

from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from src.foundation.locality import ensure_local_endpoint

ReviewVerdict = Literal["accepted", "edited", "rejected"]


class ElementReviewItem(BaseModel):
    """Um elemento IFC na fila de revisão, com as issues e sugestões a decidir."""

    guid: str = Field(min_length=22, max_length=22, description="GlobalId IFC do elemento")
    ifc_class: str = Field(description="Classe IFC, ex.: IfcWall")
    name: str | None = Field(default=None, description="Nome do elemento no modelo")
    issue_ids: list[str] = Field(default_factory=list)
    suggestion_ids: list[str] = Field(default_factory=list)
    viewer_ref: str | None = Field(
        default=None,
        description="Referência local da visualização: caminho de arquivo ou URL local",
    )

    @field_validator("viewer_ref")
    @classmethod
    def _viewer_ref_is_local(cls, value: str | None) -> str | None:
        """URLs de visualização precisam ser locais; caminhos de arquivo passam direto."""
        if value and "://" in value:
            ensure_local_endpoint(value)
        return value


class ReviewDecision(BaseModel):
    """Decisão do engenheiro sobre a sugestão de uma issue em um elemento."""

    issue_id: str = Field(min_length=1)
    guid: str = Field(min_length=22, max_length=22, description="GlobalId IFC do elemento")
    verdict: ReviewVerdict
    reviewer: str = Field(min_length=1, description="Quem decidiu, para rastreabilidade")
    edited_value: str | None = Field(default=None, description="Valor final quando editado")
    note: str | None = None
    decided_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _edited_requires_value(self) -> Self:
        """Uma edição sem o valor editado não pode ser aplicada nem auditada."""
        if self.verdict == "edited" and not self.edited_value:
            raise ValueError("decisão 'edited' exige edited_value")
        return self

    @property
    def allows_write(self) -> bool:
        """Só decisões aceitas ou editadas autorizam escrita no IFC."""
        return self.verdict in ("accepted", "edited")
