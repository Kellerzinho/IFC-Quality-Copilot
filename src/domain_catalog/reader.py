"""Reader de pacote local fixado (plano M1 §6.1; M1-06).

``open_catalog`` abre um release pela referência exata (ID, versão e hash do
manifesto) numa pasta local, confere layout, limites, hashes, forma canônica e
conteúdo publicável, e devolve um ``CatalogReader`` imutável. Qualquer falha levanta
``CatalogPackageError`` com a causa; nunca há catálogo vazio, outra versão, cache
legado nem consulta pública. Depois de aberto, o reader não toca disco nem rede.
"""

import hashlib
import os
import re
import unicodedata
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, TypeVar

from pydantic import ValidationError

from src.domain_catalog.canonical import CanonicalJSONError, load_canonical_json
from src.domain_catalog.content import CatalogContent, validate_content
from src.domain_catalog.contracts import (
    BindingPage,
    BindingQuery,
    BindingRequest,
    CandidatePage,
    CatalogQuery,
    CatalogReleaseRef,
    ConceptSummary,
    OperationCapability,
    ResolutionResult,
)
from src.domain_catalog.errors import (
    CatalogEntityNotFoundError,
    CatalogPackageError,
    CatalogValidationError,
)
from src.domain_catalog.models import ConceptDefinition, EvidencePolicy, IFCBinding
from src.domain_catalog.operations import DEFAULT_OPERATION_REGISTRY, OperationRegistry
from src.domain_catalog.package import (
    DATA_FILES,
    ENTITY_MODELS,
    MANIFEST_FILE,
    PACKAGE_FORMAT,
    PACKAGE_FORMAT_VERSION,
    CatalogManifest,
    PackageLimits,
    derived_summary,
)
from src.domain_catalog.resolver import Resolver

_ALLOWED_NAMES = frozenset({MANIFEST_FILE, *DATA_FILES.values()})


def search_key(text: str) -> str:
    """Chave de busca sem caixa, acentos e separadores; serve só para localizar."""
    decomposed = unicodedata.normalize("NFKD", text)
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^0-9a-z]+", " ", plain.casefold()).split())


def _io_error(action: str, path: Path, exc: OSError) -> CatalogPackageError:
    """Falha do sistema de arquivos com a causa encadeada; nunca vira catálogo vazio."""
    return CatalogPackageError("io", f"falha ao {action} {path.name}: {exc.strerror or exc}")


def _check_layout(release_dir: Path) -> None:
    """Somente os arquivos do formato, regulares e sem links."""
    present: set[str] = set()
    try:
        with os.scandir(release_dir) as entries:
            for entry in entries:
                if entry.name not in _ALLOWED_NAMES:
                    raise CatalogPackageError(
                        "layout", f"entrada inesperada no pacote: {entry.name}"
                    )
                if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                    raise CatalogPackageError("layout", f"{entry.name} não é arquivo regular")
                present.add(entry.name)
    except OSError as exc:
        raise _io_error("listar", release_dir, exc) from exc
    missing = sorted(_ALLOWED_NAMES - present)
    if missing:
        raise CatalogPackageError("layout", f"arquivos ausentes no pacote: {missing}")


def _read_limited(path: Path, limit: int) -> bytes:
    """Lê no máximo ``limit + 1`` bytes; arquivo maior é recusado antes de interpretar."""
    try:
        with path.open("rb") as handle:
            data = handle.read(limit + 1)
    except OSError as exc:
        raise _io_error("ler", path, exc) from exc
    if len(data) > limit:
        raise CatalogPackageError("limit", f"{path.name} excede {limit} bytes")
    return data


def _load(data: bytes, name: str) -> Any:
    try:
        return load_canonical_json(data)
    except CanonicalJSONError as exc:
        raise CatalogPackageError("format", f"{name}: {exc}") from exc


def _is_supported_format(raw: object) -> bool:
    """Formato e versão exatos; a versão é o inteiro 1, nunca ``true`` nem ``1.0``."""
    if not isinstance(raw, dict) or raw.get("format") != PACKAGE_FORMAT:
        return False
    version = raw.get("format_version")
    return type(version) is int and version == PACKAGE_FORMAT_VERSION


def _manifest(data: bytes, ref: CatalogReleaseRef) -> CatalogManifest:
    """Manifesto do formato suportado e coerente com a referência pedida."""
    raw = _load(data, MANIFEST_FILE)
    if not _is_supported_format(raw):
        found = (raw.get("format"), raw.get("format_version")) if isinstance(raw, dict) else raw
        raise CatalogPackageError("format", f"formato de pacote não suportado: {found!r}")
    try:
        manifest = CatalogManifest.model_validate(raw)
    except ValidationError as exc:
        raise CatalogPackageError("format", f"manifesto inválido: {exc}") from exc
    if (manifest.catalog.catalog_id, manifest.version) != (ref.catalog_id, ref.version):
        raise CatalogPackageError(
            "integrity",
            f"manifesto é de {manifest.catalog.catalog_id} {manifest.version}, "
            f"não da referência {ref.catalog_id} {ref.version}",
        )
    return manifest


def open_catalog(
    ref: CatalogReleaseRef,
    release_dir: Path,
    *,
    limits: PackageLimits | None = None,
    registry: OperationRegistry = DEFAULT_OPERATION_REGISTRY,
) -> "CatalogReader":
    """Abre e valida integralmente o release fixado; falha nunca vira catálogo vazio."""
    limits = limits or PackageLimits()
    try:
        found = release_dir.is_dir()
    except OSError as exc:
        raise _io_error("acessar", release_dir, exc) from exc
    if not found:
        raise CatalogPackageError("not_found", f"release {ref.version} ausente em {release_dir}")
    _check_layout(release_dir)
    manifest_bytes = _read_limited(release_dir / MANIFEST_FILE, limits.max_manifest_bytes)
    if hashlib.sha256(manifest_bytes).hexdigest() != ref.manifest_sha256:
        raise CatalogPackageError("integrity", "hash do manifesto difere da referência fixada")
    manifest = _manifest(manifest_bytes, ref)
    total_bytes = 0
    total_entities = 0
    entities: dict[str, Any] = {}
    for item in manifest.files:
        data = _read_limited(release_dir / item.path, limits.max_file_bytes)
        total_bytes += len(data)
        if total_bytes > limits.max_total_bytes:
            raise CatalogPackageError("limit", f"pacote excede {limits.max_total_bytes} bytes")
        if len(data) != item.bytes or hashlib.sha256(data).hexdigest() != item.sha256:
            raise CatalogPackageError("integrity", f"{item.path} difere do manifesto")
        rows = _load(data, item.path)
        if not isinstance(rows, list) or len(rows) != item.entries:
            raise CatalogPackageError("format", f"{item.path} não tem {item.entries} entradas")
        total_entities += len(rows)
        if total_entities > limits.max_entities:
            raise CatalogPackageError("limit", f"pacote excede {limits.max_entities} entidades")
        model = ENTITY_MODELS[item.kind]
        try:
            entities[item.kind] = tuple(model.model_validate(row) for row in rows)
        except ValidationError as exc:
            raise CatalogPackageError("content", f"{item.path}: {exc}") from exc
        _check_id_order(entities[item.kind], item.path)
    content = CatalogContent.model_validate(entities)
    try:
        validate_content(content, for_release=True)
    except CatalogValidationError as exc:
        raise CatalogPackageError("content", str(exc), exc.issues) from exc
    _check_summary(manifest, content)
    return CatalogReader(ref, manifest, content, registry)


def _check_id_order(rows: tuple[Any, ...], name: str) -> None:
    """Entidades em ordem crescente de ID, como o builder grava; outra ordem não é canônica."""
    ids = [row.id for row in rows]
    if ids != sorted(ids):
        raise CatalogPackageError("format", f"{name}: entidades fora da ordem canônica por ID")


def _check_summary(manifest: CatalogManifest, content: CatalogContent) -> None:
    """Perfis e schemas do manifesto coincidem com os derivados do conteúdo carregado."""
    profiles, schemas = derived_summary(content)
    if manifest.declared_schemas != schemas:
        raise CatalogPackageError(
            "format",
            f"manifesto declara schemas {list(manifest.declared_schemas)}; "
            f"os bindings declaram {list(schemas)}",
        )
    if manifest.profiles != profiles:
        raise CatalogPackageError(
            "format",
            f"manifesto declara perfis {list(manifest.profiles)}; "
            f"as participações formam {list(profiles)}",
        )


_Item = TypeVar("_Item")


def _paginate(items: list[_Item], offset: int, limit: int) -> tuple[_Item, ...]:
    return tuple(items[offset : offset + limit])


class CatalogReader:
    """Consulta somente leitura de um release aberto; permanece o mesmo durante a análise."""

    def __init__(
        self,
        ref: CatalogReleaseRef,
        manifest: CatalogManifest,
        content: CatalogContent,
        registry: OperationRegistry,
    ) -> None:
        """Monta índices a partir do conteúdo validado; não lê disco."""
        self._ref = ref
        self._manifest = manifest
        self._content = content
        self._registry = registry
        self._resolver = Resolver(content, ref)
        self._concepts = {concept.id: concept for concept in content.concepts}
        self._bindings = {binding.id: binding for binding in content.bindings}
        self._policies = {policy.id: policy for policy in content.evidence_policies}
        self._rules = {rule.id: rule for rule in content.applicability_rules}
        self._artifact_of = {a.id: a.source_artifact_id for a in content.source_assertions}
        self._profiles: dict[str, set[str]] = {}
        for membership in content.profile_memberships:
            self._profiles.setdefault(membership.binding_id, set()).add(membership.profile_id)
        self._bindings_of: dict[str, list[IFCBinding]] = {}
        for binding in sorted(content.bindings, key=lambda b: b.id):
            self._bindings_of.setdefault(binding.concept_id, []).append(binding)
        self._alias_terms: dict[str, list[str]] = {}
        for alias in content.aliases:
            target = (
                alias.target_concept_id or self._bindings[alias.target_binding_id or ""].concept_id
            )
            self._alias_terms.setdefault(target, []).append(alias.term)

    @property
    def ref(self) -> CatalogReleaseRef:
        """Referência exata do release aberto."""
        return self._ref

    @property
    def content(self) -> CatalogContent:
        """Conteúdo imutável do release."""
        return self._content

    def describe(self) -> CatalogManifest:
        """Manifesto do release: identidade, origem do conteúdo, termos e arquivos."""
        return self._manifest

    def _get(self, index: Mapping[str, _Item], entity_id: str, kind: str) -> _Item:
        try:
            return index[entity_id]
        except KeyError:
            raise CatalogEntityNotFoundError(
                f"{kind} {entity_id} não existe no release {self._ref.version}"
            ) from None

    def get_concept(self, concept_id: str) -> ConceptDefinition:
        """Conceito pelo ID estável."""
        return self._get(self._concepts, concept_id, "conceito")

    def get_binding(self, binding_id: str) -> IFCBinding:
        """Binding pelo ID estável."""
        return self._get(self._bindings, binding_id, "binding")

    def get_evidence_policy(self, policy_id: str) -> EvidencePolicy:
        """Política de evidência pelo ID estável."""
        return self._get(self._policies, policy_id, "política")

    def get_capability(self, operation_id: str, version: str | None = None) -> OperationCapability:
        """Disponibilidade da operação no código instalado, não no cadastro."""
        return self._registry.capability(operation_id, version)

    def resolve_binding(self, request: BindingRequest) -> ResolutionResult:
        """Resolução com estado explícito e identidade deste release."""
        return self._resolver.resolve(request)

    def _binding_matches_entity(self, binding: IFCBinding, entity: str) -> bool:
        classes = self._rules[binding.applicability_rule_id].entity_classes
        return entity.upper() in {name.upper() for name in classes}

    def _concept_cites_artifact(self, concept: ConceptDefinition, artifact_id: str) -> bool:
        assertion_ids: Iterable[str] = [
            *concept.source_assertion_ids,
            *(a for b in self._bindings_of.get(concept.id, []) for a in b.source_assertion_ids),
        ]
        return any(self._artifact_of.get(a) == artifact_id for a in assertion_ids)

    def _matched_by(self, concept: ConceptDefinition, key: str) -> tuple[str, ...]:
        fields: list[tuple[str, Iterable[str]]] = [
            ("code", [concept.code]),
            ("label", [text.text for text in concept.labels]),
            ("definition", [text.text for text in concept.definition]),
            (
                "binding",
                [
                    f"{b.set_name or ''} {b.field_name}"
                    for b in self._bindings_of.get(concept.id, [])
                ],
            ),
            ("alias", self._alias_terms.get(concept.id, [])),
        ]
        return tuple(
            name for name, texts in fields if any(key in search_key(text) for text in texts)
        )

    def search(self, query: CatalogQuery) -> CandidatePage:
        """Conceitos que atendem a todos os filtros, ordenados por código e ID."""
        key = search_key(query.text) if query.text else None
        found: list[ConceptSummary] = []
        for concept in sorted(self._content.concepts, key=lambda c: (c.code, c.id)):
            bindings = self._bindings_of.get(concept.id, [])
            matched_by: tuple[str, ...] = ()
            if key is not None:
                matched_by = self._matched_by(concept, key)
                if not matched_by:
                    continue
            if query.entity and not any(
                self._binding_matches_entity(b, query.entity) for b in bindings
            ):
                continue
            if query.carrier_kind and not any(
                b.carrier_kind == query.carrier_kind for b in bindings
            ):
                continue
            if query.profile_id and not any(
                query.profile_id in self._profiles.get(b.id, set()) for b in bindings
            ):
                continue
            if query.source_artifact_id and not self._concept_cites_artifact(
                concept, query.source_artifact_id
            ):
                continue
            if query.lifecycle and concept.lifecycle != query.lifecycle:
                continue
            label = next(
                (t.text for t in concept.labels if t.lang == "pt-BR"), concept.labels[0].text
            )
            found.append(
                ConceptSummary(
                    concept_id=concept.id,
                    code=concept.code,
                    label=label,
                    lifecycle=concept.lifecycle,
                    binding_ids=tuple(b.id for b in bindings),
                    matched_by=matched_by,
                )
            )
        return CandidatePage(
            items=_paginate(found, query.offset, query.limit),
            total=len(found),
            offset=query.offset,
            limit=query.limit,
        )

    def list_bindings(self, query: BindingQuery) -> BindingPage:
        """Bindings que atendem a todos os filtros, ordenados por ID."""
        found = [
            b
            for b in sorted(self._content.bindings, key=lambda b: b.id)
            if (query.concept_id is None or b.concept_id == query.concept_id)
            and (query.entity is None or self._binding_matches_entity(b, query.entity))
            and (query.set_name is None or b.set_name == query.set_name)
            and (query.field_name is None or b.field_name == query.field_name)
            and (query.carrier_kind is None or b.carrier_kind == query.carrier_kind)
            and (query.profile_id is None or query.profile_id in self._profiles.get(b.id, set()))
        ]
        return BindingPage(
            items=_paginate(found, query.offset, query.limit),
            total=len(found),
            offset=query.offset,
            limit=query.limit,
        )
