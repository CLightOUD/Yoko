from __future__ import annotations

import hashlib
import os
from collections import deque
from dataclasses import dataclass
from threading import Lock
from time import monotonic


@dataclass(frozen=True)
class RateLimitDecision:
    limit: int
    retry_after: int


class RequestRateLimiter:
    """Small single-process limiter for the current SQLite deployment model."""

    def __init__(self) -> None:
        self.enabled = self._env_flag("RATE_LIMIT_ENABLED", default=True)
        self.general_per_minute = self._positive_int(
            "RATE_LIMIT_GENERAL_PER_MINUTE", 300
        )
        self.auth_per_minute = self._positive_int(
            "RATE_LIMIT_AUTH_PER_MINUTE", 30
        )
        self.chat_per_minute = self._positive_int(
            "RATE_LIMIT_CHAT_PER_MINUTE", 12
        )
        self.chat_per_hour = self._positive_int(
            "RATE_LIMIT_CHAT_PER_HOUR", 120
        )
        self._buckets: dict[tuple[str, str], deque[float]] = {}
        self._lock = Lock()
        self._checks = 0

    def check(
        self,
        *,
        path: str,
        method: str,
        client_host: str,
        session_token: str | None,
    ) -> RateLimitDecision | None:
        if not self.enabled or not path.startswith("/api/"):
            return None
        if path in {"/api/health", "/api/ready"}:
            return None

        now = monotonic()
        identity = self._session_identity(session_token) or client_host or "unknown"
        limits = [
            ("general-minute", client_host or "unknown", 60, self.general_per_minute)
        ]
        if method == "POST" and path in {"/api/auth/register", "/api/auth/login"}:
            limits.append(("auth-minute", client_host or "unknown", 60, self.auth_per_minute))
        if method == "POST" and path == "/api/chat":
            limits.extend(
                (
                    ("chat-minute", identity, 60, self.chat_per_minute),
                    ("chat-hour", identity, 3600, self.chat_per_hour),
                )
            )

        with self._lock:
            self._checks += 1
            if self._checks % 256 == 0:
                self._prune_all(now)
            active: list[tuple[deque[float], int, int]] = []
            for scope, key, window_seconds, limit in limits:
                bucket = self._buckets.setdefault((scope, key), deque())
                cutoff = now - window_seconds
                while bucket and bucket[0] <= cutoff:
                    bucket.popleft()
                if len(bucket) >= limit:
                    retry_after = max(1, round(bucket[0] + window_seconds - now))
                    return RateLimitDecision(limit=limit, retry_after=retry_after)
                active.append((bucket, window_seconds, limit))
            for bucket, _, _ in active:
                bucket.append(now)
        return None

    def _prune_all(self, now: float) -> None:
        for bucket_key, bucket in list(self._buckets.items()):
            window = 3600 if bucket_key[0] == "chat-hour" else 60
            cutoff = now - window
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if not bucket:
                del self._buckets[bucket_key]

    @staticmethod
    def _session_identity(session_token: str | None) -> str | None:
        if not session_token:
            return None
        return hashlib.sha256(session_token.encode("utf-8")).hexdigest()

    @staticmethod
    def _positive_int(name: str, default: int) -> int:
        value = int(os.getenv(name, str(default)))
        if value <= 0:
            raise RuntimeError(f"{name} must be positive")
        return value

    @staticmethod
    def _env_flag(name: str, *, default: bool) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}
