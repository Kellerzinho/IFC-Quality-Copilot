"""Projetos, modelos, revisões de fonte e pares IFC–IDS (autoridade operacional comum).

``register_source_revision`` é a única alocação de identidade/revisão de fonte; nada é
inferido por nome, GUID ou hash. Registrar ou revisar par é ato explícito de contexto
humano declarado, só com referências registradas do mesmo projeto e modelo; nova
fonte não muda par automaticamente. O conjunto de pares avança ``pair_set_revision``
sob CAS e aceita no máximo dois pares ativos (o terceiro é ``pair_limit_exceeded``,
sem truncar). Objetos retidos são verificados no disco antes da transação que os
referencia; falha posterior deixa só objeto órfão (``inspect_orphans``).
"""

import uuid
from collections.abc import Callable

from pydantic import ValidationError

from src.artifacts.contracts import ArtifactError, OrphanReport, RetainedSourceObject
from src.artifacts.storage import LocalArtifactStore
from src.domain_catalog.actor import ActorSnapshot
from src.domain_catalog.curation import utc_now
from src.operations import commands
from src.operations.command_runner import Effect, OperationalRunner
from src.operations.contracts import (
    OperationalCommand,
    OperationalError,
    OperationalErrorReason,
    OperationalReceipt,
    ResultingRef,
    SourceArtifactRef,
    SourceRole,
    new_uuid,
    require_tokens,
)
from src.operations.database import OperationalStore, OperationalUnitOfWork
from src.operations.project_models import (
    MAX_ACTIVE_PAIRS,
    ModelPairBinding,
    ModelRecord,
    ProjectCatalogPin,
    ProjectRecord,
    ProjectState,
)
from src.operations.repositories import StoredRow

__all__ = ["ProjectService", "commands"]


def _project(uow: OperationalUnitOfWork, project_id: uuid.UUID) -> tuple[ProjectRecord, int]:
    row = uow.projects.get(str(project_id))
    if row is None:
        raise OperationalError("not_found", f"projeto {project_id} não existe")
    return ProjectRecord.model_validate(row.document), row.row_version


def _model(uow: OperationalUnitOfWork, model_id: uuid.UUID) -> ModelRecord:
    row = uow.models.get(str(model_id))
    if row is None:
        raise OperationalError("not_found", f"modelo {model_id} não existe")
    return ModelRecord.model_validate(row.document)


def registered_source(uow: OperationalUnitOfWork, ref: SourceArtifactRef) -> SourceArtifactRef:
    """A referência precisa ser exatamente uma revisão registrada (todos os campos)."""
    row = uow.sources.get_revision(str(ref.source_id), ref.revision)
    if row is None or SourceArtifactRef.model_validate(row.document) != ref:
        raise OperationalError(
            "foreign_reference",
            f"fonte {ref.source_id} r{ref.revision} não é uma revisão registrada idêntica",
        )
    return ref


def _pair_refs(
    uow: OperationalUnitOfWork,
    project: ProjectRecord,
    model_id: uuid.UUID,
    ifc: SourceArtifactRef,
    ids: SourceArtifactRef,
) -> None:
    if (ifc.role, ids.role) != ("ifc", "ids"):
        raise OperationalError("role_mismatch", "par exige fonte ifc e fonte ids, nessa ordem")
    for ref in (ifc, ids):
        if (ref.project_id, ref.model_id) != (project.project_id, model_id):
            raise OperationalError(
                "foreign_reference", "as duas fontes do par precisam ser do mesmo projeto e modelo"
            )
        registered_source(uow, ref)


def _with_pairs(
    project: ProjectRecord, replaced: ModelPairBinding | None, removed: uuid.UUID | None
) -> tuple[ModelPairBinding, ...]:
    pairs = {p.pair_id: p for p in project.active_pair_refs if p.pair_id != removed}
    if replaced is not None and replaced.active:
        pairs[replaced.pair_id] = replaced
    return tuple(pairs[key] for key in sorted(pairs, key=str))


class ProjectService:
    """Comandos e consultas de projeto sobre a autoridade operacional e os artefatos."""

    def __init__(
        self,
        store: OperationalStore,
        artifacts: LocalArtifactStore,
        *,
        clock: Callable[[], str] = utc_now,
        new_id: Callable[[], uuid.UUID] = new_uuid,
    ) -> None:
        """Banco operacional e armazenamento de artefatos da mesma instalação."""
        self._store = store
        self._artifacts = artifacts
        self._runner = OperationalRunner(store, clock=clock, new_id=new_id)
        self._new_id = new_id

    # --- comandos ---------------------------------------------------------------------------

    def create_project(self, *, command: OperationalCommand, name: str) -> OperationalReceipt:
        """Cria projeto com conjunto de pares vazio (revisão 0) e sem pin."""
        arguments = commands.create_project_arguments(name=name)

        def body(uow: OperationalUnitOfWork, actor: ActorSnapshot, now: str) -> Effect:
            project = ProjectRecord(
                project_id=self._new_id(),
                name=name,
                pair_set_revision=0,
                created_by_actor_context_id=actor.actor_context_id,  # type: ignore[arg-type]
                created_at_utc=now,
            )
            uow.projects.insert(project.model_dump(mode="json"))
            return Effect(
                "applied",
                (ResultingRef(kind="project", ref_id=project.project_id),),
                ({"event": "project_created", "created_project_id": str(project.project_id)},),
            )

        return self._runner.run(
            command,
            operation="create_project",
            project_id=None,
            arguments=arguments,
            requirement="human_or_service",
            body=body,
        ).receipt

    def create_model(
        self, *, command: OperationalCommand, project_id: uuid.UUID, discipline: str
    ) -> OperationalReceipt:
        """Aloca identidade lógica de modelo pertencente ao projeto."""
        arguments = commands.create_model_arguments(project_id=project_id, discipline=discipline)

        def body(uow: OperationalUnitOfWork, actor: ActorSnapshot, now: str) -> Effect:
            _project(uow, project_id)
            model = ModelRecord(
                project_id=project_id,
                model_id=self._new_id(),
                discipline=discipline,
                created_by_actor_context_id=actor.actor_context_id,  # type: ignore[arg-type]
                created_at_utc=now,
            )
            uow.models.insert(model.model_dump(mode="json"))
            return Effect(
                "applied",
                (ResultingRef(kind="model", ref_id=model.model_id),),
                ({"event": "model_created", "model_id": str(model.model_id)},),
            )

        return self._runner.run(
            command,
            operation="create_model",
            project_id=project_id,
            arguments=arguments,
            requirement="human_or_service",
            body=body,
        ).receipt

    def register_source_revision(
        self,
        *,
        command: OperationalCommand,
        project_id: uuid.UUID,
        model_id: uuid.UUID,
        role: SourceRole,
        retained: RetainedSourceObject,
        source_id: uuid.UUID | None,
        expected_source_revision: int,
    ) -> OperationalReceipt:
        """Registra revisão nova de fonte (ID novo com token 0, ou revisão+1 por CAS)."""
        require_tokens(expected_source_revision=expected_source_revision)
        arguments = commands.register_source_revision_arguments(
            project_id=project_id,
            model_id=model_id,
            role=role,
            retained=retained,
            source_id=source_id,
            expected_source_revision=expected_source_revision,
        )
        self._runner.verify_envelope(
            command,
            operation="register_source_revision",
            project_id=project_id,
            arguments=arguments,
        )
        if self._runner.lookup(command) is None:
            if retained.role != role:
                raise OperationalError(
                    "role_mismatch", f"objeto retido é {retained.role}, não {role}"
                )
            self._verify_retained(retained)

        def body(uow: OperationalUnitOfWork, actor: ActorSnapshot, now: str) -> Effect:
            _project(uow, project_id)
            model = _model(uow, model_id)
            if model.project_id != project_id:
                raise OperationalError("foreign_reference", "modelo pertence a outro projeto")
            if source_id is None:
                if expected_source_revision != 0:
                    raise OperationalError(
                        "stale_source",
                        "fonte nova exige token 0",
                        expected=expected_source_revision,
                        actual=0,
                    )
                new_source, revision, head = self._new_id(), 1, None
            else:
                head = uow.sources.get_head(str(source_id))
                if head is None:
                    raise OperationalError("not_found", f"fonte {source_id} não existe")
                current = head.document
                if (current["project_id"], current["model_id"]) != (str(project_id), str(model_id)):
                    raise OperationalError(
                        "foreign_reference", "fonte pertence a outro projeto ou modelo"
                    )
                if current["role"] != role:
                    raise OperationalError("role_mismatch", "fonte registrada com outro papel")
                if current["revision"] != expected_source_revision:
                    raise OperationalError(
                        "stale_source",
                        f"fonte {source_id} mudou",
                        expected=expected_source_revision,
                        actual=current["revision"],
                    )
                new_source, revision = source_id, expected_source_revision + 1
            ref = SourceArtifactRef(
                project_id=project_id,
                model_id=model_id,
                source_id=new_source,
                revision=revision,
                role=role,
                sha256=retained.sha256,
                size_bytes=retained.size_bytes,
                display_name=retained.display_name,
                storage_key=retained.storage_key,
            )
            uow.sources.insert_revision(ref.model_dump(mode="json"))
            head_doc = {
                "source_id": str(new_source),
                "revision": revision,
                "project_id": str(project_id),
                "model_id": str(model_id),
                "role": role,
            }
            if head is None:
                uow.sources.insert_head(head_doc)
            else:
                uow.sources.replace_head(str(new_source), head.row_version, head_doc)
            return Effect(
                "applied",
                (ResultingRef(kind="source", ref_id=new_source, revision=revision),),
                (
                    {
                        "event": "source_revision_registered",
                        "source_id": str(new_source),
                        "revision": revision,
                        "sha256": retained.sha256,
                    },
                ),
            )

        return self._runner.run(
            command,
            operation="register_source_revision",
            project_id=project_id,
            arguments=arguments,
            requirement="human_or_service",
            body=body,
        ).receipt

    def register_pair(
        self,
        *,
        command: OperationalCommand,
        project_id: uuid.UUID,
        expected_pair_set_revision: int,
        ifc: SourceArtifactRef,
        ids: SourceArtifactRef,
        discipline: str,
    ) -> OperationalReceipt:
        """Registra par novo (revisão 1, ativo) por decisão humana explícita."""
        require_tokens(expected_pair_set_revision=expected_pair_set_revision)
        arguments = commands.register_pair_arguments(
            project_id=project_id,
            expected_pair_set_revision=expected_pair_set_revision,
            ifc=ifc,
            ids=ids,
            discipline=discipline,
        )

        def body(uow: OperationalUnitOfWork, actor: ActorSnapshot, now: str) -> Effect:
            project, version = _project(uow, project_id)
            if project.pair_set_revision != expected_pair_set_revision:
                raise OperationalError(
                    "stale_pair_set",
                    "conjunto de pares mudou",
                    expected=expected_pair_set_revision,
                    actual=project.pair_set_revision,
                )
            _pair_refs(uow, project, ifc.model_id, ifc, ids)
            if len(project.active_pair_refs) >= MAX_ACTIVE_PAIRS:
                raise OperationalError(
                    "pair_limit_exceeded", f"projeto já tem {MAX_ACTIVE_PAIRS} pares ativos"
                )
            pair = ModelPairBinding(
                project_id=project_id,
                model_id=ifc.model_id,
                pair_id=self._new_id(),
                pair_revision=1,
                discipline=discipline,
                ifc=ifc,
                ids=ids,
                active=True,
                confirmed_by_actor_context_id=actor.actor_context_id,  # type: ignore[arg-type]
            )
            self._write_pair(uow, pair, head=None)
            self._bump_project(uow, project, version, _with_pairs(project, pair, None))
            return Effect(
                "applied",
                (ResultingRef(kind="pair", ref_id=pair.pair_id, revision=1),),
                (
                    {
                        "event": "pair_registered",
                        "pair_id": str(pair.pair_id),
                        "pair_revision": 1,
                        "pair_set_revision": project.pair_set_revision + 1,
                    },
                ),
            )

        return self._runner.run(
            command,
            operation="register_pair",
            project_id=project_id,
            arguments=arguments,
            requirement="human",
            body=body,
        ).receipt

    def revise_pair(
        self,
        *,
        command: OperationalCommand,
        pair_id: uuid.UUID,
        expected_pair_revision: int,
        expected_pair_set_revision: int,
        ifc: SourceArtifactRef,
        ids: SourceArtifactRef,
        active: bool,
    ) -> OperationalReceipt:
        """Nova revisão do par (fontes e/ou ativação); revisões anteriores ficam imutáveis."""
        # Tipos estritos antes do hash do comando e de qualquer decisão (E3-16).
        if not isinstance(active, bool):
            raise OperationalError("invalid_command", "active exige booleano")
        require_tokens(
            expected_pair_revision=expected_pair_revision,
            expected_pair_set_revision=expected_pair_set_revision,
        )
        arguments = commands.revise_pair_arguments(
            pair_id=pair_id,
            expected_pair_revision=expected_pair_revision,
            expected_pair_set_revision=expected_pair_set_revision,
            ifc=ifc,
            ids=ids,
            active=active,
        )
        project_id = command.project_id
        if project_id is None:
            raise OperationalError("invalid_command", "revise_pair exige projeto no envelope")

        def body(uow: OperationalUnitOfWork, actor: ActorSnapshot, now: str) -> Effect:
            head = uow.pairs.get_head(str(pair_id))
            if head is None:
                raise OperationalError("not_found", f"par {pair_id} não existe")
            if head.document["project_id"] != str(project_id):
                raise OperationalError("foreign_reference", "par pertence a outro projeto")
            project, version = _project(uow, project_id)
            if project.pair_set_revision != expected_pair_set_revision:
                raise OperationalError(
                    "stale_pair_set",
                    "conjunto de pares mudou",
                    expected=expected_pair_set_revision,
                    actual=project.pair_set_revision,
                )
            if head.document["pair_revision"] != expected_pair_revision:
                raise OperationalError(
                    "stale_pair",
                    f"par {pair_id} mudou",
                    expected=expected_pair_revision,
                    actual=head.document["pair_revision"],
                )
            previous = self._pair_revision(uow, pair_id, expected_pair_revision)
            if (previous.ifc, previous.ids, previous.active) == (ifc, ids, active):
                return Effect(
                    "noop",
                    (ResultingRef(kind="pair", ref_id=pair_id, revision=expected_pair_revision),),
                    ({"event": "pair_revision_noop", "pair_id": str(pair_id)},),
                )
            _pair_refs(uow, project, previous.model_id, ifc, ids)
            others = [p for p in project.active_pair_refs if p.pair_id != pair_id]
            if active and len(others) >= MAX_ACTIVE_PAIRS:
                raise OperationalError(
                    "pair_limit_exceeded", f"projeto já tem {MAX_ACTIVE_PAIRS} pares ativos"
                )
            pair = previous.model_copy(
                update={
                    "pair_revision": expected_pair_revision + 1,
                    "ifc": ifc,
                    "ids": ids,
                    "active": active,
                    "confirmed_by_actor_context_id": uuid.UUID(actor.actor_context_id),
                }
            )
            pair = ModelPairBinding.model_validate(pair.model_dump())
            self._write_pair(uow, pair, head=head)
            self._bump_project(uow, project, version, _with_pairs(project, pair, pair_id))
            return Effect(
                "applied",
                (ResultingRef(kind="pair", ref_id=pair_id, revision=pair.pair_revision),),
                (
                    {
                        "event": "pair_revised",
                        "pair_id": str(pair_id),
                        "pair_revision": pair.pair_revision,
                        "active": active,
                        "pair_set_revision": project.pair_set_revision + 1,
                    },
                ),
            )

        return self._runner.run(
            command,
            operation="revise_pair",
            project_id=project_id,
            arguments=arguments,
            requirement="human",
            body=body,
        ).receipt

    # --- apoio ----------------------------------------------------------------------------

    def _verify_retained(self, retained: RetainedSourceObject) -> None:
        path = self._artifacts.source_path(retained.storage_key)
        probe = SourceArtifactRef(
            project_id=uuid.UUID(int=0),
            model_id=uuid.UUID(int=0),
            source_id=uuid.UUID(int=0),
            revision=1,
            role=retained.role,
            sha256=retained.sha256,
            size_bytes=retained.size_bytes,
            display_name=retained.display_name,
            storage_key=retained.storage_key,
        )
        try:
            self._artifacts.read_verified_source(probe)
        except ArtifactError as exc:
            reason: OperationalErrorReason = (
                "artifact_unavailable"
                if exc.reason == "artifact_unavailable"
                else "artifact_integrity_error"
            )
            raise OperationalError(reason, f"objeto retido {path.name}: {exc}") from exc

    @staticmethod
    def _pair_revision(
        uow: OperationalUnitOfWork, pair_id: uuid.UUID, revision: int
    ) -> ModelPairBinding:
        row = uow.pairs.get_revision(str(pair_id), revision)
        if row is None:
            raise OperationalError("not_found", f"par {pair_id} r{revision} não existe")
        return ModelPairBinding.model_validate(row.document)

    @staticmethod
    def _write_pair(
        uow: OperationalUnitOfWork, pair: ModelPairBinding, *, head: StoredRow | None
    ) -> None:
        uow.pairs.insert_revision(pair.model_dump(mode="json"))
        head_doc = {
            "pair_id": str(pair.pair_id),
            "pair_revision": pair.pair_revision,
            "project_id": str(pair.project_id),
            "active": pair.active,
        }
        if head is None:
            uow.pairs.insert_head(head_doc)
        else:
            uow.pairs.replace_head(str(pair.pair_id), head.row_version, head_doc)

    @staticmethod
    def _bump_project(
        uow: OperationalUnitOfWork,
        project: ProjectRecord,
        version: int,
        active: tuple[ModelPairBinding, ...],
    ) -> None:
        updated = project.model_copy(
            update={"pair_set_revision": project.pair_set_revision + 1, "active_pair_refs": active}
        )
        updated = ProjectRecord.model_validate(updated.model_dump())
        uow.projects.replace(str(project.project_id), version, updated.model_dump(mode="json"))

    # --- consultas ------------------------------------------------------------------------

    def load_source(self, source_id: uuid.UUID, revision: int) -> SourceArtifactRef:
        """Revisão exata de fonte registrada; ausência é ``not_found``."""
        with self._store.transaction() as uow:
            row = uow.sources.get_revision(str(source_id), revision)
        if row is None:
            raise OperationalError("not_found", f"fonte {source_id} r{revision} não existe")
        return SourceArtifactRef.model_validate(row.document)

    def load_pair(self, pair_id: uuid.UUID, revision: int) -> ModelPairBinding:
        """Revisão exata de par; ausência é ``not_found``."""
        with self._store.transaction() as uow:
            return self._pair_revision(uow, pair_id, revision)

    def load_project_state(self, project_id: uuid.UUID) -> ProjectState:
        """Heads, revisões correntes, pares (ativos e inativos), pin e tokens."""
        with self._store.transaction() as uow:
            project, _ = _project(uow, project_id)
            models = tuple(
                ModelRecord.model_validate(r.document)
                for r in uow.models.scan(project_id=str(project_id))
            )
            heads = uow.sources.scan_heads(project_id=str(project_id))
            sources = []
            for head in heads:
                row = uow.sources.get_revision(
                    head.document["source_id"], head.document["revision"]
                )
                assert row is not None
                sources.append(SourceArtifactRef.model_validate(row.document))
            pairs = tuple(
                self._pair_revision(
                    uow, uuid.UUID(h.document["pair_id"]), h.document["pair_revision"]
                )
                for h in uow.pairs.scan_heads(project_id=str(project_id))
            )
            pin_head = uow.pins.get_head(str(project_id))
            pin = None
            if pin_head is not None:
                pin_row = uow.pins.get_revision(str(project_id), pin_head.document["pin_revision"])
                assert pin_row is not None
                pin = ProjectCatalogPin.model_validate(pin_row.document)
        try:
            return ProjectState(
                project=project,
                models=models,
                sources=tuple(sources),
                pairs=pairs,
                pin=pin,
                pin_revision=0 if pin is None else pin.pin_revision,
            )
        except ValidationError as exc:
            raise OperationalError("integrity_error", "estado do projeto incoerente") from exc

    def inspect_orphans(self) -> OrphanReport:
        """Objetos retidos sem referência no banco e restos de preparo (somente leitura)."""
        with self._store.transaction() as uow:
            referenced = {row.document["storage_key"] for row in uow.sources.scan_revisions()} | {
                row.document["storage_key"] for row in uow.releases.scan()
            }
        return self._artifacts.inspect_orphans(referenced)
