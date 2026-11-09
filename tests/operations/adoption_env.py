"""Ambiente de adoção de catálogo com componentes REAIS e dados SINTÉTICOS declarados.

Projeto com 1 ou 2 pares IFC–IDS mínimos, releases publicados pelo serviço E2
existente sobre os adaptadores reais e serviço de adoção. Atores sintéticos.
"""

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from src.artifacts.contracts import RetainedSourceObject
from src.domain_catalog.contracts import CatalogReleaseRef
from src.domain_catalog.migration import (
    CatalogAdoptionService,
    adoption_command,
    reanalysis_command,
)
from src.domain_catalog.migration_contracts import AdoptionReceipt, CatalogAdoptionPlan
from src.operations.analysis_queue import AnalysisQueueReceipt
from src.operations.contracts import SourceRole
from src.operations.database import StorePurpose
from src.operations.project_service import ProjectService, commands
from src.validation.analysis_identity import current_execution_profile
from tests.operations.e3_env import RealEnv, make_real_env

IFC_MIN = (
    b"ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION((''),'2;1');\nFILE_NAME('','',(''),(''),'','','');\n"
    b"FILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"
)
IDS_MIN = b'<ids xmlns="http://standards.buildingsmart.org/IDS"/>\n'


@dataclass
class AdoptionEnv:
    """Serviços reais e o projeto sintético preparado."""

    env: RealEnv
    projects: ProjectService
    adoption: CatalogAdoptionService
    project_id: uuid.UUID
    human: uuid.UUID
    assistant: uuid.UUID
    pairs: list[uuid.UUID] = field(default_factory=list)


def _retain(env: RealEnv, name: str, data: bytes, role: SourceRole) -> RetainedSourceObject:
    folder = env.base / "in" / uuid.uuid4().hex[:8]
    folder.mkdir(parents=True)
    (folder / name).write_bytes(data)
    return env.artifacts.retain_source(folder / name, role)


def add_pair(
    aenv: AdoptionEnv,
    discipline: str,
    variant: bytes = b"",
    *,
    ifc: bytes | None = None,
    ids: bytes | None = None,
) -> uuid.UUID:
    """Modelo novo com fontes (mínimas, salvo se dadas) e par ativo, por comandos reais."""
    service, human, project = aenv.projects, aenv.human, aenv.project_id
    model = (
        service.create_model(
            command=commands.create_model(uuid.uuid4(), human, project, discipline),
            project_id=project,
            discipline=discipline,
        )
        .resulting_refs[0]
        .ref_id
    )
    refs = []
    sources: tuple[tuple[str, bytes, SourceRole], ...] = (
        ("m.ifc", IFC_MIN + variant if ifc is None else ifc, "ifc"),
        ("r.ids", IDS_MIN if ids is None else ids, "ids"),
    )
    for name, data, role in sources:
        retained = _retain(aenv.env, name, data, role)
        receipt = service.register_source_revision(
            command=commands.register_source_revision(
                uuid.uuid4(),
                human,
                project,
                model,
                role,
                retained,
                None,
                0,
            ),
            project_id=project,
            model_id=model,
            role=role,
            retained=retained,
            source_id=None,
            expected_source_revision=0,
        )
        ref = receipt.resulting_refs[0]
        assert ref.revision is not None
        refs.append(service.load_source(ref.ref_id, ref.revision))
    expected = service.load_project_state(project).pair_set_revision
    pair = (
        service.register_pair(
            command=commands.register_pair(
                uuid.uuid4(), human, project, expected, refs[0], refs[1], discipline
            ),
            project_id=project,
            expected_pair_set_revision=expected,
            ifc=refs[0],
            ids=refs[1],
            discipline=discipline,
        )
        .resulting_refs[0]
        .ref_id
    )
    aenv.pairs.append(pair)
    return pair


def make_adoption_env(
    base: Path, *, pairs: int = 1, purpose: StorePurpose = "synthetic_test"
) -> AdoptionEnv:
    """Projeto sintético com ``pairs`` pares ativos."""
    env = make_real_env(base, purpose)
    projects = ProjectService(env.store, env.artifacts)
    human = uuid.UUID(env.curator)
    project = (
        projects.create_project(
            command=commands.create_project(uuid.uuid4(), human, name="Obra sintética"),
            name="Obra sintética",
        )
        .resulting_refs[0]
        .ref_id
    )
    aenv = AdoptionEnv(
        env=env,
        projects=projects,
        adoption=CatalogAdoptionService(env.store, env.artifacts),
        project_id=project,
        human=human,
        assistant=uuid.UUID(env.assistant),
    )
    for index in range(pairs):
        add_pair(aenv, ("arquitetura", "estrutura")[index % 2], variant=f"/*{index}*/".encode())
    return aenv


def release_dir(aenv: AdoptionEnv, ref: CatalogReleaseRef) -> Path:
    """Pasta do release publicado pela porta E2 real."""
    return aenv.env.releases.release_path(ref)


def prepare(
    aenv: AdoptionEnv,
    ref: CatalogReleaseRef,
    intent: str,
    *,
    folder: Path | None = None,
    actor: uuid.UUID | None = None,
) -> CatalogAdoptionPlan:
    """Prepara plano com os tokens correntes do projeto."""
    state = aenv.projects.load_project_state(aenv.project_id)
    return aenv.adoption.prepare_catalog_adoption(
        project_id=aenv.project_id,
        expected_pin_revision=state.pin_revision,
        expected_pair_set_revision=state.pair_set_revision,
        target_ref=ref,
        target_dir=folder or release_dir(aenv, ref),
        intent=intent,  # type: ignore[arg-type]
        reason="adoção sintética de teste",
        execution_profile=current_execution_profile(),
        prepared_by_actor_context_id=actor or aenv.human,
    )


def apply(
    aenv: AdoptionEnv,
    plan: CatalogAdoptionPlan,
    *,
    actor: uuid.UUID | None = None,
    command_id: uuid.UUID | None = None,
    plan_sha256: str | None = None,
) -> AdoptionReceipt:
    """Confirma explicitamente o plano exato (ID e hash)."""
    digest = plan_sha256 or aenv.adoption.plan_sha256(plan)
    return aenv.adoption.apply_catalog_adoption(
        command=adoption_command(
            command_id or uuid.uuid4(), actor or aenv.human, plan.project_id, plan.plan_id, digest
        ),
        plan_id=plan.plan_id,
        confirmed_plan_sha256=digest,
    )


def reanalyze(aenv: AdoptionEnv, *, actor: uuid.UUID | None = None) -> AnalysisQueueReceipt:
    """Enfileira nova análise de todos os pares ativos, sem trocar o pin."""
    state = aenv.projects.load_project_state(aenv.project_id)
    profile = current_execution_profile()
    return aenv.adoption.queue_reanalysis(
        command=reanalysis_command(
            uuid.uuid4(),
            actor or aenv.human,
            aenv.project_id,
            state.pin_revision,
            state.pair_set_revision,
            profile,
            "reanálise sintética",
        ),
        project_id=aenv.project_id,
        expected_pin_revision=state.pin_revision,
        expected_pair_set_revision=state.pair_set_revision,
        execution_profile=profile,
        reason="reanálise sintética",
    )
