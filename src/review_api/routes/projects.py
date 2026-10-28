"""Rotas de projeto, envio de fontes (upload) e confirmação de vínculo."""

from typing import Annotated

from fastapi import APIRouter, Query, Request
from starlette.concurrency import run_in_threadpool

from src.review_api.errors import ApiProblem
from src.review_api.registry import MAX_UPLOAD_BYTES, ProjectRegistry
from src.review_api.schemas import (
    ApiError,
    ArtifactRole,
    ConfirmBindingRequest,
    CreateProjectRequest,
    ModelPairBinding,
    Project,
    ProjectList,
)

router = APIRouter(prefix="/api/v1", tags=["projetos"])

_ERRORS = {
    404: {"model": ApiError},
    409: {"model": ApiError},
    413: {"model": ApiError},
    422: {"model": ApiError},
}
_BINARY_BODY = {
    "requestBody": {
        "required": True,
        "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
    }
}


def _registry(request: Request) -> ProjectRegistry:
    """Obtém o registro da aplicação."""
    return request.app.state.registry


@router.post("/projects", response_model=Project, status_code=201, operation_id="createProject")
def create_project(body: CreateProjectRequest, request: Request) -> Project:
    """Cria projeto com as linhas arquitetura e estrutura vazias."""
    return _registry(request).create_project(body.name)


@router.get("/projects", response_model=ProjectList, operation_id="listProjects")
def list_projects(request: Request) -> ProjectList:
    """Lista os projetos salvos no armazenamento local (mais recentes primeiro)."""
    items = _registry(request).list_projects()
    return ProjectList(total=len(items), items=items)


@router.get(
    "/projects/{project_id}",
    response_model=Project,
    responses=_ERRORS,
    operation_id="getProject",
)
def get_project(project_id: str, request: Request) -> Project:
    """Retorna o projeto e suas duas linhas."""
    return _registry(request).get_project(project_id)


async def _upload(
    request: Request, project_id: str, model_id: str, role: ArtifactRole, filename: str
) -> ModelPairBinding:
    """Lê o corpo binário e registra a fonte fora do loop de eventos."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES:
        raise ApiProblem(413, "arquivo_grande", "Arquivo acima do limite desta fatia.")
    data = await request.body()
    return await run_in_threadpool(
        _registry(request).register_source, project_id, model_id, role, data, filename
    )


@router.put(
    "/projects/{project_id}/models/{model_id}/ifc",
    response_model=ModelPairBinding,
    responses=_ERRORS,
    openapi_extra=_BINARY_BODY,
    operation_id="uploadIfc",
)
async def upload_ifc(
    project_id: str,
    model_id: str,
    filename: Annotated[str, Query(min_length=1, max_length=255)],
    request: Request,
) -> ModelPairBinding:
    """Recebe os bytes do IFC (corpo application/octet-stream)."""
    return await _upload(request, project_id, model_id, "ifc", filename)


@router.put(
    "/projects/{project_id}/models/{model_id}/ids",
    response_model=ModelPairBinding,
    responses=_ERRORS,
    openapi_extra=_BINARY_BODY,
    operation_id="uploadIds",
)
async def upload_ids(
    project_id: str,
    model_id: str,
    filename: Annotated[str, Query(min_length=1, max_length=255)],
    request: Request,
) -> ModelPairBinding:
    """Recebe os bytes do IDS (corpo application/octet-stream)."""
    return await _upload(request, project_id, model_id, "ids", filename)


@router.post(
    "/projects/{project_id}/models/{model_id}/confirm",
    response_model=ModelPairBinding,
    responses=_ERRORS,
    operation_id="confirmBinding",
)
def confirm_binding(
    project_id: str, model_id: str, body: ConfirmBindingRequest, request: Request
) -> ModelPairBinding:
    """Confirma explicitamente o vínculo disciplina–IFC–IDS pelas revisões."""
    return _registry(request).confirm(project_id, model_id, body)
