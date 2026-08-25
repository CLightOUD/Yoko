from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from backend.app.repositories._common import (
    BaseRepository,
    normalize_datetime,
    row_to_dict,
)


class AuthSessionRepository(BaseRepository):
    def create(
        self,
        *,
        session_id: str,
        user_id: str,
        token_hash: str,
        created_at: datetime | str,
        expires_at: datetime | str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        created = normalize_datetime(created_at)
        expires = normalize_datetime(expires_at)
        with self._connection(connection, write=True) as active_connection:
            active_connection.execute(
                """
                INSERT INTO auth_sessions (
                    id, user_id, token_hash, created_at, expires_at,
                    last_seen_at, revoked_at
                ) VALUES (?, ?, ?, ?, ?, NULL, NULL)
                """,
                (session_id, user_id, token_hash, created, expires),
            )
            row = active_connection.execute(
                "SELECT * FROM auth_sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return dict(row)

    def get_active_by_token_hash(
        self,
        token_hash: str,
        *,
        now: datetime | str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        current = normalize_datetime(now)
        with self._connection(connection) as active_connection:
            row = active_connection.execute(
                """
                SELECT * FROM auth_sessions
                WHERE token_hash = ?
                  AND revoked_at IS NULL
                  AND expires_at > ?
                """,
                (token_hash, current),
            ).fetchone()
        return row_to_dict(row)

    def revoke_by_token_hash(
        self,
        token_hash: str,
        *,
        revoked_at: datetime | str,
        connection: sqlite3.Connection | None = None,
    ) -> bool:
        revoked = normalize_datetime(revoked_at)
        with self._connection(connection, write=True) as active_connection:
            cursor = active_connection.execute(
                """
                UPDATE auth_sessions
                SET revoked_at = ?
                WHERE token_hash = ? AND revoked_at IS NULL
                """,
                (revoked, token_hash),
            )
        return cursor.rowcount > 0

    def delete_expired(
        self,
        *,
        now: datetime | str,
        connection: sqlite3.Connection | None = None,
    ) -> int:
        current = normalize_datetime(now)
        with self._connection(connection, write=True) as active_connection:
            cursor = active_connection.execute(
                "DELETE FROM auth_sessions WHERE expires_at <= ?",
                (current,),
            )
        return cursor.rowcount

    def revoke_all_for_user(
        self,
        user_id: str,
        *,
        revoked_at: datetime | str,
        connection: sqlite3.Connection | None = None,
    ) -> int:
        revoked = normalize_datetime(revoked_at)
        with self._connection(connection, write=True) as active_connection:
            cursor = active_connection.execute(
                """
                UPDATE auth_sessions
                SET revoked_at = ?
                WHERE user_id = ? AND revoked_at IS NULL
                """,
                (revoked, user_id),
            )
        return cursor.rowcount
