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


def test_initialize_migrates_weekly_and_consolidates_legacy_duplicates(
    tmp_path,
) -> None:
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE users (
            id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            timezone TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE reminders (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            title TEXT NOT NULL,
            next_trigger_at TEXT NOT NULL,
            timezone TEXT NOT NULL,
            repeat_type TEXT NOT NULL CHECK (repeat_type IN ('none', 'daily')),
            status TEXT NOT NULL CHECK (status IN ('active', 'completed', 'deleted')),
            last_triggered_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        INSERT INTO users VALUES (
            'demo-user', '用户', 'Asia/Shanghai', '2026-01-01', '2026-01-01'
        );
        INSERT INTO reminders VALUES (
            'first', 'demo-user', '服药', '2027-01-05T01:00:00+00:00',
            'Asia/Shanghai', 'none', 'active', NULL, '2026-01-01', '2026-01-01'
        );
        INSERT INTO reminders VALUES (
            'second', 'demo-user', '测量血压', '2027-01-05T01:00:00+00:00',
            'Asia/Shanghai', 'none', 'active', NULL, '2026-01-02', '2026-01-02'
        );
        INSERT INTO reminders VALUES (
            'one-time', 'demo-user', '吃降压药', '2027-01-06T11:00:00+00:00',
            'Asia/Shanghai', 'none', 'active', NULL, '2026-01-03', '2026-01-03'
        );
        INSERT INTO reminders VALUES (
            'daily', 'demo-user', '吃降压药', '2027-01-06T11:00:00+00:00',
            'Asia/Shanghai', 'daily', 'active', NULL, '2026-01-04', '2026-01-04'
        );
        """
    )
    connection.close()

    database = Database(path)
    database.initialize()

    with database.connection() as migrated:
        table_sql = migrated.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'reminders'"
        ).fetchone()["sql"]
        reminders = migrated.execute(
            "SELECT id, title, status FROM reminders ORDER BY created_at"
        ).fetchall()
        unique_index = migrated.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'index' AND name = 'uq_reminders_active_schedule'
            """
        ).fetchone()

    assert "'weekly'" in table_sql
    assert [dict(item) for item in reminders] == [
        {"id": "first", "title": "服药；测量血压", "status": "active"},
        {"id": "second", "title": "测量血压", "status": "deleted"},
        {"id": "one-time", "title": "吃降压药", "status": "deleted"},
        {"id": "daily", "title": "吃降压药", "status": "active"},
    ]
    assert unique_index is not None


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
