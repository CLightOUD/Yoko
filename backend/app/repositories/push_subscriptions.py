from __future__ import annotations

import hashlib
import sqlite3
from typing import Any
from uuid import uuid4

from backend.app.repositories._common import BaseRepository, row_to_dict, utc_now_iso


class PushSubscriptionRepository(BaseRepository):
    @staticmethod
    def endpoint_hash(endpoint: str) -> str:
        return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()

    def upsert(
        self,
        *,
        user_id: str,
        endpoint: str,
        p256dh: str,
        auth: str,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        digest = self.endpoint_hash(endpoint)
        with self.database.transaction(immediate=True) as connection:
            existing = connection.execute(
                "SELECT id FROM push_subscriptions WHERE endpoint_hash = ?",
                (digest,),
            ).fetchone()
            if existing is None:
                subscription_id = str(uuid4())
                connection.execute(
                    """
                    INSERT INTO push_subscriptions (
                        id, user_id, endpoint, endpoint_hash, p256dh, auth,
                        failure_count, last_success_at, disabled_at,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 0, NULL, NULL, ?, ?)
                    """,
                    (
                        subscription_id,
                        user_id,
                        endpoint,
                        digest,
                        p256dh,
                        auth,
                        now,
                        now,
                    ),
                )
            else:
                subscription_id = existing["id"]
                connection.execute(
                    """
                    UPDATE push_subscriptions
                    SET user_id = ?, endpoint = ?, p256dh = ?, auth = ?,
                        failure_count = 0, disabled_at = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    (user_id, endpoint, p256dh, auth, now, subscription_id),
                )
            row = connection.execute(
                "SELECT * FROM push_subscriptions WHERE id = ?",
                (subscription_id,),
            ).fetchone()
        return dict(row)

    def disable_for_user(self, *, user_id: str, endpoint: str) -> bool:
        now = utc_now_iso()
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE push_subscriptions
                SET disabled_at = COALESCE(disabled_at, ?), updated_at = ?
                WHERE user_id = ? AND endpoint_hash = ?
                """,
                (now, now, user_id, self.endpoint_hash(endpoint)),
            )
        return cursor.rowcount > 0

    def get_for_user(
        self,
        *,
        user_id: str,
        endpoint: str,
    ) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM push_subscriptions
                WHERE user_id = ? AND endpoint_hash = ?
                """,
                (user_id, self.endpoint_hash(endpoint)),
            ).fetchone()
        return row_to_dict(row)
