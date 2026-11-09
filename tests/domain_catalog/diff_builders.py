"""Construtores SINTÉTICOS para os testes de diff/impacto (E3.2a).

IDs ``urn:uuid`` literais e nomes ``SYN_*``; nada vem de fonte real. Cada cenário
declara explicitamente as relações que existem — a ausência de outras arestas faz
parte do cenário.
"""

from pathlib import Path
from typing import Any

from src.domain_catalog.content import CatalogContent
from src.domain_catalog.contracts import CatalogReleaseRef
from src.domain_catalog.models import (
    AliasMapping,
    AliasScope,
    AllowedValue,
    AllowedValueSet,
    ApplicabilityRule,
    CatalogModel,
    ConceptDefinition,
    EvidencePolicy,
    IFCBinding,
    LocalizedText,
    ProfileMembership,
    ReconciliationDecision,
    SourceArtifact,
    SourceAssertion,
    SourceLocator,
    UnitDefinition,
)
from src.domain_catalog.package import (
    CatalogIdentity,
    ComponentTerms,
    ContentOrigin,
    build_release_files,
    write_release_dir,
)
from src.domain_catalog.reader import CatalogReader, open_catalog
from tests.domain_catalog import factories as f

TERMS = (ComponentTerms(component="conteúdo", terms="sintético, sem terceiros"),)
ARTIFACT = "synthetic:diff-fonte"
ASSERTION = "synthetic:diff-linha-1"


def uid(n: int) -> str:
    """UUID literal sintético do cenário."""
    return f"urn:uuid:00000000-0000-4000-8000-{0xD000 + n:012x}"


def pt(text: str) -> tuple[LocalizedText, ...]:
    """Texto único em pt-BR."""
    return (LocalizedText(lang="pt-BR", text=text),)


def artifact(aid: str = ARTIFACT, title: str = "Fonte sintética de diff") -> SourceArtifact:
    """Artefato sintético."""
    return SourceArtifact(id=aid, title=title, artifact_type="synthetic_fixture", terms="sintético")


def assertion(
    sid: str = ASSERTION, artifact_id: str = ARTIFACT, notes: tuple[str, ...] = ()
) -> SourceAssertion:
    """Linha sintética ligada ao artefato."""
    return SourceAssertion(
        id=sid,
        source_artifact_id=artifact_id,
        locator=SourceLocator(table="T", row_ref=sid.rsplit("-", 1)[-1]),
        category="custom_property",
        target_literal="SYN",
        notes=notes,
        transcription_status="registered",
    )


def concept(cid: str, code: str = "SYN_C", **changes: Any) -> ConceptDefinition:
    """Conceito textual aprovado."""
    data: dict[str, Any] = {
        "id": cid,
        "code": code,
        "labels": pt(code),
        "definition": pt(f"Conceito sintético {code}."),
        "logical_type": "code",
        "lifecycle": "approved",
    }
    data.update(changes)
    return ConceptDefinition.model_validate(data)


def unit(uid_: str, symbol: str = "m", dimension: str = "length", **changes: Any) -> UnitDefinition:
    """Unidade aprovada."""
    return UnitDefinition.model_validate(
        {"id": uid_, "symbol": symbol, "dimension": dimension, "lifecycle": "approved", **changes}
    )


def value_set(vid: str, codes: tuple[Any, ...] = ("A", "B"), **changes: Any) -> AllowedValueSet:
    """Conjunto aprovado de códigos (texto por padrão)."""
    data: dict[str, Any] = {
        "id": vid,
        "value_type": "code",
        "values": tuple(AllowedValue(code=c) for c in codes),
        "lifecycle": "approved",
    }
    data.update(changes)
    return AllowedValueSet.model_validate(data)


def rule(rid: str, entity: str = "IfcWall", **changes: Any) -> ApplicabilityRule:
    """Regra exata para uma classe, sem subtipos."""
    return ApplicabilityRule.model_validate(
        {
            "id": rid,
            "entity_classes": (entity,),
            "include_subtypes": False,
            "lifecycle": "approved",
            **changes,
        }
    )


def policy(
    pid: str, operation_id: str = "recover_exact_property", **changes: Any
) -> EvidencePolicy:
    """Política aprovada (cadastro não cria executor)."""
    data: dict[str, Any] = {
        "id": pid,
        "operation_id": operation_id,
        "operation_version": "1.0.0",
        "admissible_channels": ("P",),
        "on_missing": "abstain",
        "on_conflict": "abstain",
        "lifecycle": "approved",
    }
    data.update(changes)
    return EvidencePolicy.model_validate(data)


def binding(bid: str, concept_id: str, rule_id: str, **changes: Any) -> IFCBinding:
    """Propriedade aprovada em conjunto personalizado."""
    data: dict[str, Any] = {
        "id": bid,
        "concept_id": concept_id,
        "applicability_rule_id": rule_id,
        "declared_schemas": ("IFC4",),
        "carrier_kind": "property",
        "set_name": "SYN_Pset",
        "field_name": f"Campo{bid[-3:]}",
        "set_kind": "custom",
        "ifc_type": "IfcLabel",
        "scope": "occurrence",
        "carrier_status": "approved",
        "lifecycle": "approved",
    }
    data.update(changes)
    return IFCBinding.model_validate(data)


def alias(aid: str, term: str, **changes: Any) -> AliasMapping:
    """Alias de busca global (localiza, não resolve), salvo mudança explícita."""
    data: dict[str, Any] = {
        "id": aid,
        "term": term,
        "purpose": "search",
        "scope": AliasScope(),
        "lifecycle": "approved",
    }
    data.update(changes)
    return AliasMapping.model_validate(data)


def membership(mid: str, binding_id: str, profile: str = "perfil-a") -> ProfileMembership:
    """Participação em perfil."""
    return ProfileMembership(
        id=mid,
        profile_id=profile,
        binding_id=binding_id,
        source_assertion_ids=(ASSERTION,),
        lifecycle="approved",
    )


def decision(did: str, bindings: tuple[str, ...], **changes: Any) -> ReconciliationDecision:
    """Decisão cadastral pendente (não aprova valor de elemento)."""
    data: dict[str, Any] = {
        "id": did,
        "code": f"syn-{did[-3:]}",
        "status": "pending",
        "source_assertion_ids": (ASSERTION,),
        "summary": "Divergência sintética.",
        "affected_binding_ids": bindings,
    }
    data.update(changes)
    return ReconciliationDecision.model_validate(data)


def content(*entities: tuple[str, CatalogModel]) -> CatalogContent:
    """Conteúdo com a fonte sintética padrão mais as entidades dadas."""
    grouped: dict[str, list[CatalogModel]] = {
        "source_artifacts": [artifact()],
        "source_assertions": [assertion()],
    }
    for kind, entity in entities:
        bucket = grouped.setdefault(kind, [])
        bucket[:] = [item for item in bucket if item.id != entity.id]  # type: ignore[attr-defined]
        bucket.append(entity)
    return CatalogContent.model_validate({k: tuple(v) for k, v in grouped.items()})


def replace(content_: CatalogContent, kind: str, entity_id: str, **changes: Any) -> CatalogContent:
    """Mesma coleção com uma entidade revalidada com as mudanças dadas."""
    items = []
    for item in getattr(content_, kind):
        if item.id == entity_id:
            item = type(item).model_validate({**item.model_dump(), **changes})
        items.append(item)
    return content_.model_copy(update={kind: tuple(items)})


def identity(**changes: Any) -> CatalogIdentity:
    """Identidade do catálogo sintético, com mudanças opcionais."""
    return f.catalog_identity().model_copy(update=changes)


def write(
    base: Path,
    content_: CatalogContent,
    version: str = "1.0.0",
    *,
    folder: str | None = None,
    created_at: str = "2026-10-22T00:00:00Z",
    catalog: CatalogIdentity | None = None,
    origin: ContentOrigin = "synthetic_fixture",
    terms: tuple[ComponentTerms, ...] = TERMS,
    previous: CatalogReleaseRef | None = None,
) -> tuple[CatalogReleaseRef, Path]:
    """Grava um release sintético em pasta nova e devolve referência e pasta."""
    files = build_release_files(
        content_,
        catalog=catalog or identity(),
        version=version,
        created_at=created_at,
        content_origin=origin,
        terms=terms,
        previous_release=previous,
    )
    target = base / (folder or version)
    return write_release_dir(files, target), target


def opened(
    base: Path, content_: CatalogContent, version: str = "1.0.0", **kw: Any
) -> CatalogReader:
    """Grava e reabre pelo reader real."""
    ref, path = write(base, content_, version, **kw)
    return open_catalog(ref, path)
