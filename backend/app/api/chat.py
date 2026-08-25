from typing import Annotated

from fastapi import APIRouter, Depends, Header

from backend.app.api.dependencies import (
    get_chat_service,
    get_current_user,
    require_trusted_origin,
)
from backend.app.api.errors import error_responses
from backend.app.schemas import ChatRequest, ChatRequestBody, ChatResponse, UserView
from backend.app.services.chat_service import ChatService


router = APIRouter(prefix="/api", tags=["agent"])
ChatServiceDependency = Annotated[ChatService, Depends(get_chat_service)]
CurrentUserDependency = Annotated[UserView, Depends(get_current_user)]


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses=error_responses(400, 401, 403, 404, 409, 422, 500, 502, 503),
    dependencies=[Depends(require_trusted_origin)],
)
def chat(
    request: ChatRequestBody,
    service: ChatServiceDependency,
    current_user: CurrentUserDependency,
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            min_length=8,
            max_length=128,
            pattern=r"^[A-Za-z0-9._:-]+$",
        ),
    ] = None,
) -> ChatResponse:
    command = ChatRequest(
        user_id=str(current_user.id),
        **request.model_dump(),
    )
    return service.run(command, idempotency_key=idempotency_key)
