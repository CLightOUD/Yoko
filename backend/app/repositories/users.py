from __future__ import annotations

import sqlite3
from typing import Any

from backend.app.repositories._common import BaseRepository, row_to_dict, utc_now_iso


class UserRepository(BaseRepository):
    def create(
        self,
        *,
        user_id: str,
        display_name: str,
        timezone: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connection(connection, write=True) as active_connection:
            active_connection.execute(
                """
                INSERT INTO users (id, display_name, timezone, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, display_name, timezone, now, now),
            )
            row = active_connection.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return dict(row)

    def get(
        self,
        user_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        with self._connection(connection) as active_connection:
            row = active_connection.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return row_to_dict(row)

    def create_account(
        self,
        *,
        user_id: str,
        username: str,
        username_normalized: str,
        password_hash: str,
        display_name: str,
        timezone: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connection(connection, write=True) as active_connection:
            active_connection.execute(
                """
                INSERT INTO users (
                    id, username, username_normalized, password_hash,
                    display_name, timezone, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    username,
                    username_normalized,
                    password_hash,
                    display_name,
                    timezone,
                    now,
                    now,
                ),
            )
            row = active_connection.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return dict(row)

    def get_by_normalized_username(
        self,
        username_normalized: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        with self._connection(connection) as active_connection:
            row = active_connection.execute(
                "SELECT * FROM users WHERE username_normalized = ?",
                (username_normalized,),
            ).fetchone()
        return row_to_dict(row)

    def update_login_state(
        self,
        user_id: str,
        *,
        failed_login_count: int,
        login_blocked_until: str | None,
        last_login_at: str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        updates = [
            "failed_login_count = ?",
            "login_blocked_until = ?",
            "updated_at = ?",
        ]
        values: list[Any] = [
            failed_login_count,
            login_blocked_until,
            utc_now_iso(),
        ]
        if last_login_at is not None:
            updates.append("last_login_at = ?")
            values.append(last_login_at)
        values.append(user_id)
        with self._connection(connection, write=True) as active_connection:
            active_connection.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
                values,
            )
            row = active_connection.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        if row is None:
            raise LookupError(f"user does not exist: {user_id}")
        return dict(row)

    def exists(
        self,
        user_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> bool:
        with self._connection(connection) as active_connection:
            row = active_connection.execute(
                "SELECT 1 FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return row is not None
