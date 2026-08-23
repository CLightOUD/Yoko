from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pwdlib import PasswordHash

from backend.app.database import Database
from backend.app.main import create_app
from backend.app.schemas import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UserView,
)
from backend.app.services.auth_service import IssuedSession


def auth_response() -> AuthResponse:
    return AuthResponse(
        user=UserView(
            id=uuid4(),
            username="alice_01",
            display_name="李阿姨",
            timezone="Asia/Shanghai",
        ),
        session_expires_at=datetime.now(UTC) + timedelta(days=180),
    )


class FakeAuthService:
    def __init__(self) -> None:
        self.response = auth_response()
        self.last_logout_token: str | None = None

    def register(self, request: RegisterRequest) -> IssuedSession:
        assert request.password.get_secret_value() == "correct-horse-2026"
        return IssuedSession(token="raw-session-token", response=self.response)

    def login(self, request: LoginRequest) -> IssuedSession:
        assert request.username == "alice_01"
        return IssuedSession(token="raw-session-token", response=self.response)

    def resolve_session(self, session_token: str | None) -> AuthResponse:
        assert session_token == "raw-session-token"
        return self.response

    def logout(self, session_token: str | None) -> None:
        self.last_logout_token = session_token


def test_auth_request_models_hide_passwords_and_validate_fields() -> None:
    request = RegisterRequest(
        username=" alice_01 ",
        password="correct-horse-2026",
        display_name=" 李阿姨 ",
    )

    assert request.username == "alice_01"
    assert request.display_name == "李阿姨"
    assert request.password.get_secret_value() == "correct-horse-2026"
    assert "correct-horse-2026" not in repr(request)

    with pytest.raises(ValidationError):
        RegisterRequest(
            username="中文账号",
            password="correct-horse-2026",
            display_name="李阿姨",
        )

    with pytest.raises(ValidationError):
        LoginRequest(username="alice_01", password="short")

    with pytest.raises(ValidationError, match="valid IANA timezone"):
        RegisterRequest(
            username="alice_01",
            password="correct-horse-2026",
            display_name="李阿姨",
            timezone="Mars/Olympus",
        )

    with pytest.raises(ValidationError, match="must include a timezone"):
        AuthResponse(
            user=auth_response().user,
            session_expires_at=datetime.now(),
        )


def test_password_hash_dependency_uses_argon2id() -> None:
    password_hash = PasswordHash.recommended()
    encoded = password_hash.hash("correct-horse-2026")

    assert encoded.startswith("$argon2id$")
    assert password_hash.verify("correct-horse-2026", encoded) is True
    assert password_hash.verify("wrong-password", encoded) is False


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "post",
            "/api/auth/register",
            {
                "username": "alice_01",
                "password": "correct-horse-2026",
                "display_name": "李阿姨",
                "timezone": "Asia/Shanghai",
            },
        ),
        (
            "post",
            "/api/auth/login",
            {"username": "alice_01", "password": "correct-horse-2026"},
        ),
        ("get", "/api/auth/me", None),
        ("post", "/api/auth/logout", None),
    ],
)
def test_stage_one_auth_routes_fail_explicitly_without_side_effects(
    client: TestClient,
    method: str,
    path: str,
    payload: dict[str, str] | None,
) -> None:
    response = client.request(method, path, json=payload)

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "AUTHENTICATION_UNAVAILABLE",
        "message": "认证服务尚未完成接入",
        "details": None,
    }
    assert "set-cookie" not in response.headers


def test_auth_routes_set_secure_cookie_and_use_frozen_response_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeAuthService()
    monkeypatch.setenv("AUTH_COOKIE_NAME", "__Host-yoko_session")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")
    app = create_app(
        database=Database(tmp_path / "auth-contract.db"),
        auth_service=service,  # type: ignore[arg-type]
    )

    with TestClient(app, base_url="https://testserver") as client:
        registered = client.post(
            "/api/auth/register",
            json={
                "username": "alice_01",
                "password": "correct-horse-2026",
                "display_name": "李阿姨",
                "timezone": "Asia/Shanghai",
            },
        )
        cookie = registered.headers["set-cookie"]

        assert registered.status_code == 201
        assert registered.json() == service.response.model_dump(mode="json")
        assert "raw-session-token" not in registered.text
        assert "__Host-yoko_session=raw-session-token" in cookie
        assert "HttpOnly" in cookie
        assert "Secure" in cookie
        assert "SameSite=lax" in cookie
        assert "Path=/" in cookie

        current = client.get("/api/auth/me")
        assert current.status_code == 200
        assert current.json() == service.response.model_dump(mode="json")

        logged_out = client.post("/api/auth/logout")
        assert logged_out.status_code == 200
        assert logged_out.json() == {"logged_out": True}
        assert service.last_logout_token == "raw-session-token"


def test_auth_openapi_contract_is_registered() -> None:
    app = create_app()
    paths = app.openapi()["paths"]

    assert paths["/api/auth/register"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/AuthResponse"}
    assert paths["/api/auth/login"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/AuthResponse"}
    assert paths["/api/auth/me"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/AuthResponse"}
    assert paths["/api/auth/logout"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/LogoutResponse"}
