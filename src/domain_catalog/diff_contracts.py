"""DTOs do diff entre dois releases do mesmo catálogo e do impacto interno (E3.2a).

Imutáveis, com campos extras proibidos e coleções em tuplas. Valores antes/depois são
JSON canônico (``DiffValue``): ``None`` em ``FieldChange`` significa lado
**inexistente** (entidade adicionada/retirada), nunca JSON nulo. Os validadores
conferem coerência estrutural — ordem, unicidade, encadeamento de caminhos e a
equivalência ``no_changes == same_release`` —, mas não provam que uma aresta de um
DTO arbitrário existe num pacote real; essa garantia é do produtor (``diff.py``).
Nenhuma propriedade aqui significa "adoção permitida".
"""

from typing import Annotated, Any, Final, Literal, Self, get_args

from pydantic import Field, StrictInt, StringConstraints, ValidationError, model_validator

from src.domain_catalog.canonical import CanonicalJSONError, canonical_json_text, parse_json_strict
from src.domain_catalog.content import ENTITY_KINDS, REFERENCES, EntityKind
from src.domain_catalog.contracts import CatalogReleaseRef, ContractModel
from src.domain_catalog.package import ENTITY_MODELS

ChangeClass = Literal["cosmetic", "semantic", "operational"]
ChangeCategory = Literal[
    "addition",
    "removal",
    "deprecation",
    "label",
    "definition",
    "type",
    "unit",
    "enum",
    "binding",
    "schema",
    "applicability",
    "alias",
    "evidence_policy",
    "operation",
    "source",
    "decision",
    "profile",
    "lifecycle",
    "other",
]
ManifestCategory = Literal[
    "release_identity",
    "catalog_metadata",
    "provenance",
    "distribution_terms",
    "derived_summary",
    "package_inventory",
    "format",
    "other",
]
ImpactDirection = Literal["reverse_dependency", "forward_contribution"]

CLASS_ORDER: Final[tuple[str, ...]] = get_args(ChangeClass)
CATEGORY_ORDER: Final[tuple[str, ...]] = get_args(ChangeCategory)
KIND_INDEX: Final[dict[str, int]] = {kind: index for index, kind in enumerate(ENTITY_KINDS)}

REFERENCE_DIRECTIONS: Final[dict[tuple[str, str, str], ImpactDirection]] = {
    reference: (
        "forward_contribution"
        if reference
        in (
            ("aliases", "target_concept_id", "concepts"),
            ("aliases", "target_binding_id", "bindings"),
            ("profile_memberships", "binding_id", "bindings"),
            ("reconciliation_decisions", "affected_binding_ids", "bindings"),
        )
        else "reverse_dependency"
    )
    for reference in REFERENCES
}
"""Direção de propagação de cada uma das 21 referências cadastrais (adendo §4.1)."""

_LOCAL_ID = r"^urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
_SOURCE_REF = r"^[a-z0-9][a-z0-9-]*:[A-Za-z0-9][A-Za-z0-9._-]*$"
_SOURCE_KINDS = frozenset({"source_artifacts", "source_assertions"})


def _ordered_unique(values: tuple[str, ...], order: tuple[str, ...], what: str) -> None:
    if not values:
        raise ValueError(f"{what} não pode ser vazio")
    indexes = [order.index(value) for value in values]
    if indexes != sorted(set(indexes)):
        raise ValueError(f"{what} precisa ser único e na ordem declarada")


class EntityKey(ContractModel):
    """Entidade por tipo e ID estável; fontes usam ``SourceRef`` e as demais ``LocalId``."""

    kind: EntityKind
    id: Annotated[str, StringConstraints(min_length=1)]

    @model_validator(mode="after")
    def _id_matches_kind(self) -> Self:
        """Tipo de ID coerente com o tipo de entidade."""
        import re

        pattern = _SOURCE_REF if self.kind in _SOURCE_KINDS else _LOCAL_ID
        if re.match(pattern, self.id) is None:
            raise ValueError(f"ID {self.id!r} inválido para {self.kind}")
        return self

    def sort_key(self) -> tuple[int, str]:
        """Ordem do formato: índice do tipo e ID literal."""
        return KIND_INDEX[self.kind], self.id


class DiffValue(ContractModel):
    """Valor JSON canônico (sem LF final); ``value`` devolve uma interpretação nova."""

    json_text: str

    @model_validator(mode="after")
    def _canonical(self) -> Self:
        """Texto precisa ser JSON estrito e já na forma canônica."""
        try:
            parsed = parse_json_strict(self.json_text)
        except CanonicalJSONError as exc:
            raise ValueError(f"json_text inválido: {exc}") from exc
        if canonical_json_text(parsed) != self.json_text:
            raise ValueError("json_text fora da forma canônica")
        return self

    @property
    def value(self) -> Any:
        """Cópia nova do valor; alterá-la não altera o DTO."""
        return parse_json_strict(self.json_text)


class FieldChange(ContractModel):
    """Campo superior alterado; ``None`` é lado inexistente, não JSON nulo."""

    field: Annotated[str, StringConstraints(min_length=1)]
    before: DiffValue | None
    after: DiffValue | None
    categories: tuple[ChangeCategory, ...]
    classes: tuple[ChangeClass, ...]

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Algum lado presente, lados distintos e rótulos únicos e ordenados."""
        if self.before is None and self.after is None:
            raise ValueError("FieldChange exige ao menos um lado presente")
        if (
            self.before is not None
            and self.after is not None
            and self.before.json_text == self.after.json_text
        ):
            raise ValueError("antes e depois iguais não são alteração")
        _ordered_unique(self.categories, CATEGORY_ORDER, "categories")
        _ordered_unique(self.classes, CLASS_ORDER, "classes")
        return self


def _entity_payload(entity: "EntityKey", value: DiffValue) -> None:
    payload = value.value
    if not isinstance(payload, dict):
        raise ValueError("entidade adicionada/retirada exige objeto JSON")
    try:
        model = ENTITY_MODELS[entity.kind].model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"payload incompatível com {entity.kind}: {exc}") from exc
    if getattr(model, "id", None) != entity.id:
        raise ValueError("payload pertence a outra entidade")


class EntityChange(ContractModel):
    """Entidade adicionada, retirada (campo ``$``) ou modificada (campos superiores)."""

    entity: EntityKey
    change_kind: Literal["added", "removed", "modified"]
    fields: tuple[FieldChange, ...]

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Forma de cada tipo de mudança, campos únicos e ordenados."""
        if not self.fields:
            raise ValueError("EntityChange exige ao menos um campo")
        names = [change.field for change in self.fields]
        if names != sorted(set(names)):
            raise ValueError("campos precisam ser únicos e em ordem literal")
        if self.change_kind == "modified":
            top_level = set(ENTITY_MODELS[self.entity.kind].model_fields) - {"id"}
            for change in self.fields:
                if change.field in ("$", "id"):
                    raise ValueError("modificação não usa '$' nem 'id'")
                if change.field not in top_level:
                    # Formato atual: só campos superiores reais deste kind (E3-15).
                    raise ValueError(
                        f"campo {change.field!r} não é campo superior de {self.entity.kind}"
                    )
                if change.before is None or change.after is None:
                    raise ValueError("modificação exige os dois lados")
            return self
        if len(self.fields) != 1 or self.fields[0].field != "$":
            raise ValueError("adição/retirada usa somente o campo '$'")
        change = self.fields[0]
        added = self.change_kind == "added"
        present = change.after if added else change.before
        absent = change.before if added else change.after
        if present is None or absent is not None:
            raise ValueError("adição tem só 'depois'; retirada tem só 'antes'")
        if change.categories != (("addition",) if added else ("removal",)):
            raise ValueError("categoria de adição/retirada incoerente")
        _entity_payload(self.entity, present)
        return self


class ManifestChange(ContractModel):
    """Campo do manifesto alterado; lista própria, nunca raiz de impacto."""

    field: Annotated[str, StringConstraints(min_length=1)]
    before: DiffValue
    after: DiffValue
    category: ManifestCategory
    classes: tuple[ChangeClass, ...]

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Lados distintos e classes únicas e ordenadas."""
        if self.before.json_text == self.after.json_text:
            raise ValueError("antes e depois iguais não são alteração")
        _ordered_unique(self.classes, CLASS_ORDER, "classes")
        return self


class ImpactEdge(ContractModel):
    """Referência cadastral real ``owner.field -> referenced`` e seu sentido de travessia."""

    owner: EntityKey
    field: Annotated[str, StringConstraints(min_length=1)]
    referenced: EntityKey
    direction: ImpactDirection

    @model_validator(mode="after")
    def _known_reference(self) -> Self:
        """Somente as 21 referências do formato, com a direção fixada no adendo."""
        key = (self.owner.kind, self.field, self.referenced.kind)
        if REFERENCE_DIRECTIONS.get(key) != self.direction:
            raise ValueError(f"referência {key} inexistente ou com direção incoerente")
        return self

    def step(self, current: EntityKey) -> EntityKey | None:
        """Próximo nó a partir de ``current`` no sentido declarado, ou ``None``."""
        if self.direction == "reverse_dependency":
            return self.owner if self.referenced == current else None
        return self.referenced if self.owner == current else None

    def sort_text(self) -> str:
        """Representação canônica usada no desempate determinístico."""
        return canonical_json_text(self.model_dump(mode="json"))


class ImpactTrace(ContractModel):
    """Testemunha de caminho mínimo de ``origin`` a ``target`` dentro de um snapshot."""

    origin: EntityKey
    target: EntityKey
    snapshot: Literal["old", "new"]
    distance: StrictInt = Field(ge=0)
    path: tuple[ImpactEdge, ...]

    @model_validator(mode="after")
    def _chained(self) -> Self:
        """Distância igual ao caminho e arestas encadeadas de ``origin`` até ``target``."""
        if self.distance != len(self.path):
            raise ValueError("distance precisa ser o comprimento do caminho")
        current = self.origin
        for edge in self.path:
            following = edge.step(current)
            if following is None:
                raise ValueError("caminho desconexo ou em sentido incoerente")
            current = following
        if current != self.target:
            raise ValueError("caminho não termina no alvo")
        return self

    def sort_key(self) -> tuple[int, str, int, int, int, str]:
        """Ordem: origem, snapshot (old antes de new), distância e alvo."""
        return (
            *self.origin.sort_key(),
            0 if self.snapshot == "old" else 1,
            self.distance,
            *self.target.sort_key(),
        )


PositiveLimit = Annotated[StrictInt, Field(ge=1)]


class DiffLimits(ContractModel):
    """Guarda local de volume de saída; não é capacidade homologada do M6."""

    max_impact_traces: PositiveLimit = 100_000


class CatalogDiff(ContractModel):
    """Diff concluído entre dois releases do mesmo catálogo, na direção pedida."""

    status: Literal["compared"] = "compared"
    old_ref: CatalogReleaseRef
    new_ref: CatalogReleaseRef
    entity_changes: tuple[EntityChange, ...]
    manifest_changes: tuple[ManifestChange, ...]
    impacts: tuple[ImpactTrace, ...]

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Refs comparáveis, ordem/unicidade, raízes completas e ``no_changes == same_release``."""
        if self.old_ref.catalog_id != self.new_ref.catalog_id:
            raise ValueError("refs de catálogos distintos não formam diff")
        if (
            self.old_ref.version == self.new_ref.version
            and self.old_ref.manifest_sha256 != self.new_ref.manifest_sha256
        ):
            raise ValueError("mesma versão com hashes distintos é colisão, não diff")
        entities = [change.entity.sort_key() for change in self.entity_changes]
        if entities != sorted(set(entities)):
            raise ValueError("entity_changes precisa ser único e ordenado por tipo e ID")
        fields = [change.field for change in self.manifest_changes]
        if fields != sorted(set(fields)):
            raise ValueError("manifest_changes precisa ser único e ordenado por campo")
        keys = [trace.sort_key() for trace in self.impacts]
        if keys != sorted(keys):
            raise ValueError("impacts fora da ordem prescrita")
        identities = [(t.origin, t.snapshot, t.target) for t in self.impacts]
        if len(identities) != len(set(identities)):
            raise ValueError("impacts repetem (origem, snapshot, alvo)")
        roots = {change.entity: change.change_kind for change in self.entity_changes}
        zero = {(t.origin, t.snapshot) for t in self.impacts if t.distance == 0}
        for trace in self.impacts:
            kind = roots.get(trace.origin)
            if kind is None:
                raise ValueError("origem de impacto sem EntityChange")
            if (kind, trace.snapshot) in (("added", "old"), ("removed", "new")):
                raise ValueError("trace em snapshot onde a origem não existe")
        for entity, kind in roots.items():
            needed = {"added": ("new",), "removed": ("old",), "modified": ("old", "new")}[kind]
            if any((entity, snapshot) not in zero for snapshot in needed):
                raise ValueError("cada raiz precisa de trace de distância zero em seus snapshots")
        if self.same_release == self.has_changes:
            raise ValueError("no_changes precisa equivaler a same_release")
        return self

    @property
    def same_release(self) -> bool:
        """Mesma referência completa (ID, versão e hash)."""
        return self.old_ref == self.new_ref

    @property
    def has_entity_changes(self) -> bool:
        """Há delta cadastral."""
        return bool(self.entity_changes)

    @property
    def has_manifest_changes(self) -> bool:
        """Há delta de manifesto."""
        return bool(self.manifest_changes)

    @property
    def has_changes(self) -> bool:
        """Há qualquer delta."""
        return self.has_entity_changes or self.has_manifest_changes

    @property
    def no_changes(self) -> bool:
        """Nenhum delta; não significa adoção segura nem dispensa de análise."""
        return not self.has_changes

    @property
    def affected_entities(self) -> tuple[EntityKey, ...]:
        """União dos alvos (inclui raízes), em ordem de tipo e ID."""
        return tuple(sorted({t.target for t in self.impacts}, key=EntityKey.sort_key))

    def _affected_ids(self, kind: str) -> tuple[str, ...]:
        return tuple(sorted(e.id for e in self.affected_entities if e.kind == kind))

    @property
    def affected_binding_ids(self) -> tuple[str, ...]:
        """IDs de bindings atingidos, em ordem literal."""
        return self._affected_ids("bindings")

    @property
    def affected_concept_ids(self) -> tuple[str, ...]:
        """IDs de conceitos atingidos, em ordem literal."""
        return self._affected_ids("concepts")

    @property
    def affected_policy_ids(self) -> tuple[str, ...]:
        """IDs de políticas de evidência atingidas, em ordem literal."""
        return self._affected_ids("evidence_policies")
