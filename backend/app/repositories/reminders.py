from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from backend.app.repositories._common import (
    BaseRepository,
    apply_updates,
    normalize_datetime,
    row_to_dict,
    utc_now_iso,
)


ReminderStatus = Literal["active", "completed", "deleted"]
ReminderListStatus = Literal["active", "completed", "deleted", "all"]


class ReminderRepository(BaseRepository):
    def create(
        self,
        *,
        user_id: str,
        title: str,
        next_trigger_at: datetime | str,
        timezone: str,
        repeat_type: Literal["none", "daily", "weekly"],
        reminder_id: str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        reminder_id = reminder_id or str(uuid4())
        now = utc_now_iso()
        trigger_at = normalize_datetime(next_trigger_at)
        with self._connection(connection, write=True) as active_connection:
            active_connection.execute(
                """
                INSERT INTO reminders (
                    id, user_id, title, next_trigger_at, timezone, repeat_type,
                    status, last_triggered_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', NULL, ?, ?)
                """,
                (
                    reminder_id,
                    user_id,
                    title,
                    trigger_at,
                    timezone,
                    repeat_type,
                    now,
                    now,
                ),
            )
            row = active_connection.execute(
                "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
            ).fetchone()
        return dict(row)

    def get_for_user(
        self,
        reminder_id: str,
        user_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        with self._connection(connection) as active_connection:
            row = active_connection.execute(
                "SELECT * FROM reminders WHERE id = ? AND user_id = ?",
                (reminder_id, user_id),
            ).fetchone()
        return row_to_dict(row)

    def list_active_for_schedule(
        self,
        *,
        user_id: str,
        next_trigger_at: datetime | str,
        timezone: str,
        repeat_type: Literal["none", "daily", "weekly"],
        exclude_id: str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        trigger_at = normalize_datetime(next_trigger_at)
        parameters: list[Any] = [
            user_id,
            trigger_at,
            timezone,
            repeat_type,
        ]
        exclude_clause = ""
        if exclude_id is not None:
            exclude_clause = " AND id <> ?"
            parameters.append(exclude_id)
        with self._connection(connection) as active_connection:
            rows = active_connection.execute(
                f"""
                SELECT * FROM reminders
                WHERE user_id = ? AND next_trigger_at = ? AND timezone = ?
                  AND repeat_type = ? AND status = 'active'{exclude_clause}
                ORDER BY created_at ASC, id ASC
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def list_active_at_time(
        self,
        *,
        user_id: str,
        next_trigger_at: datetime | str,
        timezone: str,
        exclude_id: str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        trigger_at = normalize_datetime(next_trigger_at)
        parameters: list[Any] = [user_id, trigger_at, timezone]
        exclude_clause = ""
        if exclude_id is not None:
            exclude_clause = " AND id <> ?"
            parameters.append(exclude_id)
        with self._connection(connection) as active_connection:
            rows = active_connection.execute(
                f"""
                SELECT * FROM reminders
                WHERE user_id = ? AND next_trigger_at = ? AND timezone = ?
                  AND status = 'active'{exclude_clause}
                ORDER BY created_at ASC, id ASC
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def list(
        self,
        *,
        user_id: str,
        status: ReminderListStatus = "active",
        limit: int = 50,
        offset: int = 0,
        connection: sqlite3.Connection | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        if limit < 1 or offset < 0:
            raise ValueError("invalid pagination")
        status_clause = "" if status == "all" else " AND status = ?"
        parameters: list[Any] = [user_id]
        if status != "all":
            parameters.append(status)
        with self._connection(connection) as active_connection:
            total = active_connection.execute(
                f"SELECT COUNT(*) FROM reminders WHERE user_id = ?{status_clause}",
                parameters,
            ).fetchone()[0]
            rows = active_connection.execute(
                f"""
                SELECT * FROM reminders
                WHERE user_id = ?{status_clause}
                ORDER BY next_trigger_at ASC, id ASC
                LIMIT ? OFFSET ?
                """,
                [*parameters, limit, offset],
            ).fetchall()
        return [dict(row) for row in rows], total

    def list_due(
        self,
        *,
        user_id: str,
        due_at: datetime | str,
        limit: int = 20,
        connection: sqlite3.Connection | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        if limit < 1:
            raise ValueError("limit must be positive")
        due_at_value = normalize_datetime(due_at)
        parameters = (user_id, due_at_value)
        with self._connection(connection) as active_connection:
            total = active_connection.execute(
                """
                SELECT COUNT(*) FROM reminders
                WHERE user_id = ? AND status = 'active' AND next_trigger_at <= ?
                """,
                parameters,
            ).fetchone()[0]
            rows = active_connection.execute(
                """
                SELECT * FROM reminders
                WHERE user_id = ? AND status = 'active' AND next_trigger_at <= ?
                ORDER BY next_trigger_at ASC, id ASC
                LIMIT ?
                """,
                (*parameters, limit),
            ).fetchall()
        return [dict(row) for row in rows], total

    def update(
        self,
        *,
        reminder_id: str,
        user_id: str,
        updates: dict[str, Any],
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        allowed = {"title", "next_trigger_at", "timezone", "repeat_type", "status"}
        unexpected = set(updates) - allowed
        if unexpected:
            raise ValueError(f"unsupported reminder fields: {sorted(unexpected)}")
        normalized = dict(updates)
        if "next_trigger_at" in normalized:
            normalized["next_trigger_at"] = normalize_datetime(
                normalized["next_trigger_at"]
            )
        normalized["updated_at"] = utc_now_iso()
        with self._connection(connection, write=True) as active_connection:
            row = apply_updates(
                active_connection,
                table="reminders",
                resource_id=reminder_id,
                user_id=user_id,
                updates=normalized,
            )
        return row_to_dict(row)

    def set_acknowledged(
        self,
        *,
        reminder_id: str,
        user_id: str,
        last_triggered_at: datetime | str,
        next_trigger_at: datetime | str,
        status: ReminderStatus,
        connection: sqlite3.Connection,
    ) -> dict[str, Any] | None:
        row = apply_updates(
            connection,
            table="reminders",
            resource_id=reminder_id,
            user_id=user_id,
            updates={
                "last_triggered_at": normalize_datetime(last_triggered_at),
                "next_trigger_at": normalize_datetime(next_trigger_at),
                "status": status,
                "updated_at": utc_now_iso(),
            },
        )
        return row_to_dict(row)

    def soft_delete(
        self,
        *,
        reminder_id: str,
        user_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> bool:
        with self._connection(connection, write=True) as active_connection:
            row = active_connection.execute(
                "SELECT status FROM reminders WHERE id = ? AND user_id = ?",
                (reminder_id, user_id),
            ).fetchone()
            if row is None:
                return False
            if row["status"] != "deleted":
                active_connection.execute(
                    """
                    UPDATE reminders SET status = 'deleted', updated_at = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (utc_now_iso(), reminder_id, user_id),
                )
        return True
