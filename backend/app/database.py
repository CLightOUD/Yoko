from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from backend.app.config import default_timezone


DEFAULT_DATABASE_PATH = Path("backend/data/app.db")
LATEST_SCHEMA_VERSION = 5


MIGRATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""


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
    image_sha256 TEXT CHECK (
        image_sha256 IS NULL OR length(image_sha256) = 64
    ),
    vision_observation TEXT,
    vision_confidence REAL CHECK (
        vision_confidence IS NULL OR
        (vision_confidence >= 0 AND vision_confidence <= 1)
    ),
    vision_model_ms INTEGER CHECK (
        vision_model_ms IS NULL OR vision_model_ms >= 0
    ),
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
    repeat_type TEXT NOT NULL CHECK (repeat_type IN ('none', 'daily', 'weekly')),
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


CHAT_REQUESTS_SQL = """
CREATE TABLE chat_requests (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    idempotency_key TEXT,
    request_hash TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    user_message_id TEXT NOT NULL REFERENCES messages(id),
    status TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'failed')),
    response_json TEXT,
    failure_code TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 1 CHECK (attempt_count >= 1),
    lease_expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (status <> 'completed' OR response_json IS NOT NULL)
);

CREATE UNIQUE INDEX uq_chat_requests_idempotency
    ON chat_requests(user_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
CREATE INDEX idx_chat_requests_status_lease
    ON chat_requests(status, lease_expires_at, id);
"""


AUTH_SESSIONS_SQL = """
CREATE TABLE auth_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    token_hash TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT,
    revoked_at TEXT
);

CREATE INDEX idx_auth_sessions_user_expires
    ON auth_sessions(user_id, expires_at);
CREATE INDEX idx_auth_sessions_expires_revoked
    ON auth_sessions(expires_at, revoked_at);
"""


PUSH_DELIVERY_SQL = """
CREATE TABLE push_subscriptions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    endpoint TEXT NOT NULL,
    endpoint_hash TEXT NOT NULL UNIQUE,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    failure_count INTEGER NOT NULL DEFAULT 0 CHECK (failure_count >= 0),
    last_success_at TEXT,
    disabled_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_push_subscriptions_user_active
    ON push_subscriptions(user_id, disabled_at, updated_at);

CREATE TABLE reminder_deliveries (
    id TEXT PRIMARY KEY,
    reminder_id TEXT NOT NULL REFERENCES reminders(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    subscription_id TEXT NOT NULL REFERENCES push_subscriptions(id),
    trigger_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'sent', 'failed')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    lease_expires_at TEXT NOT NULL,
    next_attempt_at TEXT NOT NULL,
    last_error_code TEXT,
    sent_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(reminder_id, trigger_at, subscription_id)
);

CREATE INDEX idx_reminder_deliveries_claim
    ON reminder_deliveries(status, next_attempt_at, lease_expires_at, id);
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
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    def initialize(self) -> None:
        from backend.app.repositories._common import utc_now_iso

        now = utc_now_iso()
        self._backup_before_legacy_migration()
        with self.transaction(immediate=True) as connection:
            connection.execute(MIGRATION_TABLE_SQL)
            applied = {
                row["version"]
                for row in connection.execute(
                    "SELECT version FROM schema_migrations"
                ).fetchall()
            }
            unsupported = sorted(
                version for version in applied if version > LATEST_SCHEMA_VERSION
            )
            if unsupported:
                raise RuntimeError(
                    f"database schema is newer than this application: {unsupported}"
                )
            migrations = (
                (1, "baseline_schema", self._migration_baseline),
                (2, "chat_request_idempotency", self._migration_chat_requests),
                (3, "account_authentication", self._migration_account_authentication),
                (4, "message_vision_metadata", self._migration_message_vision_metadata),
                (5, "web_push_delivery", self._migration_web_push_delivery),
            )
            for version, name, migration in migrations:
                if version in applied:
                    continue
                migration(connection, now)
                connection.execute(
                    """
                    INSERT INTO schema_migrations (version, name, applied_at)
                    VALUES (?, ?, ?)
                    """,
                    (version, name, now),
                )

    def schema_version(self) -> int:
        with self.connection() as connection:
            return self._schema_version(connection)

    def check_readiness(self) -> int:
        with self.connection() as connection:
            connection.execute("SELECT 1").fetchone()
            version = self._schema_version(connection)
            if version != LATEST_SCHEMA_VERSION:
                raise RuntimeError(
                    f"database schema version {version} does not match "
                    f"{LATEST_SCHEMA_VERSION}"
                )
            missing = connection.execute(
                """
                SELECT name FROM (
                    SELECT 'users' AS name
                    UNION ALL SELECT 'messages'
                    UNION ALL SELECT 'reminders'
                    UNION ALL SELECT 'memories'
                    UNION ALL SELECT 'memory_events'
                    UNION ALL SELECT 'feedbacks'
                    UNION ALL SELECT 'request_metrics'
                    UNION ALL SELECT 'chat_requests'
                    UNION ALL SELECT 'auth_sessions'
                    UNION ALL SELECT 'push_subscriptions'
                    UNION ALL SELECT 'reminder_deliveries'
                ) expected
                WHERE name NOT IN (
                    SELECT name FROM sqlite_master WHERE type = 'table'
                )
                LIMIT 1
                """
            ).fetchone()
            if missing is not None:
                raise RuntimeError(f"required table is missing: {missing['name']}")
        return version

    def backup_to(self, destination: str | Path) -> Path:
        target = Path(destination)
        if target.exists():
            raise FileExistsError(f"backup destination already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(f"{target.suffix}.partial")
        if partial.exists():
            raise FileExistsError(f"partial backup already exists: {partial}")
        try:
            with self.connection() as source, closing(
                sqlite3.connect(partial)
            ) as backup:
                source.backup(backup)
            partial.replace(target)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        return target

    @staticmethod
    def _schema_version(connection: sqlite3.Connection) -> int:
        table = connection.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'schema_migrations'
            """
        ).fetchone()
        if table is None:
            return 0
        row = connection.execute(
            "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
        ).fetchone()
        return int(row["version"])

    def _migration_baseline(
        self,
        connection: sqlite3.Connection,
        applied_at: str,
    ) -> None:
        self._execute_script(connection, SCHEMA_SQL)
        self._migrate_reminders_for_weekly(connection)
        self._consolidate_duplicate_reminders(connection, updated_at=applied_at)
        self._remove_covered_reminders(connection, updated_at=applied_at)
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_reminders_active_schedule
            ON reminders(user_id, next_trigger_at, timezone, repeat_type)
            WHERE status = 'active'
            """
        )
        connection.execute(
            """
            INSERT INTO users (id, display_name, timezone, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            ("demo-user", "用户", default_timezone(), applied_at, applied_at),
        )

    @staticmethod
    def _migration_chat_requests(
        connection: sqlite3.Connection,
        applied_at: str,
    ) -> None:
        del applied_at
        Database._execute_script(connection, CHAT_REQUESTS_SQL)

    @staticmethod
    def _migration_account_authentication(
        connection: sqlite3.Connection,
        applied_at: str,
    ) -> None:
        del applied_at
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(users)").fetchall()
        }
        additions = (
            ("username", "TEXT"),
            ("username_normalized", "TEXT"),
            ("password_hash", "TEXT"),
            ("disabled", "INTEGER NOT NULL DEFAULT 0"),
            ("last_login_at", "TEXT"),
            ("failed_login_count", "INTEGER NOT NULL DEFAULT 0"),
            ("login_blocked_until", "TEXT"),
        )
        for column, definition in additions:
            if column not in columns:
                connection.execute(
                    f"ALTER TABLE users ADD COLUMN {column} {definition}"
                )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username_normalized
            ON users(username_normalized)
            WHERE username_normalized IS NOT NULL
            """
        )
        Database._execute_script(connection, AUTH_SESSIONS_SQL)

    @staticmethod
    def _migration_message_vision_metadata(
        connection: sqlite3.Connection,
        applied_at: str,
    ) -> None:
        del applied_at
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(messages)").fetchall()
        }
        additions = (
            (
                "image_sha256",
                "TEXT CHECK (image_sha256 IS NULL OR length(image_sha256) = 64)",
            ),
            ("vision_observation", "TEXT"),
            (
                "vision_confidence",
                "REAL CHECK (vision_confidence IS NULL OR "
                "(vision_confidence >= 0 AND vision_confidence <= 1))",
            ),
            (
                "vision_model_ms",
                "INTEGER CHECK (vision_model_ms IS NULL OR vision_model_ms >= 0)",
            ),
        )
        for column, definition in additions:
            if column not in columns:
                connection.execute(
                    f"ALTER TABLE messages ADD COLUMN {column} {definition}"
                )

    @staticmethod
    def _migration_web_push_delivery(
        connection: sqlite3.Connection,
        applied_at: str,
    ) -> None:
        del applied_at
        Database._execute_script(connection, PUSH_DELIVERY_SQL)

    @staticmethod
    def _execute_script(connection: sqlite3.Connection, script: str) -> None:
        """Execute a SQL script without sqlite3.executescript's implicit commit."""
        statement = ""
        for line in script.splitlines():
            statement += f"{line}\n"
            if not sqlite3.complete_statement(statement):
                continue
            sql = statement.strip()
            if sql:
                connection.execute(sql)
            statement = ""
        if statement.strip():
            raise sqlite3.OperationalError("incomplete migration SQL statement")

    def _backup_before_legacy_migration(self) -> None:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return
        with self.connection() as connection:
            table = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'schema_migrations'
                """
            ).fetchone()
            if table is not None:
                return
            backup_path = self.path.with_name(
                f"{self.path.stem}.pre-migration-v1.bak"
            )
            if backup_path.exists():
                return
            with sqlite3.connect(backup_path) as backup:
                connection.backup(backup)

    @staticmethod
    def _migrate_reminders_for_weekly(connection: sqlite3.Connection) -> None:
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'reminders'"
        ).fetchone()
        if row is None or "'weekly'" in row["sql"]:
            return

        connection.execute("ALTER TABLE reminders RENAME TO reminders_legacy")
        connection.execute(
            """
            CREATE TABLE reminders (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id),
                title TEXT NOT NULL,
                next_trigger_at TEXT NOT NULL,
                timezone TEXT NOT NULL,
                repeat_type TEXT NOT NULL CHECK (
                    repeat_type IN ('none', 'daily', 'weekly')
                ),
                status TEXT NOT NULL CHECK (
                    status IN ('active', 'completed', 'deleted')
                ),
                last_triggered_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO reminders (
                id, user_id, title, next_trigger_at, timezone, repeat_type,
                status, last_triggered_at, created_at, updated_at
            )
            SELECT
                id, user_id, title, next_trigger_at, timezone, repeat_type,
                status, last_triggered_at, created_at, updated_at
            FROM reminders_legacy
            """
        )
        connection.execute("DROP TABLE reminders_legacy")
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_reminders_user_status_trigger
            ON reminders(user_id, status, next_trigger_at, id)
            """
        )

    @staticmethod
    def _consolidate_duplicate_reminders(
        connection: sqlite3.Connection,
        *,
        updated_at: str,
    ) -> None:
        groups = connection.execute(
            """
            SELECT user_id, next_trigger_at, timezone, repeat_type
            FROM reminders
            WHERE status = 'active'
            GROUP BY user_id, next_trigger_at, timezone, repeat_type
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        for group in groups:
            rows = connection.execute(
                """
                SELECT id, title FROM reminders
                WHERE user_id = ? AND next_trigger_at = ? AND timezone = ?
                  AND repeat_type = ? AND status = 'active'
                ORDER BY created_at ASC, id ASC
                """,
                tuple(group),
            ).fetchall()
            titles: list[str] = []
            for reminder in rows:
                for item in reminder["title"].split("；"):
                    normalized = item.strip()
                    if normalized and normalized not in titles:
                        titles.append(normalized)
            canonical_id = rows[0]["id"]
            duplicate_ids = [row["id"] for row in rows[1:]]
            connection.execute(
                "UPDATE reminders SET title = ?, updated_at = ? WHERE id = ?",
                ("；".join(titles), updated_at, canonical_id),
            )
            connection.executemany(
                """
                UPDATE reminders SET status = 'deleted', updated_at = ?
                WHERE id = ?
                """,
                [(updated_at, reminder_id) for reminder_id in duplicate_ids],
            )

    @staticmethod
    def _remove_covered_reminders(
        connection: sqlite3.Connection,
        *,
        updated_at: str,
    ) -> None:
        rows = connection.execute(
            """
            SELECT id, user_id, title, next_trigger_at, timezone, repeat_type,
                   created_at
            FROM reminders
            WHERE status = 'active'
            ORDER BY created_at ASC, id ASC
            """
        ).fetchall()
        groups: dict[tuple[str, str, str, str], list[sqlite3.Row]] = {}
        for reminder in rows:
            normalized_title = "；".join(
                " ".join(item.split()).casefold()
                for item in reminder["title"].split("；")
                if item.strip()
            )
            key = (
                reminder["user_id"],
                reminder["next_trigger_at"],
                reminder["timezone"],
                normalized_title,
            )
            groups.setdefault(key, []).append(reminder)

        priority = {"none": 1, "weekly": 2, "daily": 3}
        for reminders in groups.values():
            repeat_types = {reminder["repeat_type"] for reminder in reminders}
            if len(repeat_types) < 2:
                continue
            strongest = min(
                reminders,
                key=lambda reminder: (
                    -priority[reminder["repeat_type"]],
                    reminder["created_at"],
                    reminder["id"],
                ),
            )
            connection.executemany(
                """
                UPDATE reminders SET status = 'deleted', updated_at = ?
                WHERE id = ?
                """,
                [
                    (updated_at, reminder["id"])
                    for reminder in reminders
                    if reminder["id"] != strongest["id"]
                ],
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
