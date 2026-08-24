from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from backend.app.api.dependencies import (
    get_auth_cookie_name,
    get_auth_service,
    require_trusted_origin,
)
from backend.app.api.errors import error_responses
from backend.app.schemas import (
    AuthResponse,
    LoginRequest,
    LogoutResponse,
    RegisterRequest,
)
from backend.app.services.auth_service import AuthService, IssuedSession


router = APIRouter(prefix="/api/auth", tags=["authentication"])
AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]


def _env_flag(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _set_session_cookie(response: Response, issued: IssuedSession) -> None:
    expires_at = issued.response.session_expires_at.astimezone(UTC)
    max_age = max(0, int((expires_at - datetime.now(UTC)).total_seconds()))
    cookie_name = get_auth_cookie_name()
    secure = _env_flag("AUTH_COOKIE_SECURE", default=False)
    if cookie_name.startswith("__Host-") and not secure:
        raise RuntimeError("__Host- cookies require AUTH_COOKIE_SECURE=true")
    response.set_cookie(
        key=cookie_name,
        value=issued.token,
        max_age=max_age,
        expires=expires_at,
        path="/",
        secure=secure,
        httponly=True,
        samesite="lax",
    )


def _session_token(request: Request) -> str | None:
    return request.cookies.get(get_auth_cookie_name())


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(403, 409, 422, 500, 503),
    dependencies=[Depends(require_trusted_origin)],
)
def register(
    request: RegisterRequest,
    response: Response,
    service: AuthServiceDependency,
) -> AuthResponse:
    issued = service.register(request)
    _set_session_cookie(response, issued)
    return issued.response


@router.post(
    "/login",
    response_model=AuthResponse,
    responses=error_responses(401, 403, 422, 500, 503),
    dependencies=[Depends(require_trusted_origin)],
)
def login(
    request: LoginRequest,
    response: Response,
    service: AuthServiceDependency,
) -> AuthResponse:
    issued = service.login(request)
    _set_session_cookie(response, issued)
    return issued.response


@router.get(
    "/me",
    response_model=AuthResponse,
    responses=error_responses(401, 500, 503),
)
def current_user(
    request: Request,
    service: AuthServiceDependency,
) -> AuthResponse:
    return service.resolve_session(_session_token(request))


@router.post(
    "/logout",
    response_model=LogoutResponse,
    responses=error_responses(403, 500, 503),
    dependencies=[Depends(require_trusted_origin)],
)
def logout(
    request: Request,
    response: Response,
    service: AuthServiceDependency,
) -> LogoutResponse:
    service.logout(_session_token(request))
    response.delete_cookie(key=get_auth_cookie_name(), path="/")
    return LogoutResponse(logged_out=True)
