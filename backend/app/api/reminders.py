from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status

from backend.app.api.dependencies import (
    get_current_user,
    get_reminder_service,
    require_trusted_origin,
)
from backend.app.api.errors import error_responses
from backend.app.schemas import (
    DeleteResponse,
    DueReminderParams,
    DueReminderQuery,
    ReminderAckBody,
    ReminderAckRequest,
    ReminderAckResponse,
    ReminderCreateBody,
    ReminderCreateRequest,
    ReminderListParams,
    ReminderListQuery,
    ReminderListResponse,
    ReminderUpdateBody,
    ReminderUpdateRequest,
    ReminderView,
    UserView,
)
from backend.app.services import ReminderService


router = APIRouter(prefix="/api/reminders", tags=["reminders"])
ReminderServiceDependency = Annotated[ReminderService, Depends(get_reminder_service)]
CurrentUserDependency = Annotated[UserView, Depends(get_current_user)]


@router.post(
    "",
    response_model=ReminderView,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 404, 422, 500),
    dependencies=[Depends(require_trusted_origin)],
)
def create_reminder(
    request: ReminderCreateBody,
    service: ReminderServiceDependency,
    current_user: CurrentUserDependency,
) -> ReminderView:
    command = ReminderCreateRequest(
        user_id=str(current_user.id),
        **request.model_dump(),
    )
    return service.create(command)


@router.get(
    "",
    response_model=ReminderListResponse,
    responses=error_responses(401, 404, 422, 500),
)
def list_reminders(
    query: Annotated[ReminderListParams, Query()],
    service: ReminderServiceDependency,
    current_user: CurrentUserDependency,
) -> ReminderListResponse:
    command = ReminderListQuery(
        user_id=str(current_user.id),
        **query.model_dump(),
    )
    return service.list(command)


@router.get(
    "/due",
    response_model=ReminderListResponse,
    responses=error_responses(401, 404, 422, 500),
)
def list_due_reminders(
    query: Annotated[DueReminderParams, Query()],
    service: ReminderServiceDependency,
    current_user: CurrentUserDependency,
) -> ReminderListResponse:
    command = DueReminderQuery(
        user_id=str(current_user.id),
        **query.model_dump(),
    )
    return service.list_due(command)


@router.patch(
    "/{id}",
    response_model=ReminderView,
    responses=error_responses(400, 401, 403, 404, 409, 422, 500),
    dependencies=[Depends(require_trusted_origin)],
)
def update_reminder(
    id: Annotated[UUID, Path()],
    request: ReminderUpdateBody,
    service: ReminderServiceDependency,
    current_user: CurrentUserDependency,
) -> ReminderView:
    command = ReminderUpdateRequest(
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
def delete_reminder(
    id: Annotated[UUID, Path()],
    service: ReminderServiceDependency,
    current_user: CurrentUserDependency,
) -> DeleteResponse:
    return service.delete(id, str(current_user.id))


@router.post(
    "/{id}/ack",
    response_model=ReminderAckResponse,
    responses=error_responses(401, 403, 404, 409, 422, 500),
    dependencies=[Depends(require_trusted_origin)],
)
def acknowledge_reminder(
    id: Annotated[UUID, Path()],
    request: ReminderAckBody,
    service: ReminderServiceDependency,
    current_user: CurrentUserDependency,
) -> ReminderAckResponse:
    command = ReminderAckRequest(
        user_id=str(current_user.id),
        **request.model_dump(),
    )
    return service.acknowledge(id, command)
