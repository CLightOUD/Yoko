from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.app.repositories._common import BaseRepository, row_to_dict, utc_now_iso


class ChatRequestRepository(BaseRepository):
    def get_for_user(
        self,
        *,
        request_id: str,
        user_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        with self._connection(connection) as active_connection:
            row = active_connection.execute(
                "SELECT * FROM chat_requests WHERE id = ? AND user_id = ?",
                (request_id, user_id),
            ).fetchone()
        return row_to_dict(row)

    def create(
        self,
        *,
        request_id: str,
        user_id: str,
        idempotency_key: str | None,
        request_hash: str,
        conversation_id: str,
        user_message_id: str,
        lease_seconds: int,
        connection: sqlite3.Connection,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        connection.execute(
            """
            INSERT INTO chat_requests (
                id, user_id, idempotency_key, request_hash, conversation_id,
                user_message_id, status, response_json, failure_code,
                attempt_count, lease_expires_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL, NULL, 1, ?, ?, ?)
            """,
            (
                request_id,
                user_id,
                idempotency_key,
                request_hash,
                conversation_id,
                user_message_id,
                (now + timedelta(seconds=lease_seconds)).isoformat(),
                now.isoformat(),
                now.isoformat(),
            ),
        )
        return dict(
            connection.execute(
                "SELECT * FROM chat_requests WHERE id = ?", (request_id,)
            ).fetchone()
        )

    def get_by_idempotency_key(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        with self._connection(connection) as active_connection:
            row = active_connection.execute(
                """
                SELECT * FROM chat_requests
                WHERE user_id = ? AND idempotency_key = ?
                """,
                (user_id, idempotency_key),
            ).fetchone()
        return row_to_dict(row)

    def reclaim(
        self,
        *,
        request_id: str,
        user_id: str,
        lease_seconds: int,
        connection: sqlite3.Connection,
    ) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        now_value = now.isoformat()
        cursor = connection.execute(
            """
            UPDATE chat_requests
            SET status = 'pending', response_json = NULL, failure_code = NULL,
                attempt_count = attempt_count + 1, lease_expires_at = ?,
                updated_at = ?
            WHERE id = ? AND user_id = ?
              AND (
                status = 'failed'
                OR (status = 'pending' AND lease_expires_at <= ?)
              )
            """,
            (
                (now + timedelta(seconds=lease_seconds)).isoformat(),
                now_value,
                request_id,
                user_id,
                now_value,
            ),
        )
        if cursor.rowcount != 1:
            return None
        row = connection.execute(
            "SELECT * FROM chat_requests WHERE id = ? AND user_id = ?",
            (request_id, user_id),
        ).fetchone()
        return row_to_dict(row)

    def complete(
        self,
        *,
        request_id: str,
        user_id: str,
        response_json: str,
        connection: sqlite3.Connection,
    ) -> bool:
        cursor = connection.execute(
            """
            UPDATE chat_requests
            SET status = 'completed', response_json = ?, failure_code = NULL,
                updated_at = ?
            WHERE id = ? AND user_id = ? AND status = 'pending'
            """,
            (response_json, utc_now_iso(), request_id, user_id),
        )
        return cursor.rowcount == 1

    def fail(
        self,
        *,
        request_id: str,
        user_id: str,
        failure_code: str,
        connection: sqlite3.Connection | None = None,
    ) -> bool:
        with self._connection(connection, write=True) as active_connection:
            cursor = active_connection.execute(
                """
                UPDATE chat_requests
                SET status = 'failed', response_json = NULL, failure_code = ?,
                    updated_at = ?
                WHERE id = ? AND user_id = ? AND status = 'pending'
                """,
                (failure_code[:64], utc_now_iso(), request_id, user_id),
            )
        return cursor.rowcount == 1
