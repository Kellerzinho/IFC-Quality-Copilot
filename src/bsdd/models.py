"""Modelos estruturados para resolucao canonica via bSDD."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BSDDResolvedItem(BaseModel):
    """Resultado estruturado de resolucao semantica via bSDD."""

    canonical_uri: str | None = None
    display_name: str
    code: str | None = None
    dictionary_uri: str | None = None
    source_origin: str
    status: str
    review_required: bool = False
    aliases: list[str] = Field(default_factory=list)


class BSDDClassData(BSDDResolvedItem):
    """Classe resolvida no bSDD."""

    class_uri: str | None = None
    dictionary_name: str | None = None
    description: str | None = None


class BSDDPropertyData(BSDDResolvedItem):
    """Propriedade resolvida no bSDD."""

    property_uri: str | None = None
    data_type: str | None = None
    unit: str | None = None
    allowed_values: list[str] | None = None
    description: str | None = None
