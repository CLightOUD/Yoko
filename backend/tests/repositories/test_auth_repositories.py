from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.app.repositories import AuthSessionRepository, UserRepository


def test_account_username_is_unique_after_normalization(database) -> None:
    users = UserRepository(database)
    created = users.create_account(
        user_id=str(uuid4()),
        username="Alice_01",
        username_normalized="alice_01",
        password_hash="$argon2id$encoded-only",
        display_name="Alice",
        timezone="Asia/Shanghai",
    )

    assert users.get_by_normalized_username("alice_01")["id"] == created["id"]
    with pytest.raises(sqlite3.IntegrityError):
        users.create_account(
            user_id=str(uuid4()),
            username="alice_01",
            username_normalized="alice_01",
            password_hash="$argon2id$another-encoded-value",
            display_name="Other",
            timezone="Asia/Shanghai",
        )


def test_session_lifecycle_uses_hash_and_exact_expiry_boundary(database) -> None:
    users = UserRepository(database)
    user = users.create_account(
        user_id=str(uuid4()),
        username="alice_01",
        username_normalized="alice_01",
        password_hash="$argon2id$encoded-only",
        display_name="Alice",
        timezone="Asia/Shanghai",
    )
    sessions = AuthSessionRepository(database)
    now = datetime(2026, 8, 24, tzinfo=UTC)
    expires_at = now + timedelta(days=180)
    raw_token = "raw-session-token"
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    sessions.create(
        session_id=str(uuid4()),
        user_id=user["id"],
        token_hash=token_hash,
        created_at=now,
        expires_at=expires_at,
    )

    assert sessions.get_active_by_token_hash(
        token_hash, now=expires_at - timedelta(microseconds=1)
    ) is not None
    assert sessions.get_active_by_token_hash(token_hash, now=expires_at) is None
    with database.connection() as connection:
        stored = connection.execute(
            "SELECT token_hash FROM auth_sessions"
        ).fetchone()[0]
    assert stored == token_hash
    assert stored != raw_token

    assert sessions.revoke_by_token_hash(token_hash, revoked_at=now) is True
    assert sessions.revoke_by_token_hash(token_hash, revoked_at=now) is False
    assert sessions.get_active_by_token_hash(token_hash, now=now) is None


def test_deleting_expired_sessions_preserves_user_business_data(database) -> None:
    sessions = AuthSessionRepository(database)
    now = datetime(2026, 8, 24, tzinfo=UTC)
    sessions.create(
        session_id=str(uuid4()),
        user_id="demo-user",
        token_hash="expired-hash",
        created_at=now - timedelta(days=2),
        expires_at=now - timedelta(days=1),
    )
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO reminders (
                id, user_id, title, next_trigger_at, timezone, repeat_type,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "preserved-reminder",
                "demo-user",
                "散步",
                "2027-01-01T00:00:00+00:00",
                "Asia/Shanghai",
                "none",
                "active",
                now.isoformat(),
                now.isoformat(),
            ),
        )

    assert sessions.delete_expired(now=now) == 1
    with database.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM reminders").fetchone()[0] == 1
