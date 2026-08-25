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


def test_real_auth_routes_restore_and_revoke_session(client: TestClient) -> None:
    current = client.get("/api/auth/me")
    assert current.status_code == 200
    assert current.json()["user"]["id"] == client.app.state.test_user_id

    logged_out = client.post("/api/auth/logout")
    assert logged_out.status_code == 200
    assert logged_out.json() == {"logged_out": True}
    assert client.get("/api/auth/me").status_code == 401

    logged_in = client.post(
        "/api/auth/login",
        json={
            "username": "api_test_user",
            "password": "correct-horse-2026",
        },
    )
    assert logged_in.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_locked_and_missing_accounts_return_the_same_login_error(
    client: TestClient,
) -> None:
    client.post("/api/auth/logout")
    errors = []
    for _ in range(5):
        response = client.post(
            "/api/auth/login",
            json={
                "username": "api_test_user",
                "password": "wrong-password-2026",
            },
        )
        errors.append((response.status_code, response.json()["error"]))

    blocked = client.post(
        "/api/auth/login",
        json={
            "username": "api_test_user",
            "password": "correct-horse-2026",
        },
    )
    missing = client.post(
        "/api/auth/login",
        json={
            "username": "missing_user",
            "password": "wrong-password-2026",
        },
    )

    expected = {
        "code": "INVALID_CREDENTIALS",
        "message": "用户名或密码错误",
        "details": None,
    }
    assert errors == [(401, expected)] * 5
    assert blocked.status_code == missing.status_code == 401
    assert blocked.json()["error"] == missing.json()["error"] == expected


def test_auth_write_rejects_untrusted_origin(tmp_path: Path) -> None:
    app = create_app(database=Database(tmp_path / "origin.db"))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/auth/register",
            headers={"Origin": "https://attacker.example"},
            json={
                "username": "alice_01",
                "password": "correct-horse-2026",
                "display_name": "李阿姨",
            },
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"


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

    with TestClient(
        app,
        base_url="https://testserver",
        headers={"Origin": "https://testserver"},
    ) as client:
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


def test_auth_endpoints_are_rate_limited_per_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RATE_LIMIT_AUTH_PER_MINUTE", "1")
    service = FakeAuthService()
    app = create_app(
        database=Database(tmp_path / "auth-rate-limit.db"),
        auth_service=service,  # type: ignore[arg-type]
    )
    payload = {
        "username": "alice_01",
        "password": "correct-horse-2026",
        "display_name": "李阿姨",
        "timezone": "Asia/Shanghai",
    }

    with TestClient(
        app,
        headers={"Origin": "http://127.0.0.1:5173"},
    ) as client:
        first = client.post("/api/auth/register", json=payload)
        limited = client.post("/api/auth/register", json=payload)

    assert first.status_code == 201
    assert limited.status_code == 429
    assert limited.json()["error"] == {
        "code": "TOO_MANY_ATTEMPTS",
        "message": "请求过于频繁，请稍后重试",
        "details": None,
    }
    assert int(limited.headers["retry-after"]) >= 1
    assert limited.headers["access-control-allow-origin"] == (
        "http://127.0.0.1:5173"
    )


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
