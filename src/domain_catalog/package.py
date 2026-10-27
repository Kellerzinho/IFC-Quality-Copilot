"""Formato de pacote de release do catálogo, versão 1 (plano M1 §7.1; M1-06).

Um release é uma pasta plana com ``manifest.json`` e um arquivo JSON canônico por
tipo de entidade. O manifesto lista cada arquivo com tamanho, SHA-256 e número de
entradas; a identidade do release é o SHA-256 dos bytes do manifesto, guardado fora
dele (no pin ou recibo), sem autorreferência. Rascunho nunca vira release. A
publicação com staging, promoção atômica e recibo pertence à M1-09; aqui só se
constroem os bytes e se grava uma pasta nova, nunca sobre uma existente.
"""

import hashlib
from pathlib import Path
from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, model_validator

from src.domain_catalog.canonical import canonical_json_bytes
from src.domain_catalog.content import (
    ENTITY_KINDS,
    CatalogContent,
    EntityKind,
    validate_content,
)
from src.domain_catalog.contracts import CatalogReleaseRef, ContractModel, SemVer
from src.domain_catalog.models import (
    AliasMapping,
    AllowedValueSet,
    ApplicabilityRule,
    CatalogModel,
    ConceptDefinition,
    EvidencePolicy,
    FormatVersionOne,
    IFCBinding,
    IfcSchemaId,
    LangTag,
    LocalId,
    NonEmptyText,
    ProfileMembership,
    ReconciliationDecision,
    Sha256Hex,
    Slug,
    SourceArtifact,
    SourceAssertion,
    UnitDefinition,
)

PACKAGE_FORMAT: Final = "ifcqc-catalog-package"
PACKAGE_FORMAT_VERSION: Final = 1
MANIFEST_FILE = "manifest.json"
DATA_FILES: dict[str, str] = {kind: f"{kind}.json" for kind in ENTITY_KINDS}
"""Arquivo de dados de cada tipo; nomes fixos e planos, sem subpastas."""

ENTITY_MODELS: dict[str, type[CatalogModel]] = {
    "source_artifacts": SourceArtifact,
    "source_assertions": SourceAssertion,
    "concepts": ConceptDefinition,
    "units": UnitDefinition,
    "value_sets": AllowedValueSet,
    "applicability_rules": ApplicabilityRule,
    "evidence_policies": EvidencePolicy,
    "bindings": IFCBinding,
    "aliases": AliasMapping,
    "profile_memberships": ProfileMembership,
    "reconciliation_decisions": ReconciliationDecision,
}

ContentOrigin = Literal["curated", "synthetic_fixture"]
"""Fixture sintética de teste nunca se confunde com conteúdo curado de fonte real."""

UtcTimestamp = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")]
PositiveInt = Annotated[StrictInt, Field(ge=1)]
CountInt = Annotated[StrictInt, Field(ge=0)]


class PackageLimits(BaseModel):
    """Limites de leitura; valores provisórios até a calibração com o M6."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_manifest_bytes: PositiveInt = 1_048_576
    max_file_bytes: PositiveInt = 67_108_864
    max_total_bytes: PositiveInt = 268_435_456
    max_entities: PositiveInt = 500_000


class CatalogIdentity(ContractModel):
    """Catálogo e mantenedor; namespace local declarado provisório, nunca oficial."""

    catalog_id: LocalId
    namespace: Slug
    namespace_status: Literal["provisional", "institutional"]
    name: NonEmptyText
    maintainer: NonEmptyText
    language: LangTag
    description: str | None = None


class ComponentTerms(ContractModel):
    """Termos de uso/distribuição de um componente do pacote."""

    component: NonEmptyText
    terms: NonEmptyText


class ManifestFile(ContractModel):
    """Arquivo listado no manifesto; o caminho é o nome fixo do tipo."""

    path: NonEmptyText
    kind: EntityKind
    bytes: CountInt
    sha256: Sha256Hex
    entries: CountInt

    @model_validator(mode="after")
    def _path_is_fixed_name(self) -> Self:
        """Recusa caminho absoluto, travessia ou subpasta: só o nome fixo do tipo."""
        if self.path != DATA_FILES[self.kind]:
            raise ValueError(f"path {self.path!r} não é o arquivo do tipo {self.kind}")
        return self


class CatalogManifest(ContractModel):
    """Manifesto canônico do release; seu hash é a identidade do release."""

    format: Literal["ifcqc-catalog-package"]
    format_version: FormatVersionOne
    catalog: CatalogIdentity
    version: SemVer
    created_at: UtcTimestamp
    previous_release: CatalogReleaseRef | None = None
    content_origin: ContentOrigin
    profiles: tuple[Slug, ...] = ()
    declared_schemas: tuple[IfcSchemaId, ...] = ()
    terms: tuple[ComponentTerms, ...] = Field(min_length=1)
    files: tuple[ManifestFile, ...]

    @model_validator(mode="after")
    def _one_file_per_kind(self) -> Self:
        """Cada tipo aparece exatamente uma vez, na ordem do formato."""
        if tuple(item.kind for item in self.files) != ENTITY_KINDS:
            raise ValueError("files deve listar cada tipo de entidade uma vez, na ordem do formato")
        return self


class ReleaseFiles(BaseModel):
    """Bytes de um release construído e a referência que o identifica."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest: CatalogManifest
    manifest_bytes: bytes
    data: dict[str, bytes]
    ref: CatalogReleaseRef


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def derived_summary(content: CatalogContent) -> tuple[tuple[str, ...], tuple[IfcSchemaId, ...]]:
    """Perfis e schemas que o manifesto declara: sempre derivados do conteúdo, nunca escolhidos.

    O builder grava este resumo e o reader o recalcula para recusar manifesto que
    contradiga as participações em perfil ou os schemas declarados pelos bindings.
    """
    profiles = tuple(sorted({m.profile_id for m in content.profile_memberships}))
    schemas = tuple(sorted({schema for b in content.bindings for schema in b.declared_schemas}))
    return profiles, schemas


def build_release_files(
    content: CatalogContent,
    *,
    catalog: CatalogIdentity,
    version: str,
    created_at: str,
    content_origin: ContentOrigin,
    terms: tuple[ComponentTerms, ...],
    previous_release: CatalogReleaseRef | None = None,
) -> ReleaseFiles:
    """Serializa um conteúdo publicável; entidades ordenadas por ID tornam os bytes únicos."""
    validate_content(content, for_release=True)
    data: dict[str, bytes] = {}
    files: list[ManifestFile] = []
    for kind in ENTITY_KINDS:
        entities = sorted(getattr(content, kind), key=lambda entity: entity.id)
        blob = canonical_json_bytes([entity.model_dump(mode="json") for entity in entities])
        data[DATA_FILES[kind]] = blob
        files.append(
            ManifestFile(
                path=DATA_FILES[kind],
                kind=kind,
                bytes=len(blob),
                sha256=_sha256(blob),
                entries=len(entities),
            )
        )
    profiles, declared_schemas = derived_summary(content)
    manifest = CatalogManifest(
        format=PACKAGE_FORMAT,
        format_version=PACKAGE_FORMAT_VERSION,
        catalog=catalog,
        version=version,
        created_at=created_at,
        previous_release=previous_release,
        content_origin=content_origin,
        profiles=profiles,
        declared_schemas=declared_schemas,
        terms=terms,
        files=tuple(files),
    )
    manifest_bytes = canonical_json_bytes(manifest.model_dump(mode="json"))
    ref = CatalogReleaseRef(
        catalog_id=catalog.catalog_id, version=version, manifest_sha256=_sha256(manifest_bytes)
    )
    return ReleaseFiles(manifest=manifest, manifest_bytes=manifest_bytes, data=data, ref=ref)


def write_release_dir(release: ReleaseFiles, destination: Path) -> CatalogReleaseRef:
    """Grava o release numa pasta nova; pasta existente nunca é sobrescrita."""
    destination.mkdir(parents=True, exist_ok=False)
    for name, blob in release.data.items():
        (destination / name).write_bytes(blob)
    (destination / MANIFEST_FILE).write_bytes(release.manifest_bytes)
    return release.ref
