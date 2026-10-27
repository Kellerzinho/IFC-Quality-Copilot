"""Projeção contextual local, sem fallback nem seleção semântica própria.

Importar este módulo opt-in carrega passivamente DTOs bSDD; nenhum cliente,
registry, cache ou builder histórico é instanciado ou chamado.
"""

import hashlib

from src.bsdd.models import BSDDClassData, BSDDPropertyData
from src.domain_catalog.canonical import canonical_json_bytes
from src.domain_catalog.contracts import RESOLVED_STATUSES
from src.domain_catalog.errors import CatalogProjectionError, ProjectionErrorReason
from src.domain_catalog.models import ConceptDefinition
from src.domain_catalog.projection_contracts import CatalogProjection, ProjectionScope
from src.domain_catalog.reader import CatalogReader
from src.models import BSDDProperty


def build_catalog_projection(reader: CatalogReader, scope: ProjectionScope) -> CatalogProjection:
    """Resolve um requisito pelo E1 e conserva a forma rica do uso selecionado."""
    if reader.ref != scope.catalog:
        raise CatalogProjectionError(
            "release_mismatch", "reader difere do release solicitado", catalog=scope.catalog
        )
    request = scope.request
    if request.entity is None or (request.facet == "property" and request.set_name is None):
        raise CatalogProjectionError(
            "insufficient_context",
            "entidade e conjunto explícitos são necessários",
            catalog=scope.catalog,
        )
    result = reader.resolve_binding(request)
    if result.status not in RESOLVED_STATUSES:
        raise CatalogProjectionError(
            "unresolved_binding",
            "resolução não selecionou um uso único",
            catalog=scope.catalog,
            resolution=result,
        )
    assert result.binding_id is not None
    assert result.concept_id is not None
    binding = reader.get_binding(result.binding_id)
    concept = reader.get_concept(result.concept_id)
    content = reader.content
    rule = next(r for r in content.applicability_rules if r.id == binding.applicability_rule_id)
    value_id = binding.value_set_id or concept.value_set_id
    values = next((v for v in content.value_sets if v.id == value_id), None)
    unit = next((u for u in content.units if u.id == concept.unit_id), None)
    policy = (
        reader.get_evidence_policy(binding.evidence_policy_id)
        if binding.evidence_policy_id
        else None
    )
    capability = (
        reader.get_capability(policy.operation_id, policy.operation_version) if policy else None
    )
    sources = set(
        (*binding.source_assertion_ids, *concept.source_assertion_ids, *rule.source_assertion_ids)
    )
    if values:
        sources.update(values.source_assertion_ids)
    if policy:
        sources.update(policy.source_assertion_ids)
    assertions = tuple(a for a in content.source_assertions if a.id in sources)
    artifact_ids = {
        i for a in assertions for i in (a.source_artifact_id, a.transcription_artifact_id) if i
    }
    artifacts = tuple(a for a in content.source_artifacts if a.id in artifact_ids)
    limitations = list(result.limitations)
    limitations.append(
        "DTOs legados omitem Pset, escopo, aplicabilidade, rótulos tipados, "
        "política/capacidade, fonte/decisão e referência completa; usar envelope rico."
    )
    limitations.append(
        "Contexto semântico não comprova valor do projeto, conformidade IDS, "
        "operação disponível ou autorização de escrita."
    )
    if policy is None:
        limitations.append("Nenhuma política/operação cadastrada para este uso.")
    elif capability is not None and capability.status != "available":
        limitations.append(f"Operação indisponível: {capability.reason}")
    _, language_limit = _description(concept, scope.language, reader.describe().catalog.language)
    if language_limit:
        limitations.append(language_limit)
    return CatalogProjection(
        scope=scope,
        resolution=result,
        binding=binding,
        concept=concept,
        applicability_rule=rule,
        effective_value_set=values,
        unit=unit,
        evidence_policy=policy,
        capability=capability,
        source_assertions=assertions,
        source_artifacts=artifacts,
        limitations=tuple(limitations),
    )


def _description(
    concept: ConceptDefinition, language: str, primary: str
) -> tuple[str | None, str | None]:
    """Seleciona idioma solicitado ou principal, declarando ausência/fallback."""
    texts = {item.lang: item.text for item in concept.definition}
    if language in texts:
        return texts[language], None
    if primary in texts:
        return texts[
            primary
        ], f"Definição em {language} ausente; fallback explícito para {primary}."
    return (
        None,
        f"definição ausente nos idiomas {language} e {primary}; nenhum outro idioma escolhido.",
    )


class ScopedLocalCatalogAdapter:
    """Compatibilidade limitada a um único requisito, uso e release explícitos."""

    def __init__(self, reader: CatalogReader, scope: ProjectionScope) -> None:
        """Fixa o contexto sem executar seleção antecipada ou acesso externo."""
        if reader.ref != scope.catalog:
            raise CatalogProjectionError(
                "release_mismatch", "reader difere do release solicitado", catalog=scope.catalog
            )
        self._reader = reader
        self._scope = scope
        self._class_uri = (
            "urn:ifc-quality-copilot:local-class:"
            + hashlib.sha256(canonical_json_bytes(scope.model_dump(mode="json"))).hexdigest()
        )

    def projection(self) -> CatalogProjection:
        """Preserva dados ricos mesmo quando enum ou portador não cabe no legado."""
        return build_catalog_projection(self._reader, self._scope)

    def _error(
        self, reason: ProjectionErrorReason, message: str, projection: CatalogProjection
    ) -> CatalogProjectionError:
        return CatalogProjectionError(
            reason, message, catalog=self._scope.catalog, resolution=projection.resolution
        )

    def _property_projection(self) -> CatalogProjection:
        projection = self.projection()
        binding = projection.binding
        if binding.carrier_kind != "property" or binding.carrier_status != "approved":
            raise self._error(
                "unsupported_carrier",
                "somente propriedade com portador aprovado é projetável",
                projection,
            )
        return projection

    def _property(self, property_uri: str) -> CatalogProjection:
        projection = self._property_projection()
        if property_uri != projection.binding.id:
            raise self._error(
                "foreign_reference", "referência não é o binding deste escopo", projection
            )
        return projection

    def _class(self, class_uri: str) -> CatalogProjection:
        projection = self._property_projection()
        if class_uri != self._class_uri:
            raise self._error(
                "foreign_reference", "referência não é o agrupamento deste escopo", projection
            )
        return projection

    def _values(self, projection: CatalogProjection) -> list[str] | None:
        values = projection.effective_value_set
        if values is None:
            return None
        codes: list[str] = []
        for value in values.values:
            if not isinstance(value.code, str):
                raise self._error(
                    "unrepresentable_enum", "código tipado não cabe em list[str]", projection
                )
            codes.append(value.code)
        return codes

    def search_classes_text(self, query: str, domain: str = "IFC") -> list[BSDDClassData]:
        """Busca apenas a entidade deste escopo, por igualdade sem caixa."""
        projection = self._property_projection()
        if domain != "IFC":
            raise self._error("unsupported_domain", "somente domínio IFC nesta fatia", projection)
        entity = self._scope.request.entity
        assert entity is not None
        if query and query.casefold() != entity.casefold():
            return []
        return [self.get_class_metadata(self._class_uri)]

    def get_class_metadata(self, class_uri: str) -> BSDDClassData:
        """Agrupamento local; sua descrição nunca é uma definição oficial IFC."""
        self._class(class_uri)
        entity = self._scope.request.entity
        assert entity is not None
        return BSDDClassData(
            class_uri=self._class_uri,
            canonical_uri=None,
            display_name=entity,
            code=entity,
            source_origin="local_snapshot",
            status="resolved",
            dictionary_name=self._reader.describe().catalog.name,
            dictionary_uri=self._reader.ref.catalog_id,
            description=(
                f"Agrupamento local de usos do catálogo para {entity}; "
                "não é definição oficial IFC/bSDD."
            ),
        )

    def resolve_property(self, property_uri: str) -> BSDDPropertyData:
        """Projeta apenas o binding escolhido e recusa enum tipado sem coerção."""
        projection = self._property(property_uri)
        binding = projection.binding
        description, _ = _description(
            projection.concept, self._scope.language, self._reader.describe().catalog.language
        )
        return BSDDPropertyData(
            property_uri=binding.id,
            canonical_uri=None,
            display_name=binding.field_name,
            code=binding.field_name,
            source_origin="local_snapshot",
            status="resolved",
            dictionary_uri=self._reader.ref.catalog_id,
            data_type=binding.ifc_type,
            unit=projection.unit.symbol if projection.unit else None,
            allowed_values=self._values(projection),
            description=description,
        )

    def search_class(self, query: str, domain: str = "IFC") -> list[dict[str, str]]:
        """Wrapper de busca para consumidor legado, sem canonicalização."""
        return [
            {
                "uri": item.class_uri or "",
                "name": item.display_name,
                "code": item.code or "",
                "description": item.description or "",
            }
            for item in self.search_classes_text(query, domain)
        ]

    def get_class_properties(self, class_uri: str) -> list[BSDDProperty]:
        """Devolve cópia nova da propriedade do uso, nunca de outros Psets."""
        projection = self._class(class_uri)
        prop = self.resolve_property(projection.binding.id)
        return [
            BSDDProperty(
                name=prop.display_name,
                code=prop.code,
                uri=prop.property_uri,
                data_type=prop.data_type,
                unit=prop.unit,
                allowed_values=prop.allowed_values,
                description=prop.description,
            )
        ]

    def get_property_values(self, property_uri: str) -> list[str]:
        """Cópia de todos os códigos textuais; vazio só quando não há enum."""
        return self._values(self._property(property_uri)) or []
