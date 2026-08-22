from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import get_chat_service
from backend.app.api.errors import error_responses
from backend.app.schemas import ChatRequest, ChatResponse
from backend.app.services.chat_service import ChatService


router = APIRouter(prefix="/api", tags=["agent"])
ChatServiceDependency = Annotated[ChatService, Depends(get_chat_service)]


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses=error_responses(400, 404, 422, 500, 502),
)
def chat(request: ChatRequest, service: ChatServiceDependency) -> ChatResponse:
    return service.run(request)
