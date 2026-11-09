"""Conteúdo agregado do catálogo e validação cruzada (M1-03).

As entidades validam a si mesmas; aqui se verificam identidade única, referências,
unidade versus dimensão, tipo IFC versus conceito, restrição de valores e
prontidão para publicação. Todos os problemas são reunidos em uma única falha,
com entidade e campo, em vez de parar no primeiro.
"""

from collections.abc import Iterator
from typing import Literal

from pydantic import Field

from src.domain_catalog.errors import CatalogValidationError, ContentIssue
from src.domain_catalog.models import (
    IFC_VALUE_TYPES,
    PUBLISHABLE_LIFECYCLES,
    AliasMapping,
    AllowedValueSet,
    ApplicabilityRule,
    CatalogModel,
    ConceptDefinition,
    EvidencePolicy,
    IFCBinding,
    ProfileMembership,
    ReconciliationDecision,
    SourceArtifact,
    SourceAssertion,
    UnitDefinition,
)

EntityKind = Literal[
    "source_artifacts",
    "source_assertions",
    "concepts",
    "units",
    "value_sets",
    "applicability_rules",
    "evidence_policies",
    "bindings",
    "aliases",
    "profile_memberships",
    "reconciliation_decisions",
]
"""Tipos de entidade do conteúdo; cada um é um arquivo do pacote."""

ENTITY_KINDS: tuple[EntityKind, ...] = (
    "source_artifacts",
    "source_assertions",
    "concepts",
    "units",
    "value_sets",
    "applicability_rules",
    "evidence_policies",
    "bindings",
    "aliases",
    "profile_memberships",
    "reconciliation_decisions",
)
"""Tipos de entidade do conteúdo, na ordem usada em validação e empacotamento."""

REFERENCES: tuple[tuple[str, str, str], ...] = (
    ("source_assertions", "source_artifact_id", "source_artifacts"),
    ("source_assertions", "transcription_artifact_id", "source_artifacts"),
    ("concepts", "unit_id", "units"),
    ("concepts", "value_set_id", "value_sets"),
    ("concepts", "source_assertion_ids", "source_assertions"),
    ("value_sets", "restricts_value_set_id", "value_sets"),
    ("value_sets", "source_assertion_ids", "source_assertions"),
    ("applicability_rules", "source_assertion_ids", "source_assertions"),
    ("evidence_policies", "source_assertion_ids", "source_assertions"),
    ("bindings", "concept_id", "concepts"),
    ("bindings", "applicability_rule_id", "applicability_rules"),
    ("bindings", "value_set_id", "value_sets"),
    ("bindings", "evidence_policy_id", "evidence_policies"),
    ("bindings", "source_assertion_ids", "source_assertions"),
    ("aliases", "target_concept_id", "concepts"),
    ("aliases", "target_binding_id", "bindings"),
    ("aliases", "source_assertion_ids", "source_assertions"),
    ("profile_memberships", "binding_id", "bindings"),
    ("profile_memberships", "source_assertion_ids", "source_assertions"),
    ("reconciliation_decisions", "source_assertion_ids", "source_assertions"),
    ("reconciliation_decisions", "affected_binding_ids", "bindings"),
)
"""Referências entre entidades: ``(tipo, campo, tipo alvo)``; todas são conferidas."""

_LOGICAL_TO_VALUE_TYPE: dict[str, str] = {
    "code": "code",
    "string": "string",
    "integer": "integer",
    "boolean": "boolean",
}


class CatalogContent(CatalogModel):
    """Todas as entidades de um catálogo (rascunho ou release), sem valores de elementos."""

    source_artifacts: tuple[SourceArtifact, ...] = ()
    source_assertions: tuple[SourceAssertion, ...] = ()
    concepts: tuple[ConceptDefinition, ...] = ()
    units: tuple[UnitDefinition, ...] = ()
    value_sets: tuple[AllowedValueSet, ...] = ()
    applicability_rules: tuple[ApplicabilityRule, ...] = ()
    evidence_policies: tuple[EvidencePolicy, ...] = ()
    bindings: tuple[IFCBinding, ...] = ()
    aliases: tuple[AliasMapping, ...] = ()
    profile_memberships: tuple[ProfileMembership, ...] = ()
    reconciliation_decisions: tuple[ReconciliationDecision, ...] = Field(default=())

    def iter_entities(self) -> Iterator[tuple[str, CatalogModel]]:
        """Percorre ``(tipo, entidade)`` em ordem estável."""
        for kind in ENTITY_KINDS:
            for entity in getattr(self, kind):
                yield kind, entity


class _Checker:
    """Acumula problemas de um conteúdo; cada método cobre uma família de regras."""

    def __init__(self, content: CatalogContent) -> None:
        self.content = content
        self.issues: list[ContentIssue] = []
        self.ids: dict[str, set[str]] = {kind: set() for kind in ENTITY_KINDS}
        self.concepts = {item.id: item for item in content.concepts}
        self.units = {item.id: item for item in content.units}
        self.value_sets = {item.id: item for item in content.value_sets}

    def add(self, code: str, kind: str, entity_id: str, field: str | None, message: str) -> None:
        self.issues.append(
            ContentIssue(
                code=code, entity_kind=kind, entity_id=entity_id, field=field, message=message
            )
        )

    def check_unique_ids(self) -> None:
        seen: dict[str, str] = {}
        for kind, entity in self.content.iter_entities():
            entity_id = entity.id  # type: ignore[attr-defined]
            if entity_id in seen:
                self.add("duplicate_id", kind, entity_id, "id", f"ID já usado em {seen[entity_id]}")
                continue
            seen[entity_id] = kind
            self.ids[kind].add(entity_id)

    def check_references(self) -> None:
        for kind, field, target in REFERENCES:
            for entity in getattr(self.content, kind):
                value = getattr(entity, field)
                for item in value if isinstance(value, tuple) else (value,):
                    if item is not None and item not in self.ids[target]:
                        self.add(
                            "orphan_reference",
                            kind,
                            entity.id,
                            field,
                            f"{item} não existe em {target}",
                        )

    def check_units(self) -> None:
        for concept in self.content.concepts:
            unit = self.units.get(concept.unit_id) if concept.unit_id else None
            if unit is not None and unit.dimension != concept.dimension:
                self.add(
                    "unit_dimension_mismatch",
                    "concepts",
                    concept.id,
                    "unit_id",
                    f"unidade {unit.symbol} é {unit.dimension}; conceito é {concept.dimension}",
                )

    def _value_set_matches(
        self, kind: str, entity_id: str, field: str, vs_id: str | None, concept: ConceptDefinition
    ) -> None:
        value_set = self.value_sets.get(vs_id) if vs_id else None
        if value_set is None:
            return
        expected = _LOGICAL_TO_VALUE_TYPE.get(concept.logical_type)
        if expected != value_set.value_type:
            self.add(
                "value_type_mismatch",
                kind,
                entity_id,
                field,
                f"conjunto {value_set.value_type} incompatível com conceito {concept.logical_type}",
            )

    def check_value_sets(self) -> None:
        for concept in self.content.concepts:
            self._value_set_matches(
                "concepts", concept.id, "value_set_id", concept.value_set_id, concept
            )
        for vs in self.content.value_sets:
            parent = (
                self.value_sets.get(vs.restricts_value_set_id)
                if vs.restricts_value_set_id
                else None
            )
            if parent is None:
                continue
            parent_codes = {(type(v.code), v.code) for v in parent.values}
            extra = [v.code for v in vs.values if (type(v.code), v.code) not in parent_codes]
            if parent.value_type != vs.value_type or extra:
                self.add(
                    "restriction_not_subset",
                    "value_sets",
                    vs.id,
                    "values",
                    f"restrição acrescenta códigos ao conjunto {parent.id}: {extra}",
                )

    def check_bindings(self) -> None:
        for b in self.content.bindings:
            concept = self.concepts.get(b.concept_id)
            if concept is None:
                continue
            if b.ifc_type is not None:
                spec = IFC_VALUE_TYPES[b.ifc_type]
                dimension_ok = (
                    concept.dimension == spec.dimension
                    if spec.dimension is not None
                    else concept.dimension in (None, "dimensionless")
                )
                if concept.logical_type not in spec.logical_types or not dimension_ok:
                    self.add(
                        "ifc_type_incompatible",
                        "bindings",
                        b.id,
                        "ifc_type",
                        f"{b.ifc_type} incompatível com conceito "
                        f"{concept.logical_type}/{concept.dimension}",
                    )
            self._value_set_matches("bindings", b.id, "value_set_id", b.value_set_id, concept)
            value_set = self.value_sets.get(b.value_set_id) if b.value_set_id else None
            if (
                value_set is not None
                and concept.value_set_id is not None
                and b.value_set_id != concept.value_set_id
                and value_set.restricts_value_set_id != concept.value_set_id
            ):
                self.add(
                    "value_set_not_restriction",
                    "bindings",
                    b.id,
                    "value_set_id",
                    "conjunto do binding precisa ser o do conceito ou uma restrição dele",
                )

    def check_publishable(self) -> None:
        for kind, entity in self.content.iter_entities():
            lifecycle = getattr(entity, "lifecycle", None)
            if lifecycle is not None and lifecycle not in PUBLISHABLE_LIFECYCLES:
                self.add(
                    "lifecycle_not_publishable",
                    kind,
                    entity.id,  # type: ignore[attr-defined]
                    "lifecycle",
                    f"estado {lifecycle} não entra em release",
                )


def content_issues(content: CatalogContent, *, for_release: bool) -> list[ContentIssue]:
    """Lista os problemas do conteúdo; ``for_release`` acrescenta a prontidão de publicação."""
    checker = _Checker(content)
    checker.check_unique_ids()
    checker.check_references()
    checker.check_units()
    checker.check_value_sets()
    checker.check_bindings()
    if for_release:
        checker.check_publishable()
    return checker.issues


def validate_content(content: CatalogContent, *, for_release: bool) -> None:
    """Falha com todos os problemas encontrados; não corrige nada em silêncio."""
    issues = content_issues(content, for_release=for_release)
    if issues:
        raise CatalogValidationError(issues)
