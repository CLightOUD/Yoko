from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.app.repositories import UserRepository
from backend.app.schemas import LoginRequest, RegisterRequest
from backend.app.services import (
    AuthenticationRequiredError,
    AuthService,
    InvalidCredentialsError,
    UsernameAlreadyExistsError,
)


PASSWORD = "correct-horse-2026"


def registration(username: str = "Alice_01") -> RegisterRequest:
    return RegisterRequest(
        username=username,
        password=PASSWORD,
        display_name="李阿姨",
        timezone="Asia/Shanghai",
    )


def test_register_hashes_password_and_rejects_normalized_duplicate(database) -> None:
    service = AuthService(database)
    issued = service.register(registration("Alice_01"))
    user = UserRepository(database).get_by_normalized_username("alice_01")

    assert issued.response.user.username == "Alice_01"
    assert user["password_hash"].startswith("$argon2id$")
    assert user["password_hash"] != PASSWORD
    with database.connection() as connection:
        row = connection.execute(
            "SELECT token_hash FROM auth_sessions WHERE user_id = ?", (user["id"],)
        ).fetchone()
    assert row["token_hash"] != issued.token
    assert issued.token not in row["token_hash"]

    with pytest.raises(UsernameAlreadyExistsError):
        service.register(registration("  ALICE_01  "))


def test_login_sessions_are_independent_expire_at_boundary_and_revoke(
    database, monkeypatch
) -> None:
    now = datetime(2026, 8, 24, 1, 2, 3, tzinfo=UTC)
    monkeypatch.setattr(AuthService, "_utc_now", staticmethod(lambda: now))
    service = AuthService(database)
    first = service.register(registration())
    second = service.login(LoginRequest(username="alice_01", password=PASSWORD))

    assert first.token != second.token
    assert service.resolve_session(first.token).user == first.response.user
    assert service.resolve_session(second.token).user == second.response.user

    expires_at = first.response.session_expires_at
    monkeypatch.setattr(
        AuthService,
        "_utc_now",
        staticmethod(lambda: expires_at - timedelta(microseconds=1)),
    )
    assert service.resolve_session(first.token).user == first.response.user
    monkeypatch.setattr(AuthService, "_utc_now", staticmethod(lambda: expires_at))
    with pytest.raises(AuthenticationRequiredError):
        service.resolve_session(first.token)

    monkeypatch.setattr(AuthService, "_utc_now", staticmethod(lambda: now))
    service.logout(first.token)
    with pytest.raises(AuthenticationRequiredError):
        service.resolve_session(first.token)
    assert service.resolve_session(second.token).user == second.response.user
    service.logout(None)


def test_invalid_credentials_are_generic_and_login_limit_resets_after_success(
    database, monkeypatch
) -> None:
    now = datetime(2026, 8, 24, tzinfo=UTC)
    monkeypatch.setattr(AuthService, "_utc_now", staticmethod(lambda: now))
    service = AuthService(database)
    service.register(registration())
    wrong = LoginRequest(username="alice_01", password="wrong-password-2026")

    with pytest.raises(InvalidCredentialsError) as existing:
        service.login(wrong)
    with pytest.raises(InvalidCredentialsError) as missing:
        service.login(LoginRequest(username="missing", password="wrong-password-2026"))
    assert str(existing.value) == str(missing.value) == "用户名或密码错误"

    for _ in range(3):
        with pytest.raises(InvalidCredentialsError):
            service.login(wrong)
    with pytest.raises(InvalidCredentialsError):
        service.login(wrong)
    with pytest.raises(InvalidCredentialsError):
        service.login(LoginRequest(username="alice_01", password=PASSWORD))

    for _ in range(5):
        with pytest.raises(InvalidCredentialsError) as missing_again:
            service.login(
                LoginRequest(username="missing", password="wrong-password-2026")
            )
        assert str(missing_again.value) == "用户名或密码错误"

    after_block = now + timedelta(minutes=15)
    monkeypatch.setattr(
        AuthService, "_utc_now", staticmethod(lambda: after_block)
    )
    service.login(LoginRequest(username="alice_01", password=PASSWORD))
    user = UserRepository(database).get_by_normalized_username("alice_01")
    assert user["failed_login_count"] == 0
    assert user["login_blocked_until"] is None
    assert user["last_login_at"] == after_block.isoformat()
