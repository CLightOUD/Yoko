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
