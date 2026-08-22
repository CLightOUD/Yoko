from __future__ import annotations

import sqlite3
from typing import Any, Literal
from uuid import uuid4

from backend.app.repositories._common import (
    BaseRepository,
    apply_updates,
    encode_json,
    row_to_dict,
    utc_now_iso,
)


MemoryScope = Literal["global", "task"]
TaskType = Literal["global", "medication", "walking", "appointment", "other"]


class MemoryRepository(BaseRepository):
    def create(
        self,
        *,
        user_id: str,
        scope: MemoryScope,
        task_type: TaskType,
        memory_key: str,
        memory_value: str,
        display_text: str,
        source_message_id: str | None = None,
        memory_id: str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        memory_id = memory_id or str(uuid4())
        now = utc_now_iso()
        with self._connection(connection, write=True) as active_connection:
            active_connection.execute(
                """
                INSERT INTO memories (
                    id, user_id, scope, task_type, memory_key, memory_value,
                    display_text, active, source_message_id, created_at, updated_at,
                    last_used_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, NULL)
                """,
                (
                    memory_id,
                    user_id,
                    scope,
                    task_type,
                    memory_key,
                    memory_value,
                    display_text,
                    source_message_id,
                    now,
                    now,
                ),
            )
            row = active_connection.execute(
                "SELECT * FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()
        return self._convert_row(row)

    def get_for_user(
        self,
        memory_id: str,
        user_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        with self._connection(connection) as active_connection:
            row = active_connection.execute(
                "SELECT * FROM memories WHERE id = ? AND user_id = ?",
                (memory_id, user_id),
            ).fetchone()
        return self._convert_row(row)

    def find_active_by_key(
        self,
        *,
        user_id: str,
        task_type: TaskType,
        memory_key: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        with self._connection(connection) as active_connection:
            row = active_connection.execute(
                """
                SELECT * FROM memories
                WHERE user_id = ? AND task_type = ? AND memory_key = ? AND active = 1
                """,
                (user_id, task_type, memory_key),
            ).fetchone()
        return self._convert_row(row)

    def find_latest_by_key(
        self,
        *,
        user_id: str,
        task_type: TaskType,
        memory_key: str,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        with self._connection(connection) as active_connection:
            row = active_connection.execute(
                """
                SELECT * FROM memories
                WHERE user_id = ? AND task_type = ? AND memory_key = ?
                ORDER BY active DESC, updated_at DESC, id ASC
                LIMIT 1
                """,
                (user_id, task_type, memory_key),
            ).fetchone()
        return self._convert_row(row)

    def list(
        self,
        *,
        user_id: str,
        active: bool | None = True,
        task_type: TaskType | None = None,
        limit: int = 50,
        offset: int = 0,
        connection: sqlite3.Connection | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        if limit < 1 or offset < 0:
            raise ValueError("invalid pagination")
        conditions = ["user_id = ?"]
        parameters: list[Any] = [user_id]
        if active is not None:
            conditions.append("active = ?")
            parameters.append(int(active))
        if task_type is not None:
            conditions.append("task_type = ?")
            parameters.append(task_type)
        where = " AND ".join(conditions)
        with self._connection(connection) as active_connection:
            total = active_connection.execute(
                f"SELECT COUNT(*) FROM memories WHERE {where}", parameters
            ).fetchone()[0]
            rows = active_connection.execute(
                f"""
                SELECT * FROM memories WHERE {where}
                ORDER BY updated_at DESC, id ASC
                LIMIT ? OFFSET ?
                """,
                [*parameters, limit, offset],
            ).fetchall()
        return [self._convert_row(row) for row in rows], total

    def retrieve(
        self,
        *,
        user_id: str,
        task_type: TaskType,
        limit: int = 3,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 3:
            raise ValueError("memory retrieval limit must be between 1 and 3")
        with self._connection(connection) as active_connection:
            rows = active_connection.execute(
                """
                SELECT * FROM memories
                WHERE user_id = ? AND active = 1
                  AND (task_type = 'global' OR task_type = ?)
                ORDER BY
                    CASE WHEN task_type = ? THEN 0 ELSE 1 END,
                    updated_at DESC,
                    id ASC
                LIMIT ?
                """,
                (user_id, task_type, task_type, limit),
            ).fetchall()
        return [self._convert_row(row) for row in rows]

    def update(
        self,
        *,
        memory_id: str,
        user_id: str,
        updates: dict[str, Any],
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        allowed = {"memory_value", "display_text", "active", "source_message_id"}
        unexpected = set(updates) - allowed
        if unexpected:
            raise ValueError(f"unsupported memory fields: {sorted(unexpected)}")
        normalized = dict(updates)
        if "active" in normalized:
            normalized["active"] = int(normalized["active"])
        normalized["updated_at"] = utc_now_iso()
        with self._connection(connection, write=True) as active_connection:
            row = apply_updates(
                active_connection,
                table="memories",
                resource_id=memory_id,
                user_id=user_id,
                updates=normalized,
            )
        return self._convert_row(row)

    def mark_used(
        self,
        *,
        memory_ids: list[str],
        user_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> int:
        if not memory_ids:
            return 0
        placeholders = ",".join("?" for _ in memory_ids)
        with self._connection(connection, write=True) as active_connection:
            cursor = active_connection.execute(
                f"""
                UPDATE memories SET last_used_at = ?
                WHERE user_id = ? AND active = 1 AND id IN ({placeholders})
                """,
                (utc_now_iso(), user_id, *memory_ids),
            )
        return cursor.rowcount

    @staticmethod
    def _convert_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        result = row_to_dict(row)
        if result is not None:
            result["active"] = bool(result["active"])
        return result


class MemoryEventRepository(BaseRepository):
    def create(
        self,
        *,
        memory_id: str,
        user_id: str,
        action: str,
        before_value: Any,
        after_value: Any,
        source_message_id: str | None = None,
        event_id: str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        event_id = event_id or str(uuid4())
        created_at = utc_now_iso()
        with self._connection(connection, write=True) as active_connection:
            active_connection.execute(
                """
                INSERT INTO memory_events (
                    id, memory_id, user_id, action, source_message_id,
                    before_value, after_value, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    memory_id,
                    user_id,
                    action,
                    source_message_id,
                    None if before_value is None else encode_json(before_value),
                    None if after_value is None else encode_json(after_value),
                    created_at,
                ),
            )
            row = active_connection.execute(
                "SELECT * FROM memory_events WHERE id = ?", (event_id,)
            ).fetchone()
        return dict(row)

    def list_for_memory(
        self,
        *,
        memory_id: str,
        user_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        with self._connection(connection) as active_connection:
            rows = active_connection.execute(
                """
                SELECT * FROM memory_events
                WHERE memory_id = ? AND user_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (memory_id, user_id),
            ).fetchall()
        return [dict(row) for row in rows]
