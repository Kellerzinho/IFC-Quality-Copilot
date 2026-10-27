"""Envelope imutável da projeção local opt-in; não autoriza operações ou escrita."""

from typing import Literal, Self

from pydantic import model_validator

from src.domain_catalog.contracts import (
    RESOLVED_STATUSES,
    BindingRequest,
    CatalogReleaseRef,
    ContractModel,
    OperationCapability,
    ResolutionResult,
)
from src.domain_catalog.errors import ProjectionErrorReason
from src.domain_catalog.models import (
    AllowedValueSet,
    ApplicabilityRule,
    ConceptDefinition,
    EvidencePolicy,
    IFCBinding,
    LocalId,
    NonEmptyText,
    SourceArtifact,
    SourceAssertion,
    UnitDefinition,
)


class ProjectionScope(ContractModel):
    """Referência exata e requisito conhecido, sem completar fatos ausentes."""

    catalog: CatalogReleaseRef
    request: BindingRequest
    language: NonEmptyText = "pt-BR"


class CatalogProjection(ContractModel):
    """Uso selecionado com seus tipos, fontes e limites de representação."""

    scope: ProjectionScope
    resolution: ResolutionResult
    binding: IFCBinding
    concept: ConceptDefinition
    applicability_rule: ApplicabilityRule
    effective_value_set: AllowedValueSet | None
    unit: UnitDefinition | None
    evidence_policy: EvidencePolicy | None
    capability: OperationCapability | None
    source_assertions: tuple[SourceAssertion, ...]
    source_artifacts: tuple[SourceArtifact, ...]
    limitations: tuple[str, ...]

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Preserva identidades e referências internas, sem autenticar bytes do release."""
        result = self.resolution
        if result.status not in RESOLVED_STATUSES:
            raise ValueError("projeção exige resolução única")
        if result.catalog != self.scope.catalog or result.request != self.scope.request:
            raise ValueError("resolução deve preservar release e requisito do escopo")
        if (result.binding_id, result.concept_id) != (self.binding.id, self.concept.id):
            raise ValueError("binding/conceito devem ser os escolhidos na resolução")
        if self.binding.concept_id != self.concept.id:
            raise ValueError("conceito não pertence ao binding")
        if self.binding.applicability_rule_id != self.applicability_rule.id:
            raise ValueError("regra não pertence ao binding")
        value_set_id = self.binding.value_set_id or self.concept.value_set_id
        if (self.effective_value_set.id if self.effective_value_set else None) != value_set_id:
            raise ValueError("enum efetivo deve preservar a referência do uso")
        if (self.unit.id if self.unit else None) != self.concept.unit_id:
            raise ValueError("unidade deve preservar a referência do conceito")
        policy = self.evidence_policy
        if (policy.id if policy else None) != self.binding.evidence_policy_id:
            raise ValueError("política deve preservar a referência do binding")
        capability = self.capability
        if policy is None:
            if capability is not None:
                raise ValueError("capacidade exige política de evidência")
        elif capability is None or (capability.operation_id, capability.requested_version) != (
            policy.operation_id,
            policy.operation_version,
        ):
            raise ValueError("capacidade deve preservar operação e versão da política")
        return self


class LocalProjectedProperty(ContractModel):
    """Cópia imutável e identificada da propriedade representável pelo legado."""

    name: str
    code: str
    uri: LocalId
    data_type: str | None
    unit: str | None
    allowed_values: tuple[str, ...] | None
    description: str | None


class LocalCatalogContext(ContractModel):
    """Contexto semântico local; disponibilidade não significa operação ou escrita."""

    condition_id: Literal["m1-local-context-v1"] = "m1-local-context-v1"
    source_origin: Literal["local_snapshot"] = "local_snapshot"
    scope: ProjectionScope
    resolution: ResolutionResult | None
    status: Literal["available", "unavailable"]
    projection: CatalogProjection | None
    properties: tuple[LocalProjectedProperty, ...]
    error_reason: ProjectionErrorReason | None
    limitations: tuple[str, ...]

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Recusa sucesso vazio e identidades contraditórias em qualquer estado."""
        if self.resolution is not None and (
            self.resolution.catalog != self.scope.catalog
            or self.resolution.request != self.scope.request
        ):
            raise ValueError("resolução deve preservar escopo e release")
        if self.projection is not None and (
            self.projection.scope != self.scope or self.projection.resolution != self.resolution
        ):
            raise ValueError("projeção deve preservar escopo e resolução")
        if self.status == "unavailable":
            if self.error_reason is None or self.properties:
                raise ValueError("indisponibilidade exige motivo e nenhuma propriedade legada")
            return self
        if self.error_reason is not None or self.projection is None or self.resolution is None:
            raise ValueError("contexto disponível exige projeção/resolução e nenhum erro")
        if self.resolution.status not in RESOLVED_STATUSES or len(self.properties) != 1:
            raise ValueError("contexto disponível exige uso único e uma propriedade")
        binding = self.projection.binding
        prop = self.properties[0]
        if binding.carrier_kind != "property" or binding.carrier_status != "approved":
            raise ValueError("contexto disponível exige propriedade com portador aprovado")
        if (prop.uri, prop.name, prop.code, prop.data_type) != (
            binding.id,
            binding.field_name,
            binding.field_name,
            binding.ifc_type,
        ):
            raise ValueError("propriedade deve representar o binding escolhido")
        values = self.projection.effective_value_set
        if values is not None and any(not isinstance(v.code, str) for v in values.values):
            raise ValueError("enum tipado não cabe no contexto legado disponível")
        expected_values = tuple(v.code for v in values.values) if values else None
        if prop.allowed_values != expected_values:
            raise ValueError("opções devem preservar todos os códigos do uso")
        expected_unit = self.projection.unit.symbol if self.projection.unit else None
        if prop.unit != expected_unit:
            raise ValueError("unidade deve preservar símbolo do uso")
        return self
