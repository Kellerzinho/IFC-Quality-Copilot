"""Registro de projetos e armazenamento de fontes por hash — PROVISÓRIO.

Projetos e vínculos ficam em memória e são gravados em SQLite local
(``project_store.py``) a cada alteração, para reabrir depois de reiniciar a API;
sessão, recibos e decisões duráveis continuam sendo M4-12/M6. Os bytes
recebidos ficam em ``<data_root>/blobs/<sha256>.<ifc|ids>``, imutáveis.
Leitura de IFC é síncrona e serializada por um lock; a API a executa em
threadpool. A M6 prevê fila de jobs para esse trabalho.
"""

import hashlib
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path

import ifcopenshell
from loguru import logger

from src.review_api.elements import list_elements
from src.review_api.errors import ApiProblem
from src.review_api.legacy_adapter import compute_gaps
from src.review_api.project_store import ProjectStore, utc_now
from src.review_api.schemas import (
    ArtifactRole,
    ConfirmBindingRequest,
    Discipline,
    ElementRecord,
    Gap,
    ModelPairBinding,
    Project,
    ProjectSummary,
    SourceArtifactRef,
)
from src.translator.ids_parser import parse_ids

MAX_UPLOAD_BYTES = 512 * 1024 * 1024
_DISCIPLINES: tuple[Discipline, ...] = ("architecture", "structure")
_IFC_CACHE_SIZE = 4


class ArtifactStore:
    """Bytes imutáveis endereçados pelo SHA-256 do conteúdo."""

    def __init__(self, root: Path) -> None:
        """Cria (se preciso) o diretório de blobs sob a raiz de dados."""
        self.blobs = root / "blobs"
        self.blobs.mkdir(parents=True, exist_ok=True)

    def path_for(self, role: ArtifactRole, revision_id: str) -> Path:
        """Retorna o caminho interno de uma revisão."""
        return self.blobs / f"{revision_id}.{role}"

    def put(self, role: ArtifactRole, data: bytes) -> tuple[str, Path, bool]:
        """Grava os bytes se ainda não existirem; devolve (sha, caminho, novo?)."""
        revision_id = hashlib.sha256(data).hexdigest()
        target = self.path_for(role, revision_id)
        if target.exists():
            return revision_id, target, False
        tmp = target.with_suffix(f".{uuid.uuid4().hex}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, target)
        return revision_id, target, True


class ProjectRegistry:
    """Projetos em memória com duas linhas (arquitetura e estrutura)."""

    def __init__(self, data_root: Path) -> None:
        """Inicializa armazenamento e caches."""
        self.store = ArtifactStore(data_root)
        self._db = ProjectStore(data_root)
        self._projects: dict[str, Project] = {}
        self._dates: dict[str, tuple[datetime, datetime]] = {}
        for stored in self._db.load_all():
            self._projects[stored.project.project_id] = stored.project
            self._dates[stored.project.project_id] = (stored.created_at, stored.updated_at)
        self._lock = threading.RLock()
        self._ifc_lock = threading.RLock()
        self._ifc_cache: dict[str, ifcopenshell.file] = {}
        self._gap_cache: dict[tuple[str, str, str], list[Gap]] = {}
        self._element_cache: dict[tuple[str, str], list[ElementRecord]] = {}

    # -- projetos ---------------------------------------------------------

    def create_project(self, name: str) -> Project:
        """Cria projeto com as linhas arquitetura e estrutura, sem fontes."""
        project_id = uuid.uuid4().hex
        models = [
            ModelPairBinding(
                project_id=project_id, model_id=uuid.uuid4().hex, discipline=discipline
            )
            for discipline in _DISCIPLINES
        ]
        project = Project(project_id=project_id, name=name, models=models)
        now = utc_now()
        with self._lock:
            self._db.save(project, now, now)
            self._projects[project_id] = project
            self._dates[project_id] = (now, now)
        return project

    def list_projects(self) -> list[ProjectSummary]:
        """Projetos salvos, do alterado mais recentemente ao mais antigo."""
        with self._lock:
            items = [
                ProjectSummary(
                    project_id=p.project_id,
                    name=p.name,
                    created_at=self._dates[p.project_id][0],
                    updated_at=self._dates[p.project_id][1],
                    models=p.models,
                )
                for p in self._projects.values()
            ]
        return sorted(items, key=lambda s: (s.updated_at, s.project_id), reverse=True)

    def get_project(self, project_id: str) -> Project:
        """Retorna o projeto ou 404."""
        with self._lock:
            project = self._projects.get(project_id)
        if project is None:
            raise ApiProblem(404, "projeto_inexistente", "Projeto não encontrado.")
        return project

    def get_binding(self, project_id: str, model_id: str) -> ModelPairBinding:
        """Retorna a linha do projeto ou 404."""
        for binding in self.get_project(project_id).models:
            if binding.model_id == model_id:
                return binding
        raise ApiProblem(404, "modelo_inexistente", "Modelo não encontrado neste projeto.")

    def _replace_binding(self, binding: ModelPairBinding) -> None:
        """Substitui a linha imutável dentro do projeto."""
        with self._lock:
            project = self._projects[binding.project_id]
            models = [binding if m.model_id == binding.model_id else m for m in project.models]
            updated = project.model_copy(update={"models": models})
            created_at = self._dates[binding.project_id][0]
            now = utc_now()
            self._db.save(updated, created_at, now)
            self._projects[binding.project_id] = updated
            self._dates[binding.project_id] = (created_at, now)

    # -- fontes -----------------------------------------------------------

    def register_source(
        self,
        project_id: str,
        model_id: str,
        role: ArtifactRole,
        data: bytes,
        display_name: str,
    ) -> ModelPairBinding:
        """Valida e registra um IFC ou IDS; invalida a confirmação anterior."""
        binding = self.get_binding(project_id, model_id)
        if not data:
            raise ApiProblem(422, "arquivo_vazio", "O arquivo enviado está vazio.")
        if len(data) > MAX_UPLOAD_BYTES:
            raise ApiProblem(413, "arquivo_grande", "Arquivo acima do limite desta fatia.")
        revision_id, path, created = self.store.put(role, data)
        try:
            ifc_schema = self._validate(role, revision_id, path)
        except ApiProblem:
            if created:
                path.unlink(missing_ok=True)
            raise
        ref = SourceArtifactRef(
            role=role,
            revision_id=revision_id,
            size_bytes=len(data),
            display_name=display_name,
            ifc_schema=ifc_schema,
        )
        updated = binding.model_copy(
            update={
                role: ref,
                "confirmed": False,
                "confirmed_ifc_revision_id": None,
                "confirmed_ids_revision_id": None,
            }
        )
        self._replace_binding(ModelPairBinding.model_validate(updated.model_dump()))
        logger.info("Fonte {} registrada: modelo={} rev={}", role, model_id, revision_id[:12])
        return self.get_binding(project_id, model_id)

    def _validate(self, role: ArtifactRole, revision_id: str, path: Path) -> str | None:
        """Abre o IFC ou valida o IDS (XSD + parser legado); devolve schema IFC."""
        if role == "ifc":
            with path.open("rb") as handle:
                head = handle.read(64).lstrip(b"\xef\xbb\xbf \t\r\n")
            if not head.startswith(b"ISO-10303-21;"):
                raise ApiProblem(422, "ifc_invalido", "O arquivo não é um IFC STEP (ISO-10303-21).")
            try:
                return self.open_ifc(revision_id).schema
            except ApiProblem:
                raise
            except Exception as exc:
                raise ApiProblem(
                    422, "ifc_invalido", "Não foi possível ler o IFC enviado."
                ) from exc
        try:
            parse_ids(str(path))
        except Exception as exc:
            raise ApiProblem(
                422, "ids_invalido", "IDS inválido (XML ou XSD IDS 1.0)."
            ) from exc
        return None

    def confirm(
        self, project_id: str, model_id: str, request: ConfirmBindingRequest
    ) -> ModelPairBinding:
        """Confirma o vínculo somente sobre as revisões atuais (409 se divergirem)."""
        binding = self.get_binding(project_id, model_id)
        if binding.ifc is None or binding.ids is None:
            raise ApiProblem(409, "vinculo_incompleto", "Envie IFC e IDS antes de confirmar.")
        if (
            request.ifc_revision_id != binding.ifc.revision_id
            or request.ids_revision_id != binding.ids.revision_id
        ):
            raise ApiProblem(
                409, "revisao_divergente", "As revisões confirmadas não são as atuais."
            )
        updated = binding.model_copy(
            update={
                "confirmed": True,
                "confirmed_ifc_revision_id": request.ifc_revision_id,
                "confirmed_ids_revision_id": request.ids_revision_id,
            }
        )
        self._replace_binding(ModelPairBinding.model_validate(updated.model_dump()))
        return self.get_binding(project_id, model_id)

    # -- leitura ----------------------------------------------------------

    def open_ifc(self, revision_id: str) -> ifcopenshell.file:
        """Abre (com cache pequeno) a revisão IFC armazenada."""
        with self._ifc_lock:
            cached = self._ifc_cache.get(revision_id)
            if cached is not None:
                return cached
            path = self.store.path_for("ifc", revision_id)
            if not path.exists():
                raise ApiProblem(404, "fonte_ausente", "Revisão IFC não está armazenada.")
            ifc_file = ifcopenshell.open(str(path))
            if len(self._ifc_cache) >= _IFC_CACHE_SIZE:
                self._ifc_cache.pop(next(iter(self._ifc_cache)))
            self._ifc_cache[revision_id] = ifc_file
            return ifc_file

    def require_ifc(self, project_id: str, model_id: str) -> ModelPairBinding:
        """Retorna a linha exigindo IFC registrado."""
        binding = self.get_binding(project_id, model_id)
        if binding.ifc is None:
            raise ApiProblem(409, "ifc_ausente", "Este modelo ainda não tem IFC.")
        return binding

    def elements(
        self, project_id: str, model_id: str
    ) -> tuple[ModelPairBinding, list[ElementRecord]]:
        """Elementos da revisão IFC atual da linha (cache por modelo + revisão)."""
        binding = self.require_ifc(project_id, model_id)
        assert binding.ifc is not None
        revision_id = binding.ifc.revision_id
        with self._ifc_lock:
            cached = self._element_cache.get((model_id, revision_id))
            if cached is None:
                cached = list_elements(self.open_ifc(revision_id), model_id, revision_id)
                self._element_cache[(model_id, revision_id)] = cached
        return binding, cached

    def gaps(self, project_id: str, model_id: str) -> tuple[ModelPairBinding, list[Gap]]:
        """Lacunas via adaptador legado; exige vínculo confirmado."""
        binding = self.get_binding(project_id, model_id)
        if not binding.confirmed or binding.ifc is None or binding.ids is None:
            raise ApiProblem(
                409, "vinculo_nao_confirmado", "Confirme IFC e IDS desta linha antes de analisar."
            )
        key = (model_id, binding.ifc.revision_id, binding.ids.revision_id)
        with self._ifc_lock:
            cached = self._gap_cache.get(key)
            if cached is None:
                cached = compute_gaps(
                    self.store.path_for("ifc", binding.ifc.revision_id),
                    self.store.path_for("ids", binding.ids.revision_id),
                    model_id,
                    binding.ifc.revision_id,
                )
                self._gap_cache[key] = cached
        return binding, cached
