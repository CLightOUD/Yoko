from __future__ import annotations

from dataclasses import dataclass

from backend.app.database import Database
from backend.app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest
from backend.app.services.errors import AuthenticationUnavailableError


@dataclass(frozen=True, slots=True, repr=False)
class IssuedSession:
    """An authenticated response plus the raw token used only for Set-Cookie."""

    token: str
    response: AuthResponse


class AuthService:
    """Stage-one contract implemented by the data/service owner in stage two."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def register(self, request: RegisterRequest) -> IssuedSession:
        raise AuthenticationUnavailableError("认证服务尚未完成接入")

    def login(self, request: LoginRequest) -> IssuedSession:
        raise AuthenticationUnavailableError("认证服务尚未完成接入")

    def resolve_session(self, session_token: str | None) -> AuthResponse:
        raise AuthenticationUnavailableError("认证服务尚未完成接入")

    def logout(self, session_token: str | None) -> None:
        raise AuthenticationUnavailableError("认证服务尚未完成接入")
