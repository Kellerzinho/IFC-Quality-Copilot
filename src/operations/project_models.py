"""Projeto, modelo, par IFC–IDS e pin de catálogo persistidos na autoridade comum.

``ModelPairBinding`` é o conceito M4 de par; ``PairRef`` é apenas outro nome do mesmo
DTO, não uma terceira associação. ``ProjectCatalogPin`` é conteúdo M1 persistido aqui.
Revisões anteriores de fonte, par e pin são imutáveis; heads avançam por CAS.
"""

from typing import Self

from pydantic import StrictBool, model_validator

from src.domain_catalog.actor import ActorSnapshot
from src.domain_catalog.contracts import CatalogReleaseRef, ContractModel
from src.domain_catalog.models import NonEmptyText
from src.domain_catalog.package import UtcTimestamp
from src.domain_catalog.provenance import CatalogProvenance
from src.operations.contracts import (
    CanonicalUUID,
    NonNegativeInt,
    PositiveInt,
    SchemaVersionOne,
    SourceArtifactRef,
)

MAX_ACTIVE_PAIRS = 2
"""MVP: um ou dois pares ativos por projeto; o terceiro é recusado sem truncar."""


class ModelRecord(ContractModel):
    """Identidade lógica de um modelo pertencente a um projeto."""

    schema_version: SchemaVersionOne = 1
    project_id: CanonicalUUID
    model_id: CanonicalUUID
    discipline: NonEmptyText
    created_by_actor_context_id: CanonicalUUID
    created_at_utc: UtcTimestamp


class ModelPairBinding(ContractModel):
    """Revisão imutável de um par IFC–IDS de um modelo, confirmada por contexto local."""

    schema_version: SchemaVersionOne = 1
    project_id: CanonicalUUID
    model_id: CanonicalUUID
    pair_id: CanonicalUUID
    pair_revision: PositiveInt
    discipline: NonEmptyText
    ifc: SourceArtifactRef
    ids: SourceArtifactRef
    active: StrictBool
    confirmed_by_actor_context_id: CanonicalUUID

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Papéis corretos e as duas fontes do mesmo projeto e modelo do par."""
        if (self.ifc.role, self.ids.role) != ("ifc", "ids"):
            raise ValueError("par exige fonte ifc e fonte ids, nessa ordem")
        for ref in (self.ifc, self.ids):
            if (ref.project_id, ref.model_id) != (self.project_id, self.model_id):
                raise ValueError("fontes do par pertencem a outro projeto ou modelo")
        return self


PairRef = ModelPairBinding
"""Referência de par: o mesmo DTO, sem terceira associação."""


class ProjectRecord(ContractModel):
    """Head do projeto: revisão do conjunto de pares e os pares ativos ordenados."""

    schema_version: SchemaVersionOne = 1
    project_id: CanonicalUUID
    name: NonEmptyText
    pair_set_revision: NonNegativeInt
    active_pair_refs: tuple[ModelPairBinding, ...] = ()
    created_by_actor_context_id: CanonicalUUID
    created_at_utc: UtcTimestamp

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Pares ativos do próprio projeto, únicos, ordenados por ``pair_id`` e no limite."""
        ids = [str(pair.pair_id) for pair in self.active_pair_refs]
        if ids != sorted(set(ids)):
            raise ValueError("active_pair_refs precisa estar ordenado por pair_id, sem repetição")
        if any(
            pair.project_id != self.project_id or not pair.active for pair in self.active_pair_refs
        ):
            raise ValueError("active_pair_refs só contém pares ativos deste projeto")
        if len(self.active_pair_refs) > MAX_ACTIVE_PAIRS:
            raise ValueError(f"no máximo {MAX_ACTIVE_PAIRS} pares ativos")
        return self


class ProjectCatalogPin(ContractModel):
    """Revisão imutável do release fixado no projeto, com proveniência e adoção."""

    schema_version: SchemaVersionOne = 1
    project_id: CanonicalUUID
    pin_revision: PositiveInt
    catalog: CatalogReleaseRef
    catalog_provenance: CatalogProvenance
    adoption_id: CanonicalUUID
    previous_pin_revision: PositiveInt | None = None
    actor_snapshot: ActorSnapshot
    reason: NonEmptyText
    created_at_utc: UtcTimestamp

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Proveniência publicada do mesmo release; revisão anterior imediatamente antes."""
        if self.catalog_provenance.catalog != self.catalog:
            raise ValueError("proveniência pertence a outro release")
        if not self.catalog_provenance.published:
            raise ValueError("pin exige release com cadeia de publicação verificada")
        expected = None if self.pin_revision == 1 else self.pin_revision - 1
        if self.previous_pin_revision != expected:
            raise ValueError("previous_pin_revision precisa ser a revisão imediatamente anterior")
        if self.actor_snapshot.actor_kind != "human":
            raise ValueError("pin exige ator humano declarado")
        return self


class ProjectState(ContractModel):
    """Estado consultável do projeto: heads, revisões, pares, pin e tokens de CAS."""

    project: ProjectRecord
    models: tuple[ModelRecord, ...]
    sources: tuple[SourceArtifactRef, ...]
    pairs: tuple[ModelPairBinding, ...]
    pin: ProjectCatalogPin | None
    pin_revision: NonNegativeInt

    @property
    def pair_set_revision(self) -> int:
        """Token do conjunto de pares."""
        return self.project.pair_set_revision
