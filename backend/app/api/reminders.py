from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status

from backend.app.api.dependencies import get_reminder_service
from backend.app.api.errors import error_responses
from backend.app.schemas import (
    DeleteResponse,
    DueReminderQuery,
    ReminderAckRequest,
    ReminderAckResponse,
    ReminderCreateRequest,
    ReminderListQuery,
    ReminderListResponse,
    ReminderUpdateRequest,
    ReminderView,
)
from backend.app.schemas.common import UserId
from backend.app.services import ReminderService


router = APIRouter(prefix="/api/reminders", tags=["reminders"])
ReminderServiceDependency = Annotated[ReminderService, Depends(get_reminder_service)]


@router.post(
    "",
    response_model=ReminderView,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(404, 422, 500),
)
def create_reminder(
    request: ReminderCreateRequest,
    service: ReminderServiceDependency,
) -> ReminderView:
    return service.create(request)


@router.get(
    "",
    response_model=ReminderListResponse,
    responses=error_responses(404, 422, 500),
)
def list_reminders(
    query: Annotated[ReminderListQuery, Query()],
    service: ReminderServiceDependency,
) -> ReminderListResponse:
    return service.list(query)


@router.get(
    "/due",
    response_model=ReminderListResponse,
    responses=error_responses(404, 422, 500),
)
def list_due_reminders(
    query: Annotated[DueReminderQuery, Query()],
    service: ReminderServiceDependency,
) -> ReminderListResponse:
    return service.list_due(query)


@router.patch(
    "/{id}",
    response_model=ReminderView,
    responses=error_responses(400, 404, 409, 422, 500),
)
def update_reminder(
    id: Annotated[UUID, Path()],
    request: ReminderUpdateRequest,
    service: ReminderServiceDependency,
) -> ReminderView:
    return service.update(id, request)


@router.delete(
    "/{id}",
    response_model=DeleteResponse,
    responses=error_responses(404, 422, 500),
)
def delete_reminder(
    id: Annotated[UUID, Path()],
    user_id: Annotated[UserId, Query()],
    service: ReminderServiceDependency,
) -> DeleteResponse:
    return service.delete(id, user_id)


@router.post(
    "/{id}/ack",
    response_model=ReminderAckResponse,
    responses=error_responses(404, 409, 422, 500),
)
def acknowledge_reminder(
    id: Annotated[UUID, Path()],
    request: ReminderAckRequest,
    service: ReminderServiceDependency,
) -> ReminderAckResponse:
    return service.acknowledge(id, request)
