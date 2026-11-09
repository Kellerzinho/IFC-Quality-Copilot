"""Contratos do importador local de snapshot bSDD (E4, M1-10).

Perfil local ``ifcqc-bsdd-import-subset-1``: lê o formato JSON oficial de importação
do bSDD com ``ModelVersion == "2.0"`` (campos do dicionário na raiz, sem wrapper
``Dictionary``), conforme o template e a documentação consultados em 22/10/2026
(``docs/catalogo/evidencias-e4/bsdd-fontes-primarias.json``). Não é resposta da API
nem certificação de conformidade bSDD.

Três identidades separadas: ``raw_sha256`` dos bytes adquiridos; ``semantic_sha256`` do
``dictionary.normalized.json`` materializado pela regra ``ifcqc-bsdd-normalization-1``;
e o ``CatalogContent`` candidato, fundamentado no artefato normalizado. Reordenar ou
reformatar o arquivo muda o recibo de aquisição, nunca o conteúdo candidato.
"""

import hashlib
import uuid
from typing import Annotated, Final, Literal, Self

from pydantic import Field, StrictInt, model_validator

from src.domain_catalog.canonical import CanonicalJSONError, canonical_json_text, parse_json_strict
from src.domain_catalog.content import CatalogContent
from src.domain_catalog.models import (
    CatalogModel,
    FormatVersionOne,
    NonEmptyText,
    Sha256Hex,
    SourceArtifact,
)

BSDD_IMPORT_PROFILE: Final = "ifcqc-bsdd-import-subset-1"
BSDD_INPUT_FORMAT: Final = "bsdd-import-json"
SUPPORTED_MODEL_VERSION: Final = "2.0"
NORMALIZATION_RULE: Final = "ifcqc-bsdd-normalization-1"
STAGING_FORMAT: Final = "ifcqc-bsdd-staging-1"
BSDD_UUID_NAMESPACE = uuid.UUID("d6a3c3a4-0b3e-5b8c-9d1e-6f0c2a4e7b10")
"""Namespace UUIDv5 próprio e fixo dos candidatos bSDD; mudar este valor muda todos os IDs."""

PositiveInt = Annotated[StrictInt, Field(ge=1)]
CountInt = Annotated[StrictInt, Field(ge=0)]

EntityKind = Literal["class", "property", "class_property"]
UsageStatus = Literal["permitted", "unknown", "restricted"]
"""Estatuto declarado por quem fornece o arquivo; proveniência, não decisão jurídica."""
SnapshotOrigin = Literal["real", "synthetic"]
ItemStatus = Literal["projected", "preserved_without_projection", "pending", "rejected"]
ItemSeverity = Literal["info", "loss", "pending", "warning"]
ItemEffect = Literal["projected", "not_projected", "pending_external", "none"]
DistributionGate = Literal[
    "terms_declared_permitted", "blocked_terms_unknown", "blocked_terms_restricted"
]


class SnapshotLimits(CatalogModel):
    """Limites iniciais de recurso do importador; não são política institucional nem SLA.

    A profundidade efetiva nunca passa de 64, teto do leitor JSON estrito do catálogo.
    """

    max_bytes: PositiveInt = 16 * 1024 * 1024
    max_classes: PositiveInt = 10_000
    max_properties: PositiveInt = 50_000
    max_class_properties: PositiveInt = 100_000
    max_allowed_values: PositiveInt = 100_000
    max_depth: Annotated[StrictInt, Field(ge=1, le=64)] = 64
    max_string_chars: PositiveInt = 65_536


class BSDDSnapshotEnvelope(CatalogModel):
    """Bytes adquiridos, sua identidade e a identidade declarada do dicionário."""

    profile: Literal["ifcqc-bsdd-import-subset-1"]
    input_format: Literal["bsdd-import-json"]
    source: SourceArtifact
    raw_bytes: bytes
    raw_sha256: Sha256Hex
    raw_size_bytes: CountInt
    payload_json: NonEmptyText
    model_version: Literal["2.0"]
    organization_code: NonEmptyText
    dictionary_code: NonEmptyText
    dictionary_version: NonEmptyText
    language_iso_code: NonEmptyText
    origin: SnapshotOrigin
    declared_license: str | None = None
    declared_license_url: str | None = None
    usage_status: UsageStatus = "unknown"
    limits: SnapshotLimits

    @model_validator(mode="after")
    def _bound_to_raw_bytes(self) -> Self:
        """Hash, tamanho, payload e identidade derivam dos bytes; envelope montado à mão
        com qualquer um dessincronizado é recusado antes de projetar ou entregar à E2."""
        problem = envelope_problem(self)
        if problem is not None:
            raise ValueError(f"envelope dessincronizado: {problem}")
        return self


def envelope_problem(envelope: BSDDSnapshotEnvelope) -> str | None:
    """Primeira incoerência entre bytes brutos e os campos derivados, ou ``None``."""
    raw = envelope.raw_bytes
    if hashlib.sha256(raw).hexdigest() != envelope.raw_sha256:
        return "raw_sha256 não é o hash de raw_bytes"
    if len(raw) != envelope.raw_size_bytes:
        return "raw_size_bytes não é o tamanho de raw_bytes"
    source = envelope.source
    if source.sha256 is not None and source.sha256 != envelope.raw_sha256:
        return "source.sha256 declarado difere do hash de raw_bytes"
    if source.size_bytes is not None and source.size_bytes != len(raw):
        return "source.size_bytes declarado difere do tamanho de raw_bytes"
    expected_origin = "synthetic" if source.artifact_type == "synthetic_fixture" else "real"
    if envelope.origin != expected_origin:
        return f"origin {envelope.origin} não corresponde a source.artifact_type"
    try:
        root = parse_json_strict(raw.decode("utf-8"))
    except (UnicodeDecodeError, CanonicalJSONError) as exc:
        return f"raw_bytes não é JSON estrito ({exc})"
    if canonical_json_text(root) != envelope.payload_json:
        return "payload_json não é a forma canônica de raw_bytes"
    declared = (
        envelope.organization_code,
        envelope.dictionary_code,
        envelope.dictionary_version,
        envelope.language_iso_code,
    )
    if not isinstance(root, dict) or declared != tuple(
        root.get(name)
        for name in ("OrganizationCode", "DictionaryCode", "DictionaryVersion", "LanguageIsoCode")
    ):
        return "identidade do dicionário difere do payload"
    return None


class BSDDEntity(CatalogModel):
    """Classe, propriedade ou associação preservada integralmente no staging.

    ``fields_json`` guarda, em JSON canônico, todos os campos da entidade como vieram
    (inclusive desconhecidos), exceto as associações de classe, que são entidades
    próprias. ``origin_key`` localiza a entidade entre versões e não prova
    equivalência; ``source_key`` identifica a proposta desta versão.
    """

    entity_kind: EntityKind
    origin_key: NonEmptyText
    source_key: NonEmptyText
    code_literal: str | None = None
    name_literal: str | None = None
    owned_uri_literal: str | None = None
    class_code_literal: str | None = None
    property_ref: Literal["local_code", "external_uri"] | None = None
    property_code_literal: str | None = None
    property_uri_literal: str | None = None
    normalized_pointer: NonEmptyText
    fields_json: NonEmptyText


class BSDDStaging(CatalogModel):
    """Conteúdo semântico normalizado de uma versão do dicionário, sem recibo bruto."""

    profile: Literal["ifcqc-bsdd-import-subset-1"]
    normalization_rule: Literal["ifcqc-bsdd-normalization-1"]
    model_version: Literal["2.0"]
    organization_code: NonEmptyText
    dictionary_code: NonEmptyText
    dictionary_version: NonEmptyText
    language_iso_code: NonEmptyText
    semantic_sha256: Sha256Hex
    dictionary_json: NonEmptyText
    entities: tuple[BSDDEntity, ...]

    def entity(self, kind: str, code: str) -> BSDDEntity:
        """Entidade pelo tipo e código (comparação sem caixa, como no bSDD)."""
        key = code.casefold()
        for item in self.entities:
            if item.entity_kind == kind and (item.code_literal or "").casefold() == key:
                return item
        raise KeyError(f"{kind} {code}")


class ReportItem(CatalogModel):
    """Destino de um campo ou entidade: projetado, preservado, pendente ou rejeitado."""

    pointer: NonEmptyText
    field: str | None = None
    entity_code: str | None = None
    code: NonEmptyText
    status: ItemStatus
    severity: ItemSeverity
    effect: ItemEffect
    reason: NonEmptyText


class BSDDImportReport(CatalogModel):
    """Relatório da importação; não aprova nem publica nada."""

    profile: Literal["ifcqc-bsdd-import-subset-1"]
    origin: SnapshotOrigin
    usage_status: UsageStatus
    distribution_gate: DistributionGate
    counts: dict[str, int]
    items: tuple[ReportItem, ...]


class AcquisitionLink(CatalogModel):
    """Vínculo raw→normalized de uma entidade nesta aquisição."""

    entity_kind: EntityKind
    origin_key: NonEmptyText
    source_key: NonEmptyText
    raw_pointer: NonEmptyText
    normalized_pointer: NonEmptyText
    assertion_id: str | None = None


class BSDDAcquisition(CatalogModel):
    """Recibo da aquisição: bytes brutos, regra, normalizado e ponteiros de cada entidade."""

    profile: Literal["ifcqc-bsdd-import-subset-1"]
    normalization_rule: Literal["ifcqc-bsdd-normalization-1"]
    source: SourceArtifact
    origin: SnapshotOrigin
    usage_status: UsageStatus
    limits: SnapshotLimits
    raw_sha256: Sha256Hex
    raw_size_bytes: CountInt
    normalized_sha256: Sha256Hex
    normalized_size_bytes: CountInt
    links: tuple[AcquisitionLink, ...]


class PendingMigration(CatalogModel):
    """Mesma origem em outra versão: só a curadoria explícita associa os candidatos."""

    origin_key: NonEmptyText
    entity_kind: EntityKind
    from_source_key: NonEmptyText
    to_source_key: NonEmptyText
    status: Literal["pending_curation"] = "pending_curation"


class DiffEntry(CatalogModel):
    """Entidade incluída ou removida entre dois stagings."""

    origin_key: NonEmptyText
    entity_kind: EntityKind
    code_literal: str | None = None


class DiffChange(CatalogModel):
    """Entidade presente nos dois stagings com campos alterados."""

    origin_key: NonEmptyText
    entity_kind: EntityKind
    code_literal: str | None = None
    fields: tuple[str, ...]


class BSDDStagingDiff(CatalogModel):
    """Delta revisável por identidade de origem; não é diff de release."""

    before_version: NonEmptyText
    after_version: NonEmptyText
    before_semantic_sha256: Sha256Hex
    after_semantic_sha256: Sha256Hex
    dictionary_fields_changed: tuple[str, ...] = ()
    added: tuple[DiffEntry, ...] = ()
    removed: tuple[DiffEntry, ...] = ()
    changed: tuple[DiffChange, ...] = ()
    unchanged: CountInt = 0

    @property
    def is_empty(self) -> bool:
        """Sem inclusão, remoção ou mudança de entidade ou de campo do dicionário."""
        return not (self.dictionary_fields_changed or self.added or self.removed or self.changed)


class BSDDImportResult(CatalogModel):
    """Staging, relatório, recibo de aquisição e candidatos em rascunho (ou ``None``)."""

    staging: BSDDStaging
    report: BSDDImportReport
    acquisition: BSDDAcquisition
    content: CatalogContent | None
    raw_bytes: bytes
    normalized_bytes: bytes
    prior: BSDDStaging | None = None
    diff: BSDDStagingDiff | None = None
    migrations: tuple[PendingMigration, ...] = ()


class StagingFile(CatalogModel):
    """Arquivo do staging gravado, com tamanho e hash."""

    path: NonEmptyText
    bytes: CountInt
    sha256: Sha256Hex


class BSDDStagingManifest(CatalogModel):
    """Manifesto de um staging gravado; reaberto e conferido antes de qualquer handoff."""

    format: Literal["ifcqc-bsdd-staging-1"]
    format_version: FormatVersionOne
    profile: Literal["ifcqc-bsdd-import-subset-1"]
    normalization_rule: Literal["ifcqc-bsdd-normalization-1"]
    source: SourceArtifact
    limits: SnapshotLimits
    usage_status: UsageStatus
    raw_sha256: Sha256Hex
    semantic_sha256: Sha256Hex
    content_sha256: Sha256Hex | None
    files: tuple[StagingFile, ...]
