from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


DEFAULT_DATABASE_PATH = Path("backend/data/app.db")


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    timezone TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    request_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation
    ON messages(user_id, conversation_id, created_at, id);
CREATE INDEX IF NOT EXISTS idx_messages_request
    ON messages(user_id, request_id);

CREATE TABLE IF NOT EXISTS reminders (
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

CREATE INDEX IF NOT EXISTS idx_reminders_user_status_trigger
    ON reminders(user_id, status, next_trigger_at, id);

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    scope TEXT NOT NULL CHECK (scope IN ('global', 'task')),
    task_type TEXT NOT NULL CHECK (
        task_type IN ('global', 'medication', 'walking', 'appointment', 'other')
    ),
    memory_key TEXT NOT NULL,
    memory_value TEXT NOT NULL,
    display_text TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    source_message_id TEXT REFERENCES messages(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_used_at TEXT,
    CHECK (
        (scope = 'global' AND task_type = 'global') OR
        (scope = 'task' AND task_type <> 'global')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_memories_active_key
    ON memories(user_id, task_type, memory_key)
    WHERE active = 1;
CREATE INDEX IF NOT EXISTS idx_memories_user_active_task
    ON memories(user_id, active, task_type, updated_at DESC, id);

CREATE TABLE IF NOT EXISTS memory_events (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL REFERENCES memories(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    action TEXT NOT NULL,
    source_message_id TEXT REFERENCES messages(id),
    before_value TEXT,
    after_value TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memory_events_memory
    ON memory_events(memory_id, created_at, id);

CREATE TABLE IF NOT EXISTS request_metrics (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL REFERENCES users(id),
    model_call_count INTEGER NOT NULL CHECK (model_call_count >= 0),
    input_tokens INTEGER CHECK (input_tokens IS NULL OR input_tokens >= 0),
    output_tokens INTEGER CHECK (output_tokens IS NULL OR output_tokens >= 0),
    memory_tokens INTEGER NOT NULL CHECK (memory_tokens >= 0),
    retrieved_memory_count INTEGER NOT NULL CHECK (retrieved_memory_count >= 0),
    used_memory_count INTEGER NOT NULL CHECK (
        used_memory_count >= 0 AND used_memory_count <= retrieved_memory_count
    ),
    retrieval_ms INTEGER NOT NULL CHECK (retrieval_ms >= 0),
    model_ms INTEGER NOT NULL CHECK (model_ms >= 0),
    tool_ms INTEGER NOT NULL CHECK (tool_ms >= 0),
    total_ms INTEGER NOT NULL CHECK (
        total_ms >= 0 AND total_ms >= retrieval_ms + model_ms + tool_ms
    ),
    retrieved_memory_ids TEXT NOT NULL DEFAULT '[]',
    used_memory_ids TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    CHECK (input_tokens IS NULL OR memory_tokens <= input_tokens)
);

CREATE INDEX IF NOT EXISTS idx_request_metrics_user_created
    ON request_metrics(user_id, created_at, id);

CREATE TABLE IF NOT EXISTS feedbacks (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    request_id TEXT NOT NULL,
    feedback_message_id TEXT NOT NULL REFERENCES messages(id),
    feedback_text TEXT,
    corrected_reply TEXT,
    rating TEXT CHECK (rating IS NULL OR rating IN ('up', 'down')),
    dedup_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    CHECK (
        feedback_text IS NOT NULL OR corrected_reply IS NOT NULL OR rating IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_feedbacks_user_request
    ON feedbacks(user_id, request_id, created_at, id);
"""


class Database:
    """SQLite connection, schema initialization, and transaction boundary."""

    def __init__(self, path: str | Path | None = None) -> None:
        configured_path = path or os.getenv("DATABASE_PATH") or DEFAULT_DATABASE_PATH
        self.path = Path(configured_path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        from backend.app.repositories._common import utc_now_iso

        now = utc_now_iso()
        with self.transaction() as connection:
            connection.executescript(SCHEMA_SQL)
            connection.execute(
                """
                INSERT INTO users (id, display_name, timezone, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                ("demo-user", "用户", "Asia/Shanghai", now, now),
            )

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
