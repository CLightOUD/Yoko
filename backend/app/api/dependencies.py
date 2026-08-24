import os
from typing import Annotated

from fastapi import Depends, Request

from backend.app.database import Database
from backend.app.schemas import UserView
from backend.app.services import OriginNotAllowedError
from backend.app.services.auth_service import AuthService
from backend.app.services import MemoryService, MetricsService, ReminderService
from backend.app.services.chat_service import ChatService
from backend.app.services.feedback_service import FeedbackService


def get_database(request: Request) -> Database:
    return request.app.state.database


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


def get_auth_cookie_name() -> str:
    return os.getenv("AUTH_COOKIE_NAME", "yoko_session")


def get_current_user(
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserView:
    session_token = request.cookies.get(get_auth_cookie_name())
    return service.resolve_session(session_token).user


def require_trusted_origin(request: Request) -> None:
    origin = request.headers.get("Origin")
    configured_origin = os.getenv(
        "FRONTEND_ORIGIN", "http://127.0.0.1:5173"
    ).rstrip("/")
    request_origin = f"{request.url.scheme}://{request.url.netloc}".rstrip("/")
    if origin is None or origin.rstrip("/") not in {
        configured_origin,
        request_origin,
    }:
        raise OriginNotAllowedError("请求来源不受信任")


def get_reminder_service(request: Request) -> ReminderService:
    return request.app.state.reminder_service


def get_memory_service(request: Request) -> MemoryService:
    return request.app.state.memory_service


def get_metrics_service(request: Request) -> MetricsService:
    return request.app.state.metrics_service


def get_feedback_service(request: Request) -> FeedbackService:
    return request.app.state.feedback_service


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service
