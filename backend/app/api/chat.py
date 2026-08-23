from typing import Annotated

from fastapi import APIRouter, Depends, Header

from backend.app.api.dependencies import get_chat_service
from backend.app.api.errors import error_responses
from backend.app.schemas import ChatRequest, ChatResponse
from backend.app.services.chat_service import ChatService


router = APIRouter(prefix="/api", tags=["agent"])
ChatServiceDependency = Annotated[ChatService, Depends(get_chat_service)]


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses=error_responses(400, 404, 409, 422, 500, 502),
)
def chat(
    request: ChatRequest,
    service: ChatServiceDependency,
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
    return service.run(request, idempotency_key=idempotency_key)
