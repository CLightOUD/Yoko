from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query

from backend.app.api.dependencies import (
    get_current_user,
    get_memory_service,
    require_trusted_origin,
)
from backend.app.api.errors import error_responses
from backend.app.schemas import (
    DeleteResponse,
    MemoryListParams,
    MemoryListQuery,
    MemoryListResponse,
    MemoryUpdateBody,
    MemoryUpdateRequest,
    MemoryView,
    UserView,
)
from backend.app.services import MemoryService


router = APIRouter(prefix="/api/memories", tags=["memories"])
MemoryServiceDependency = Annotated[MemoryService, Depends(get_memory_service)]
CurrentUserDependency = Annotated[UserView, Depends(get_current_user)]


@router.get(
    "",
    response_model=MemoryListResponse,
    responses=error_responses(401, 404, 422, 500),
)
def list_memories(
    query: Annotated[MemoryListParams, Query()],
    service: MemoryServiceDependency,
    current_user: CurrentUserDependency,
) -> MemoryListResponse:
    command = MemoryListQuery(
        user_id=str(current_user.id),
        **query.model_dump(),
    )
    return service.list(command)


@router.patch(
    "/{id}",
    response_model=MemoryView,
    responses=error_responses(401, 403, 404, 409, 422, 500),
    dependencies=[Depends(require_trusted_origin)],
)
def update_memory(
    id: Annotated[UUID, Path()],
    request: MemoryUpdateBody,
    service: MemoryServiceDependency,
    current_user: CurrentUserDependency,
) -> MemoryView:
    command = MemoryUpdateRequest(
        user_id=str(current_user.id),
        **request.model_dump(exclude_unset=True),
    )
    return service.update(id, command)


@router.delete(
    "/{id}",
    response_model=DeleteResponse,
    responses=error_responses(401, 403, 404, 422, 500),
    dependencies=[Depends(require_trusted_origin)],
)
def delete_memory(
    id: Annotated[UUID, Path()],
    service: MemoryServiceDependency,
    current_user: CurrentUserDependency,
) -> DeleteResponse:
    return service.delete(id, str(current_user.id))
