"""Cenários SINTÉTICOS de M3: catálogo, IFC e IDS reais, avaliados pelo backend fixado.

Binding ``SYN_Conjunto.SYN_Metodo`` (ocorrência, propriedade aprovada, IfcLabel) em
``IfcSlab``, com política de evidência e aliases configuráveis. Nada aqui é dado real.
"""

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ifcopenshell

from src.domain_catalog.content import CatalogContent
from src.domain_catalog.models import (
    AliasMapping,
    AliasScope,
    AllowedValue,
    AllowedValueSet,
    ConceptDefinition,
    EvidencePolicy,
    IFCBinding,
)
from src.domain_catalog.reader import CatalogReader, open_catalog
from src.ifc_analyzer.observations import IfcObservationReader
from src.ifc_analyzer.read_only import ReadOnlyIfcSession
from src.suggestion_engine.catalog_operations import E3OperationBundle, build_e3_operation_bundle
from src.validation.analysis_service import attach_catalog_annotations
from src.validation.diagnostic_models import DiagnosticSnapshot, RequirementResult
from src.validation.ids_engine import IdsEngine
from tests.domain_catalog import factories as f
from tests.validation import ids_builders as x
from tests.validation import ifc_builders as ib
from tests.validation.engine_helpers import bundle as ids_bundle
from tests.validation.engine_helpers import prepare

POLICY = "urn:uuid:00000000-0000-4000-8000-00000000e301"
VALUES = "urn:uuid:00000000-0000-4000-8000-00000000e302"
ALIAS = "urn:uuid:00000000-0000-4000-8000-00000000e303"
OTHER_BINDING = "urn:uuid:00000000-0000-4000-8000-00000000e304"
OTHER_CONCEPT = "urn:uuid:00000000-0000-4000-8000-00000000e305"

TARGET = x.prop("SYN_Conjunto", "SYN_Metodo")


def content(
    *,
    operation: str = "recover_exact_property",
    version: str | None = "1.0.0",
    channels: tuple[str, ...] = ("P", "T"),
    preconditions: tuple[str, ...] = (),
    on_missing: str = "abstain",
    on_conflict: str = "abstain",
    scope: str = "occurrence",
    carrier_status: str = "approved",
    codes: tuple[str, ...] | None = None,
    aliases: tuple[AliasMapping, ...] | None = None,
    policy: bool = True,
    extra_bindings: tuple[IFCBinding, ...] = (),
    extra_concepts: tuple[ConceptDefinition, ...] = (),
) -> CatalogContent:
    """Catálogo publicável com o binding alvo e a política escolhida."""
    concept = f.concept().model_copy(update={"value_set_id": VALUES if codes else None})
    binding_changes: dict[str, Any] = {
        "scope": scope,
        "carrier_status": carrier_status,
        "evidence_policy_id": POLICY if policy else None,
    }
    if carrier_status != "approved":
        binding_changes["ifc_type"] = None
    binding = IFCBinding.model_validate({**f.binding().model_dump(), **binding_changes})
    policies: tuple[EvidencePolicy, ...] = ()
    if policy:
        policies = (
            EvidencePolicy(
                id=POLICY,
                operation_id=operation,
                operation_version=version,
                admissible_channels=channels,  # type: ignore[arg-type]
                preconditions=preconditions,
                on_missing=on_missing,  # type: ignore[arg-type]
                on_conflict=on_conflict,  # type: ignore[arg-type]
                lifecycle="approved",
            ),
        )
    value_sets: tuple[AllowedValueSet, ...] = ()
    if codes:
        value_sets = (
            AllowedValueSet(
                id=VALUES,
                value_type="code",
                values=tuple(AllowedValue(code=c) for c in codes),
                lifecycle="approved",
            ),
        )
    if aliases is None:
        aliases = (alias(),)
    return CatalogContent(
        source_artifacts=(f.source_artifact(),),
        source_assertions=(f.source_assertion(),),
        concepts=(concept, *extra_concepts),
        value_sets=value_sets,
        applicability_rules=(f.rule(),),
        evidence_policies=policies,
        bindings=(binding, *extra_bindings),
        aliases=aliases,
    )


def alias(
    alias_id: str = ALIAS,
    term: str = "Metodo",
    *,
    sets: tuple[str, ...] | None = ("SYN_Legado",),
    purpose: str = "representation_match",
    target: str = f.BINDING_ID,
    entity_classes: tuple[str, ...] | None = None,
    lifecycle: str = "approved",
) -> AliasMapping:
    """Alias com finalidade e escopo explícitos."""
    return AliasMapping(
        id=alias_id,
        term=term,
        purpose=purpose,  # type: ignore[arg-type]
        scope=AliasScope(set_names=sets, entity_classes=entity_classes),
        target_binding_id=target,
        lifecycle=lifecycle,  # type: ignore[arg-type]
    )


def slab(model: ifcopenshell.file, *sets: tuple[str, str, Any, str]) -> Any:
    """Laje com conjuntos de ocorrência ``(set, campo, valor, tipo IFC)``."""
    element = ib.element(model, "IfcSlab")
    for set_name, field_name, value, ifc_type in sets:
        ib.pset(model, element, set_name, [ib.single(model, field_name, ifc_type, value)])
    return element


@dataclass
class M3Case:
    """Snapshot formal anotado, sessão, reader do release, bundle e leitor de observações."""

    snapshot: DiagnosticSnapshot
    session: ReadOnlyIfcSession
    reader: CatalogReader
    bundle: E3OperationBundle
    observations: IfcObservationReader

    def row(self, index: int = 0) -> RequirementResult:
        """Linha de requisito com elemento, na ordem do snapshot."""
        return [r for r in self.snapshot.requirements if r.element is not None][index]


def case(
    tmp_path: Path,
    catalog: CatalogContent,
    model: ifcopenshell.file,
    requirement: str = TARGET,
) -> M3Case:
    """Avalia IDS/IFC pelo backend real, abre o release com o bundle e anexa o catálogo."""
    session, document, identity = prepare(
        tmp_path / "m", model, x.ids(x.spec("Lajes", x.entity("IFCSLAB"), requirement))
    )
    snapshot = IdsEngine(ids_bundle()).evaluate(session, document, identity)
    operations = build_e3_operation_bundle()
    ref, folder = f.write_synthetic_release(tmp_path / f"c-{uuid.uuid4().hex[:6]}", catalog)
    reader = open_catalog(ref, folder, registry=operations.registry)
    return M3Case(
        snapshot=attach_catalog_annotations(snapshot, reader),
        session=session,
        reader=reader,
        bundle=operations,
        observations=IfcObservationReader(session, identity.analysis_id),
    )
