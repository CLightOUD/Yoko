from __future__ import annotations

import sqlite3
from typing import Any, Literal
from uuid import uuid4

from backend.app.repositories._common import BaseRepository, row_to_dict, utc_now_iso


MessageRole = Literal["user", "assistant", "system"]


class MessageRepository(BaseRepository):
    def create(
        self,
        *,
        user_id: str,
        conversation_id: str,
        role: MessageRole,
        content: str,
        request_id: str | None = None,
        message_id: str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        message_id = message_id or str(uuid4())
        created_at = utc_now_iso()
        with self._connection(connection, write=True) as active_connection:
            active_connection.execute(
                """
                INSERT INTO messages (
                    id, user_id, conversation_id, role, content, request_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    user_id,
                    conversation_id,
                    role,
                    content,
                    request_id,
                    created_at,
                ),
            )
            row = active_connection.execute(
                "SELECT * FROM messages WHERE id = ?", (message_id,)
            ).fetchone()
        return dict(row)

    def get_for_user(
        self,
        message_id: str,
        user_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        with self._connection(connection) as active_connection:
            row = active_connection.execute(
                "SELECT * FROM messages WHERE id = ? AND user_id = ?",
                (message_id, user_id),
            ).fetchone()
        return row_to_dict(row)

    def conversation_belongs_to_user(
        self,
        conversation_id: str,
        user_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> bool:
        with self._connection(connection) as active_connection:
            row = active_connection.execute(
                """
                SELECT 1 FROM messages
                WHERE conversation_id = ? AND user_id = ?
                LIMIT 1
                """,
                (conversation_id, user_id),
            ).fetchone()
        return row is not None

    def list_for_request(
        self,
        *,
        user_id: str,
        request_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        with self._connection(connection) as active_connection:
            rows = active_connection.execute(
                """
                SELECT * FROM messages
                WHERE user_id = ? AND request_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (user_id, request_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_recent(
        self,
        *,
        user_id: str,
        conversation_id: str,
        limit: int = 20,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._connection(connection) as active_connection:
            rows = active_connection.execute(
                """
                SELECT * FROM (
                    SELECT * FROM messages
                    WHERE user_id = ? AND conversation_id = ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                )
                ORDER BY created_at ASC, id ASC
                """,
                (user_id, conversation_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]
