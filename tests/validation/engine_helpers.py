"""Execução do motor IDS real sobre modelos e IDS sintéticos, para os testes M2."""

import uuid
from pathlib import Path

import ifcopenshell

from src.domain_catalog.curation import utc_now
from src.ifc_analyzer.read_only import ReadOnlyIfcSession
from src.operations.contracts import SourceArtifactRef
from src.translator.ids_document import IDSDocument, parse_ids_document
from src.validation.analysis_identity import AnalysisIdentity, current_execution_profile
from src.validation.diagnostic_models import DiagnosticSnapshot, RequirementResult
from src.validation.ids_engine import IdsEngine
from src.validation.schema_bundle import SchemaBundle
from tests.validation import ifc_builders as ib

_BUNDLE: SchemaBundle | None = None


def bundle() -> SchemaBundle:
    """Bundle oficial carregado uma vez por processo de teste."""
    global _BUNDLE
    if _BUNDLE is None:
        _BUNDLE = SchemaBundle.load()
    return _BUNDLE


def identity_for(ifc: SourceArtifactRef, ids: SourceArtifactRef) -> AnalysisIdentity:
    """Identidade sem catálogo, com o perfil de execução real do runtime."""
    profile = current_execution_profile()
    return AnalysisIdentity(
        project_id=ifc.project_id,
        analysis_id=uuid.uuid4(),
        pair_id=uuid.uuid4(),
        pair_revision=1,
        ifc=ifc,
        ids=ids,
        catalog_state="not_attached",
        verifier=profile.verifier,
        condition_id=profile.condition_id,
        condition_config_sha256=profile.condition_config_sha256,
        limits=profile.limits,
    )


def prepare(
    tmp_path: Path, model: ifcopenshell.file, ids_bytes: bytes
) -> tuple[ReadOnlyIfcSession, IDSDocument, AnalysisIdentity]:
    """Grava/reabre o IFC, valida o IDS pelo bundle e monta a identidade."""
    path, ifc_ref = ib.write(model, tmp_path / f"m-{uuid.uuid4().hex[:8]}.ifc")
    session = ReadOnlyIfcSession.open(ifc_ref, path)
    document = parse_ids_document(ids_bytes, bundle())
    return session, document, identity_for(ifc_ref, ib.ids_ref(ids_bytes))


def run(tmp_path: Path, model: ifcopenshell.file, ids_bytes: bytes) -> DiagnosticSnapshot:
    """Avaliação formal completa pelo backend real."""
    session, document, identity = prepare(tmp_path, model, ids_bytes)
    return IdsEngine(bundle()).evaluate(session, document, identity, clock=utc_now)


def rows(
    snapshot: DiagnosticSnapshot, spec: int = 0, requirement: int | None = None
) -> list[RequirementResult]:
    """Linhas de uma especificação (e requisito), na ordem do snapshot."""
    return [
        r
        for r in snapshot.requirements
        if r.requirement.specification_index == spec
        and (requirement is None or r.requirement.index == requirement)
    ]


def states(
    snapshot: DiagnosticSnapshot, spec: int = 0
) -> list[tuple[int, int | None, str, str | None]]:
    """(requisito, express ID ou None, estado, motivo) de cada linha da especificação."""
    return [
        (
            r.requirement.index,
            None if r.element is None else r.element.express_id,
            r.state,
            r.reason,
        )
        for r in rows(snapshot, spec)
    ]
