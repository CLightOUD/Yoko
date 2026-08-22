from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query

from backend.app.api.dependencies import get_memory_service
from backend.app.api.errors import error_responses
from backend.app.schemas import (
    DeleteResponse,
    MemoryListQuery,
    MemoryListResponse,
    MemoryUpdateRequest,
    MemoryView,
)
from backend.app.schemas.common import UserId
from backend.app.services import MemoryService


router = APIRouter(prefix="/api/memories", tags=["memories"])
MemoryServiceDependency = Annotated[MemoryService, Depends(get_memory_service)]


@router.get(
    "",
    response_model=MemoryListResponse,
    responses=error_responses(404, 422, 500),
)
def list_memories(
    query: Annotated[MemoryListQuery, Query()],
    service: MemoryServiceDependency,
) -> MemoryListResponse:
    return service.list(query)


@router.patch(
    "/{id}",
    response_model=MemoryView,
    responses=error_responses(404, 409, 422, 500),
)
def update_memory(
    id: Annotated[UUID, Path()],
    request: MemoryUpdateRequest,
    service: MemoryServiceDependency,
) -> MemoryView:
    return service.update(id, request)


@router.delete(
    "/{id}",
    response_model=DeleteResponse,
    responses=error_responses(404, 422, 500),
)
def delete_memory(
    id: Annotated[UUID, Path()],
    user_id: Annotated[UserId, Query()],
    service: MemoryServiceDependency,
) -> DeleteResponse:
    return service.delete(id, user_id)
