"""Projetos, modelos, revisões de fonte e pares IFC–IDS com CAS, replay e limites."""

import threading
import uuid
from pathlib import Path

import pytest

from src.artifacts.contracts import RetainedSourceObject
from src.domain_catalog.draft_store import StoreUnavailableError
from src.operations.contracts import OperationalCommand, OperationalError, SourceArtifactRef
from src.operations.project_models import ModelPairBinding, PairRef
from src.operations.project_service import ProjectService, commands
from src.operations.repositories import EventRepository
from tests.operations.e3_env import RealEnv, make_real_env

IFC_A = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n/* A */\nENDSEC;\nEND-ISO-10303-21;\n"
IFC_B = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n/* B */\nENDSEC;\nEND-ISO-10303-21;\n"
IDS_A = b'<ids xmlns="http://standards.buildingsmart.org/IDS"/>\n'


def _retain(env: RealEnv, name: str, data: bytes, role: str) -> RetainedSourceObject:
    path = env.base / "in" / uuid.uuid4().hex[:8] / name
    path.parent.mkdir(parents=True)
    path.write_bytes(data)
    return env.artifacts.retain_source(path, role)  # type: ignore[arg-type]


class Flow:
    """Atalhos de comandos com chaves novas; ator humano sintético declarado."""

    def __init__(self, env: RealEnv) -> None:
        self.env = env
        self.service = ProjectService(env.store, env.artifacts)
        self.human = uuid.UUID(env.curator)

    def project(self) -> uuid.UUID:
        receipt = self.service.create_project(
            command=commands.create_project(uuid.uuid4(), self.human, name="Obra sintética"),
            name="Obra sintética",
        )
        return receipt.resulting_refs[0].ref_id

    def model(self, project: uuid.UUID, discipline: str = "arquitetura") -> uuid.UUID:
        receipt = self.service.create_model(
            command=commands.create_model(uuid.uuid4(), self.human, project, discipline),
            project_id=project,
            discipline=discipline,
        )
        return receipt.resulting_refs[0].ref_id

    def source(
        self,
        project: uuid.UUID,
        model: uuid.UUID,
        retained: RetainedSourceObject,
        source_id: uuid.UUID | None = None,
        expected: int = 0,
        command_id: uuid.UUID | None = None,
    ) -> SourceArtifactRef:
        command = commands.register_source_revision(
            command_id or uuid.uuid4(),
            self.human,
            project,
            model,
            retained.role,
            retained,
            source_id,
            expected,
        )
        receipt = self.service.register_source_revision(
            command=command,
            project_id=project,
            model_id=model,
            role=retained.role,
            retained=retained,
            source_id=source_id,
            expected_source_revision=expected,
        )
        ref = receipt.resulting_refs[0]
        assert ref.revision is not None
        return self.service.load_source(ref.ref_id, ref.revision)

    def pair(
        self,
        project: uuid.UUID,
        expected_set: int,
        ifc: SourceArtifactRef,
        ids: SourceArtifactRef,
        actor: uuid.UUID | None = None,
    ) -> uuid.UUID:
        actor = actor or self.human
        receipt = self.service.register_pair(
            command=commands.register_pair(
                uuid.uuid4(), actor, project, expected_set, ifc, ids, "arquitetura"
            ),
            project_id=project,
            expected_pair_set_revision=expected_set,
            ifc=ifc,
            ids=ids,
            discipline="arquitetura",
        )
        return receipt.resulting_refs[0].ref_id


@pytest.fixture
def flow(tmp_path: Path) -> Flow:
    return Flow(make_real_env(tmp_path))


def _sources(
    flow: Flow, project: uuid.UUID, model: uuid.UUID
) -> tuple[SourceArtifactRef, SourceArtifactRef]:
    ifc = flow.source(project, model, _retain(flow.env, "modelo.ifc", IFC_A, "ifc"))
    ids = flow.source(project, model, _retain(flow.env, "requisitos.ids", IDS_A, "ids"))
    return ifc, ids


def test_project_state_reopens_with_models_sources_and_pair(flow: Flow, tmp_path: Path) -> None:
    project = flow.project()
    model = flow.model(project)
    ifc, ids = _sources(flow, project, model)
    pair = flow.pair(project, 0, ifc, ids)

    state = ProjectService(make_real_env(tmp_path).store, flow.env.artifacts).load_project_state(
        project
    )

    assert state.project.pair_set_revision == 1
    assert [p.pair_id for p in state.project.active_pair_refs] == [pair]
    (binding,) = state.pairs
    assert isinstance(binding, ModelPairBinding)
    assert PairRef is ModelPairBinding
    assert (binding.ifc, binding.ids, binding.active, binding.pair_revision) == (ifc, ids, True, 1)
    assert binding.confirmed_by_actor_context_id == flow.human
    assert state.pin is None
    assert state.pin_revision == 0
    assert {m.model_id for m in state.models} == {model}


def test_replay_returns_original_receipt_and_any_difference_conflicts(flow: Flow) -> None:
    project = flow.project()
    key = uuid.uuid4()
    first = flow.service.create_model(
        command=commands.create_model(key, flow.human, project, "estrutura"),
        project_id=project,
        discipline="estrutura",
    )
    flow.model(project, "arquitetura")
    replay = flow.service.create_model(
        command=commands.create_model(key, flow.human, project, "estrutura"),
        project_id=project,
        discipline="estrutura",
    )
    assert replay == first
    with pytest.raises(OperationalError) as conflict:
        flow.service.create_model(
            command=commands.create_model(key, flow.human, project, "hidráulica"),
            project_id=project,
            discipline="hidráulica",
        )
    assert conflict.value.reason == "idempotency_conflict"


def test_envelope_must_represent_the_arguments(flow: Flow) -> None:
    project = flow.project()
    signed = commands.create_model(uuid.uuid4(), flow.human, project, "estrutura")
    with pytest.raises(OperationalError) as forged:
        flow.service.create_model(command=signed, project_id=project, discipline="arquitetura")
    assert forged.value.reason == "invalid_command"
    wrong_operation = OperationalCommand.build(
        command_id=uuid.uuid4(),
        actor_context_id=flow.human,
        operation="create_project",
        project_id=project,
        arguments={"project_id": str(project), "discipline": "estrutura"},
    )
    with pytest.raises(OperationalError) as mismatch:
        flow.service.create_model(
            command=wrong_operation, project_id=project, discipline="estrutura"
        )
    assert mismatch.value.reason == "invalid_command"


def test_e2_command_key_cannot_be_reused_by_operations(flow: Flow) -> None:
    from tests.domain_catalog import factories as f
    from tests.operations.e3_env import meta

    e2 = meta(flow.env.importer)
    flow.env.curation.import_draft(
        e2,
        title="Sintético",
        catalog=f.catalog_identity(),
        content=f.minimal_content("draft"),
        source_label="fixture sintética",
        reason="teste",
    )
    with pytest.raises(OperationalError) as conflict:
        flow.service.create_project(
            command=commands.create_project(uuid.UUID(e2.command_id), flow.human, name="Obra"),
            name="Obra",
        )
    assert conflict.value.reason == "idempotency_conflict"


def test_assistant_cannot_confirm_pair_and_unknown_actor_is_refused(flow: Flow) -> None:
    project = flow.project()
    model = flow.model(project)
    ifc, ids = _sources(flow, project, model)
    with pytest.raises(OperationalError) as assistant:
        flow.pair(project, 0, ifc, ids, actor=uuid.UUID(flow.env.assistant))
    assert assistant.value.reason == "human_actor_required"
    with pytest.raises(OperationalError) as unknown:
        flow.pair(project, 0, ifc, ids, actor=uuid.uuid4())
    assert unknown.value.reason == "invalid_actor"


def test_source_revision_cas_new_bytes_and_replay_after_later_revision(flow: Flow) -> None:
    project = flow.project()
    model = flow.model(project)
    retained_a = _retain(flow.env, "modelo.ifc", IFC_A, "ifc")
    key = uuid.uuid4()
    first = flow.source(project, model, retained_a, command_id=key)
    second = flow.source(project, model, retained_a, first.source_id, expected=1)
    third = flow.source(
        project, model, _retain(flow.env, "modelo.ifc", IFC_B, "ifc"), first.source_id, expected=2
    )

    assert (first.revision, second.revision, third.revision) == (1, 2, 3)
    assert second.sha256 == first.sha256
    assert second != first
    assert flow.source(project, model, retained_a, command_id=key) == first
    with pytest.raises(OperationalError) as stale:
        flow.source(project, model, retained_a, first.source_id, expected=1)
    assert stale.value.reason == "stale_source"


def test_concurrent_source_revisions_with_same_token_only_one_wins(flow: Flow) -> None:
    project = flow.project()
    model = flow.model(project)
    retained = _retain(flow.env, "modelo.ifc", IFC_A, "ifc")
    base = flow.source(project, model, retained)
    barrier = threading.Barrier(2)
    outcomes: list[object] = []

    def attempt() -> None:
        barrier.wait()
        try:
            outcomes.append(flow.source(project, model, retained, base.source_id, expected=1))
        except OperationalError as exc:
            outcomes.append(exc.reason)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(type(o).__name__ for o in outcomes) == ["SourceArtifactRef", "str"]
    assert "stale_source" in outcomes


def test_sources_cannot_cross_models_projects_or_roles(flow: Flow) -> None:
    project, other_project = flow.project(), flow.project()
    model, other_model = flow.model(project), flow.model(project, "estrutura")
    foreign_model = flow.model(other_project)
    retained = _retain(flow.env, "modelo.ifc", IFC_A, "ifc")
    ref = flow.source(project, model, retained)
    with pytest.raises(OperationalError) as transplant:
        flow.source(project, other_model, retained, ref.source_id, expected=1)
    assert transplant.value.reason == "foreign_reference"
    with pytest.raises(OperationalError) as cross_project:
        flow.source(project, foreign_model, retained)
    assert cross_project.value.reason == "foreign_reference"
    ids_bytes = _retain(flow.env, "requisitos.ids", IDS_A, "ids")
    with pytest.raises(OperationalError) as role:
        flow.service.register_source_revision(
            command=commands.register_source_revision(
                uuid.uuid4(), flow.human, project, model, "ifc", ids_bytes, None, 0
            ),
            project_id=project,
            model_id=model,
            role="ifc",
            retained=ids_bytes,
            source_id=None,
            expected_source_revision=0,
        )
    assert role.value.reason == "role_mismatch"


def test_pair_requires_registered_exact_refs_of_same_model(flow: Flow) -> None:
    project = flow.project()
    model, other = flow.model(project), flow.model(project, "estrutura")
    ifc, ids = _sources(flow, project, model)
    _, other_ids = _sources(flow, project, other)
    forged = ifc.model_copy(update={"size_bytes": ifc.size_bytes + 1})
    for bad_ifc, bad_ids, reason in (
        (forged, ids, "foreign_reference"),
        (ifc, other_ids, "foreign_reference"),
        (ids, ifc, "role_mismatch"),
    ):
        with pytest.raises(OperationalError) as refused:
            flow.pair(project, 0, bad_ifc, bad_ids)
        assert refused.value.reason == reason
    with pytest.raises(OperationalError) as stale:
        flow.pair(project, 3, ifc, ids)
    assert stale.value.reason == "stale_pair_set"
    assert flow.service.load_project_state(project).project.pair_set_revision == 0


def test_third_active_pair_is_refused_without_truncation(flow: Flow) -> None:
    project = flow.project()
    models = [flow.model(project, name) for name in ("arquitetura", "estrutura", "hidráulica")]
    pairs = [_sources(flow, project, model) for model in models]
    first = flow.pair(project, 0, *pairs[0])
    flow.pair(project, 1, *pairs[1])
    with pytest.raises(OperationalError) as limit:
        flow.pair(project, 2, *pairs[2])
    assert limit.value.reason == "pair_limit_exceeded"
    state = flow.service.load_project_state(project)
    assert (state.project.pair_set_revision, len(state.project.active_pair_refs)) == (2, 2)

    ifc, ids = pairs[0]
    flow.service.revise_pair(
        command=commands.revise_pair(
            uuid.uuid4(), flow.human, project, first, 1, 2, ifc, ids, False
        ),
        pair_id=first,
        expected_pair_revision=1,
        expected_pair_set_revision=2,
        ifc=ifc,
        ids=ids,
        active=False,
    )
    third = flow.pair(project, 3, *pairs[2])
    state = flow.service.load_project_state(project)
    assert third in {p.pair_id for p in state.project.active_pair_refs}
    assert flow.service.load_pair(first, 1).active is True
    assert flow.service.load_pair(first, 2).active is False


def test_revising_pair_keeps_previous_revision_and_checks_tokens(flow: Flow) -> None:
    project = flow.project()
    model = flow.model(project)
    ifc, ids = _sources(flow, project, model)
    pair = flow.pair(project, 0, ifc, ids)
    new_ifc = flow.source(
        project, model, _retain(flow.env, "modelo.ifc", IFC_B, "ifc"), ifc.source_id, 1
    )
    assert flow.service.load_project_state(project).pairs[0].ifc == ifc

    def revise(expected_pair: int, expected_set: int) -> None:
        flow.service.revise_pair(
            command=commands.revise_pair(
                uuid.uuid4(),
                flow.human,
                project,
                pair,
                expected_pair,
                expected_set,
                new_ifc,
                ids,
                True,
            ),
            pair_id=pair,
            expected_pair_revision=expected_pair,
            expected_pair_set_revision=expected_set,
            ifc=new_ifc,
            ids=ids,
            active=True,
        )

    with pytest.raises(OperationalError) as stale_pair:
        revise(2, 1)
    assert stale_pair.value.reason == "stale_pair"
    with pytest.raises(OperationalError) as stale_set:
        revise(1, 0)
    assert stale_set.value.reason == "stale_pair_set"
    revise(1, 1)
    state = flow.service.load_project_state(project)
    assert (state.pairs[0].pair_revision, state.pairs[0].ifc) == (2, new_ifc)
    assert state.project.pair_set_revision == 2
    assert flow.service.load_pair(pair, 1).ifc == ifc


def test_promoted_file_without_commit_is_only_an_orphan(
    flow: Flow, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = flow.project()
    model = flow.model(project)
    retained = _retain(flow.env, "modelo.ifc", IFC_A, "ifc")

    def broken(self: EventRepository, namespace: str, document: dict[str, object]) -> int:
        raise StoreUnavailableError("falha simulada ao gravar evento")

    monkeypatch.setattr(EventRepository, "append", broken)
    with pytest.raises(StoreUnavailableError):
        flow.source(project, model, retained)
    monkeypatch.undo()

    state = flow.service.load_project_state(project)
    assert state.sources == ()
    assert flow.service.inspect_orphans().sources == (retained.storage_key,)
    assert flow.env.artifacts.source_path(retained.storage_key).exists()


def test_unknown_project_is_typed_not_found(flow: Flow) -> None:
    with pytest.raises(OperationalError) as missing:
        flow.service.load_project_state(uuid.uuid4())
    assert missing.value.reason == "not_found"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("active", "false"),
        ("active", 0),
        ("active", 1),
        ("schema_version", True),
        ("schema_version", 1.0),
    ],
)
def test_pair_dto_refuses_coerced_bool_and_schema_version(
    flow: Flow, field: str, value: object
) -> None:
    """E3-16: tipos errados são recusados, nunca normalizados."""
    from pydantic import ValidationError

    project = flow.project()
    model = flow.model(project)
    ifc, ids = _sources(flow, project, model)
    pair = flow.pair(project, 0, ifc, ids)
    document = flow.service.load_pair(pair, 1).model_dump(mode="json")
    assert ModelPairBinding.model_validate(document).active is True
    with pytest.raises(ValidationError):
        ModelPairBinding.model_validate({**document, field: value})


@pytest.mark.parametrize("value", ["false", 0, 1])
def test_revise_pair_refuses_non_bool_active_before_any_decision(flow: Flow, value: object) -> None:
    """E3-16: argumento público não booleano é recusado antes de no-op/limites/hash."""
    project = flow.project()
    model = flow.model(project)
    ifc, ids = _sources(flow, project, model)
    pair = flow.pair(project, 0, ifc, ids)
    with pytest.raises(OperationalError) as refused:
        flow.service.revise_pair(
            command=commands.revise_pair(
                uuid.uuid4(),
                flow.human,
                project,
                pair,
                1,
                1,
                ifc,
                ids,
                value,  # type: ignore[arg-type]
            ),
            pair_id=pair,
            expected_pair_revision=1,
            expected_pair_set_revision=1,
            ifc=ifc,
            ids=ids,
            active=value,  # type: ignore[arg-type]
        )
    assert refused.value.reason == "invalid_command"
    assert flow.service.load_project_state(project).pairs[0].pair_revision == 1


@pytest.mark.parametrize("token", [False, 0.0])
def test_register_pair_refuses_non_int_expected_token(flow: Flow, token: object) -> None:
    """M-04: token público bool/float é recusado antes do hash e de qualquer CAS."""
    project = flow.project()
    model = flow.model(project)
    ifc, ids = _sources(flow, project, model)
    with pytest.raises(OperationalError) as refused:
        flow.pair(project, token, ifc, ids)  # type: ignore[arg-type]
    assert refused.value.reason == "invalid_command"
    assert flow.service.load_project_state(project).pairs == ()


@pytest.mark.parametrize("token", [True, 1.0])
def test_register_source_revision_refuses_non_int_expected_token(flow: Flow, token: object) -> None:
    """M-04: ``expected_source_revision=True`` não vira revisão 2."""
    project = flow.project()
    model = flow.model(project)
    ifc, _ = _sources(flow, project, model)
    retained = _retain(flow.env, "modelo.ifc", IFC_B, "ifc")
    with pytest.raises(OperationalError) as refused:
        flow.source(project, model, retained, ifc.source_id, token)  # type: ignore[arg-type]
    assert refused.value.reason == "invalid_command"
    assert flow.service.load_source(ifc.source_id, 1) == ifc
