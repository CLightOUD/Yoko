from __future__ import annotations

import sqlite3
from typing import Any, Literal
from uuid import uuid4

from backend.app.repositories._common import BaseRepository, row_to_dict, utc_now_iso


class FeedbackRepository(BaseRepository):
    def create(
        self,
        *,
        user_id: str,
        request_id: str,
        feedback_message_id: str,
        dedup_key: str,
        feedback_text: str | None = None,
        corrected_reply: str | None = None,
        rating: Literal["up", "down"] | None = None,
        feedback_id: str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        feedback_id = feedback_id or str(uuid4())
        created_at = utc_now_iso()
        with self._connection(connection, write=True) as active_connection:
            active_connection.execute(
                """
                INSERT INTO feedbacks (
                    id, user_id, request_id, feedback_message_id, feedback_text,
                    corrected_reply, rating, dedup_key, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback_id,
                    user_id,
                    request_id,
                    feedback_message_id,
                    feedback_text,
                    corrected_reply,
                    rating,
                    dedup_key,
                    created_at,
                ),
            )
            row = active_connection.execute(
                "SELECT * FROM feedbacks WHERE id = ?", (feedback_id,)
            ).fetchone()
        return dict(row)

    def get_by_dedup_key(
        self,
        dedup_key: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        with self._connection(connection) as active_connection:
            row = active_connection.execute(
                "SELECT * FROM feedbacks WHERE dedup_key = ?", (dedup_key,)
            ).fetchone()
        return row_to_dict(row)
