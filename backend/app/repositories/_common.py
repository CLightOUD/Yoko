from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from backend.app.database import Database


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def normalize_datetime(value: datetime | str) -> str:
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
    else:
        parsed = value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("datetime must include timezone information")
    return parsed.astimezone(UTC).isoformat()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def encode_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def decode_json(value: str) -> Any:
    return json.loads(value)


class BaseRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @contextmanager
    def _connection(
        self,
        connection: sqlite3.Connection | None,
        *,
        write: bool = False,
    ) -> Iterator[sqlite3.Connection]:
        if connection is not None:
            yield connection
            return
        manager = self.database.transaction() if write else self.database.connection()
        with manager as managed_connection:
            yield managed_connection


def apply_updates(
    connection: sqlite3.Connection,
    *,
    table: str,
    resource_id: str,
    user_id: str,
    updates: Mapping[str, Any],
) -> sqlite3.Row | None:
    if not updates:
        raise ValueError("updates cannot be empty")
    assignments = ", ".join(f"{column} = ?" for column in updates)
    values = [*updates.values(), resource_id, user_id]
    connection.execute(
        f"UPDATE {table} SET {assignments} WHERE id = ? AND user_id = ?",
        values,
    )
    return connection.execute(
        f"SELECT * FROM {table} WHERE id = ? AND user_id = ?",
        (resource_id, user_id),
    ).fetchone()
