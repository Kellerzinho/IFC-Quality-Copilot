"""Rotas somente leitura: elementos, arquivo IFC para o viewer e lacunas."""

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from src.review_api.errors import ApiProblem
from src.review_api.legacy_adapter import LEGACY_SOURCE, LIMITATIONS
from src.review_api.registry import ProjectRegistry
from src.review_api.schemas import ApiError, ElementList, ElementRecord, GapList

router = APIRouter(prefix="/api/v1", tags=["analise"])

_ERRORS = {404: {"model": ApiError}, 409: {"model": ApiError}}


def _registry(request: Request) -> ProjectRegistry:
    """Obtém o registro da aplicação."""
    return request.app.state.registry


def _elements(registry: ProjectRegistry, project_id: str, model_id: str) -> ElementList:
    """Lista elementos da revisão IFC atual da linha."""
    binding, items = registry.elements(project_id, model_id)
    assert binding.ifc is not None
    return ElementList(
        model_id=model_id, ifc_revision_id=binding.ifc.revision_id, total=len(items), items=items
    )


@router.get(
    "/projects/{project_id}/models/{model_id}/elements",
    response_model=ElementList,
    responses=_ERRORS,
    operation_id="listElements",
)
async def get_elements(project_id: str, model_id: str, request: Request) -> ElementList:
    """Lista os elementos (IfcElement e IfcSpace, sem aberturas) do IFC da linha."""
    return await run_in_threadpool(_elements, _registry(request), project_id, model_id)


@router.get(
    "/projects/{project_id}/models/{model_id}/elements/{express_id}",
    response_model=ElementRecord,
    responses=_ERRORS,
    operation_id="getElement",
)
async def get_element(
    project_id: str, model_id: str, express_id: int, request: Request
) -> ElementRecord:
    """Resolve um express_id (ex.: vindo do viewer) para o ElementRecord da linha.

    Um id que não pertence à lista de elementos responde 404; nunca devolve
    outro elemento parecido.
    """
    listing = await run_in_threadpool(_elements, _registry(request), project_id, model_id)
    for record in listing.items:
        if record.ref.express_id == express_id:
            return record
    raise ApiProblem(404, "elemento_inexistente", "Elemento não encontrado nesta revisão.")


@router.get(
    "/projects/{project_id}/models/{model_id}/ifc-file",
    responses={200: {"content": {"application/octet-stream": {}}}, **_ERRORS},
    response_class=FileResponse,
    operation_id="getIfcFile",
)
def get_ifc_file(project_id: str, model_id: str, request: Request) -> FileResponse:
    """Serve os bytes do IFC da linha ao viewer; cabeçalho X-Ifc-Revision identifica a revisão."""
    registry = _registry(request)
    binding = registry.require_ifc(project_id, model_id)
    assert binding.ifc is not None
    path = registry.store.path_for("ifc", binding.ifc.revision_id)
    if not path.exists():
        raise ApiProblem(404, "fonte_ausente", "Revisão IFC não está armazenada.")
    return FileResponse(
        path,
        media_type="application/octet-stream",
        headers={"X-Ifc-Revision": binding.ifc.revision_id, "Cache-Control": "no-store"},
    )


def _gaps(registry: ProjectRegistry, project_id: str, model_id: str) -> GapList:
    """Monta a lista PROVISÓRIA de lacunas pelo adaptador legado."""
    binding, items = registry.gaps(project_id, model_id)
    assert binding.ifc is not None
    assert binding.ids is not None
    return GapList(
        model_id=model_id,
        ifc_revision_id=binding.ifc.revision_id,
        ids_revision_id=binding.ids.revision_id,
        source=LEGACY_SOURCE,
        total=len(items),
        items=items,
        limitations=LIMITATIONS,
    )


@router.get(
    "/projects/{project_id}/models/{model_id}/gaps",
    response_model=GapList,
    responses=_ERRORS,
    operation_id="listGaps",
)
async def get_gaps(project_id: str, model_id: str, request: Request) -> GapList:
    """Lista lacunas PROVISÓRIAS (adaptador legado) de uma linha confirmada."""
    return await run_in_threadpool(_gaps, _registry(request), project_id, model_id)
