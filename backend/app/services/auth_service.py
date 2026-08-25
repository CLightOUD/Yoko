from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from pwdlib import PasswordHash

from backend.app.database import Database
from backend.app.repositories import AuthSessionRepository, UserRepository
from backend.app.schemas.auth import (
    AccountDeleteRequest,
    AccountDeleteResponse,
    AccountExportResponse,
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    UserView,
)
from backend.app.services.errors import (
    AuthenticationRequiredError,
    InvalidCredentialsError,
    InvalidRequestError,
    ResourceNotFoundError,
    UsernameAlreadyExistsError,
)


@dataclass(frozen=True, slots=True, repr=False)
class IssuedSession:
    """An authenticated response plus the raw token used only for Set-Cookie."""

    token: str
    response: AuthResponse


class AuthService:
    """Registration, password verification, and opaque server-side sessions."""

    MAX_FAILED_LOGINS = 5
    BLOCK_DURATION = timedelta(minutes=15)

    def __init__(self, database: Database) -> None:
        self.database = database
        self.users = UserRepository(database)
        self.sessions = AuthSessionRepository(database)
        self.password_hash = PasswordHash.recommended()
        self._dummy_password_hash = self.password_hash.hash(
            secrets.token_urlsafe(32)
        )

    def register(self, request: RegisterRequest) -> IssuedSession:
        now = self._utc_now()
        username = request.username.strip()
        normalized = self._normalize_username(username)
        encoded_password = self.password_hash.hash(
            request.password.get_secret_value()
        )
        try:
            with self.database.transaction(immediate=True) as connection:
                if self.users.get_by_normalized_username(
                    normalized, connection=connection
                ) is not None:
                    raise UsernameAlreadyExistsError("用户名已存在")
                user = self.users.create_account(
                    user_id=str(uuid4()),
                    username=username,
                    username_normalized=normalized,
                    password_hash=encoded_password,
                    display_name=request.display_name,
                    timezone=request.timezone,
                    connection=connection,
                )
                return self._issue_session(user, now=now, connection=connection)
        except sqlite3.IntegrityError as exc:
            raise UsernameAlreadyExistsError("用户名已存在") from exc

    def login(self, request: LoginRequest) -> IssuedSession:
        now = self._utc_now()
        normalized = self._normalize_username(request.username)
        password = request.password.get_secret_value()
        failure: Exception | None = None
        issued: IssuedSession | None = None

        with self.database.transaction(immediate=True) as connection:
            user = self.users.get_by_normalized_username(
                normalized, connection=connection
            )
            if user is None:
                self._verify_password(password, self._dummy_password_hash)
                failure = InvalidCredentialsError("用户名或密码错误")
            else:
                password_matches = self._verify_password(
                    password,
                    user["password_hash"] or self._dummy_password_hash,
                )
                blocked_until = self._parse_datetime(user["login_blocked_until"])
                if blocked_until is not None and now < blocked_until:
                    failure = InvalidCredentialsError("用户名或密码错误")
                else:
                    if (
                        bool(user["disabled"])
                        or user["password_hash"] is None
                        or not password_matches
                    ):
                        prior_failures = (
                            0
                            if blocked_until is not None and now >= blocked_until
                            else int(user["failed_login_count"])
                        )
                        failures = prior_failures + 1
                        next_block = (
                            now + self.BLOCK_DURATION
                            if failures >= self.MAX_FAILED_LOGINS
                            else None
                        )
                        self.users.update_login_state(
                            user["id"],
                            failed_login_count=failures,
                            login_blocked_until=(
                                next_block.isoformat() if next_block else None
                            ),
                            connection=connection,
                        )
                        failure = InvalidCredentialsError("用户名或密码错误")
                    else:
                        user = self.users.update_login_state(
                            user["id"],
                            failed_login_count=0,
                            login_blocked_until=None,
                            last_login_at=now.isoformat(),
                            connection=connection,
                        )
                        issued = self._issue_session(
                            user, now=now, connection=connection
                        )

        if failure is not None:
            raise failure
        if issued is None:
            raise RuntimeError("login completed without a result")
        return issued

    def resolve_session(self, session_token: str | None) -> AuthResponse:
        if not session_token:
            raise AuthenticationRequiredError("请先登录")
        now = self._utc_now()
        token_hash = self._hash_token(session_token)
        with self.database.connection() as connection:
            session = self.sessions.get_active_by_token_hash(
                token_hash, now=now, connection=connection
            )
            if session is None:
                raise AuthenticationRequiredError("请先登录")
            user = self.users.get(session["user_id"], connection=connection)
        if (
            user is None
            or bool(user["disabled"])
            or user["username"] is None
        ):
            raise AuthenticationRequiredError("请先登录")
        return self._response(user, expires_at=session["expires_at"])

    def logout(self, session_token: str | None) -> None:
        if not session_token:
            return
        self.sessions.revoke_by_token_hash(
            self._hash_token(session_token), revoked_at=self._utc_now()
        )

    def change_password(
        self,
        user_id: str,
        request: ChangePasswordRequest,
    ) -> IssuedSession:
        now = self._utc_now()
        current_password = request.current_password.get_secret_value()
        new_password = request.new_password.get_secret_value()
        with self.database.transaction(immediate=True) as connection:
            user = self.users.get(user_id, connection=connection)
            if (
                user is None
                or user["password_hash"] is None
                or not self._verify_password(current_password, user["password_hash"])
            ):
                raise InvalidCredentialsError("用户名或密码错误")
            if self._verify_password(new_password, user["password_hash"]):
                raise InvalidRequestError("新密码不能与当前密码相同")
            updated = self.users.update_password(
                user_id,
                password_hash=self.password_hash.hash(new_password),
                connection=connection,
            )
            self.sessions.revoke_all_for_user(
                user_id,
                revoked_at=now,
                connection=connection,
            )
            return self._issue_session(updated, now=now, connection=connection)

    def export_account(self, user_id: str) -> AccountExportResponse:
        with self.database.transaction() as connection:
            user = self.users.get(user_id, connection=connection)
            if user is None or user["username"] is None:
                raise ResourceNotFoundError("用户不存在")

            def rows(sql: str) -> list[dict]:
                return [dict(row) for row in connection.execute(sql, (user_id,))]

            account = {
                key: user[key]
                for key in (
                    "id",
                    "username",
                    "display_name",
                    "timezone",
                    "created_at",
                    "updated_at",
                    "last_login_at",
                )
            }
            messages = rows(
                """
                SELECT id, conversation_id, role, content, request_id, created_at
                FROM messages WHERE user_id = ? ORDER BY created_at, id
                """
            )
            reminders = rows(
                """
                SELECT id, title, next_trigger_at, timezone, repeat_type, status,
                       last_triggered_at, created_at, updated_at
                FROM reminders WHERE user_id = ? ORDER BY created_at, id
                """
            )
            memories = rows(
                """
                SELECT id, scope, task_type, memory_key, memory_value,
                       display_text, active, source_message_id, created_at,
                       updated_at, last_used_at
                FROM memories WHERE user_id = ? ORDER BY created_at, id
                """
            )
            memory_events = rows(
                """
                SELECT id, memory_id, action, source_message_id, before_value,
                       after_value, created_at
                FROM memory_events WHERE user_id = ? ORDER BY created_at, id
                """
            )
            request_metrics = rows(
                """
                SELECT id, request_id, model_call_count, input_tokens,
                       output_tokens, memory_tokens, retrieved_memory_count,
                       used_memory_count, retrieval_ms, model_ms, tool_ms,
                       total_ms, retrieved_memory_ids, used_memory_ids, created_at
                FROM request_metrics WHERE user_id = ? ORDER BY created_at, id
                """
            )
            feedbacks = rows(
                """
                SELECT id, request_id, feedback_message_id, feedback_text,
                       corrected_reply, rating, created_at
                FROM feedbacks WHERE user_id = ? ORDER BY created_at, id
                """
            )
        return AccountExportResponse(
            exported_at=self._utc_now(),
            account=account,
            messages=messages,
            reminders=reminders,
            memories=memories,
            memory_events=memory_events,
            request_metrics=request_metrics,
            feedbacks=feedbacks,
        )

    def delete_account(
        self,
        user_id: str,
        request: AccountDeleteRequest,
    ) -> AccountDeleteResponse:
        password = request.password.get_secret_value()
        with self.database.transaction(immediate=True) as connection:
            user = self.users.get(user_id, connection=connection)
            if (
                user is None
                or user["password_hash"] is None
                or not self._verify_password(password, user["password_hash"])
            ):
                raise InvalidCredentialsError("用户名或密码错误")
            for table in (
                "feedbacks",
                "memory_events",
                "memories",
                "request_metrics",
                "chat_requests",
                "reminders",
                "auth_sessions",
                "messages",
            ):
                connection.execute(
                    f"DELETE FROM {table} WHERE user_id = ?",
                    (user_id,),
                )
            deleted = connection.execute(
                "DELETE FROM users WHERE id = ?",
                (user_id,),
            )
            if deleted.rowcount != 1:
                raise ResourceNotFoundError("用户不存在")
        return AccountDeleteResponse(deleted=True)

    def _issue_session(
        self,
        user: dict,
        *,
        now: datetime,
        connection: sqlite3.Connection,
    ) -> IssuedSession:
        token = secrets.token_urlsafe(32)
        expires_at = now + timedelta(days=self._session_ttl_days())
        self.sessions.delete_expired(now=now, connection=connection)
        self.sessions.create(
            session_id=str(uuid4()),
            user_id=user["id"],
            token_hash=self._hash_token(token),
            created_at=now,
            expires_at=expires_at,
            connection=connection,
        )
        return IssuedSession(
            token=token,
            response=self._response(user, expires_at=expires_at),
        )

    @staticmethod
    def _response(user: dict, *, expires_at: datetime | str) -> AuthResponse:
        parsed_expiry = (
            datetime.fromisoformat(expires_at)
            if isinstance(expires_at, str)
            else expires_at
        )
        return AuthResponse(
            user=UserView(
                id=UUID(user["id"]),
                username=user["username"],
                display_name=user["display_name"],
                timezone=user["timezone"],
            ),
            session_expires_at=parsed_expiry,
        )

    def _verify_password(self, password: str, encoded: str) -> bool:
        try:
            return self.password_hash.verify(password, encoded)
        except Exception:
            return False

    @staticmethod
    def _normalize_username(username: str) -> str:
        return username.strip().casefold()

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) if value is not None else None

    @staticmethod
    def _session_ttl_days() -> int:
        value = int(os.getenv("SESSION_TTL_DAYS", "180"))
        if value <= 0:
            raise RuntimeError("SESSION_TTL_DAYS must be positive")
        return value

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(UTC)
