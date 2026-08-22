from __future__ import annotations

import sqlite3

import pytest

from backend.app.database import Database
from backend.app.repositories import UserRepository


EXPECTED_TABLES = {
    "feedbacks",
    "memories",
    "memory_events",
    "messages",
    "reminders",
    "request_metrics",
    "users",
}


def test_initialize_is_idempotent_and_seeds_demo_user(database: Database) -> None:
    database.initialize()

    with database.connection() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]

    assert EXPECTED_TABLES <= tables
    assert foreign_keys == 1
    assert UserRepository(database).get("demo-user") == {
        "id": "demo-user",
        "display_name": "用户",
        "timezone": "Asia/Shanghai",
        "created_at": UserRepository(database).get("demo-user")["created_at"],
        "updated_at": UserRepository(database).get("demo-user")["updated_at"],
    }


def test_transaction_rolls_back_all_writes(database: Database) -> None:
    with pytest.raises(RuntimeError, match="force rollback"):
        with database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO users (id, display_name, timezone, created_at, updated_at)
                VALUES ('rolled-back', '临时用户', 'Asia/Shanghai', 'now', 'now')
                """
            )
            raise RuntimeError("force rollback")

    assert UserRepository(database).get("rolled-back") is None


def test_foreign_keys_reject_unknown_users(database: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO reminders (
                    id, user_id, title, next_trigger_at, timezone, repeat_type,
                    status, last_triggered_at, created_at, updated_at
                ) VALUES (
                    'bad-reminder', 'missing-user', '标题',
                    '2026-08-23T10:00:00+08:00', 'Asia/Shanghai', 'none',
                    'active', NULL, 'now', 'now'
                )
                """
            )
