from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from backend.app.database import Database


class ReminderDeliveryRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def claim_due(
        self,
        *,
        now: datetime,
        limit: int,
        lease_seconds: int,
        max_attempts: int,
    ) -> list[dict[str, Any]]:
        now_value = now.astimezone(UTC).isoformat()
        lease_value = (now.astimezone(UTC) + timedelta(seconds=lease_seconds)).isoformat()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO reminder_deliveries (
                    id, reminder_id, user_id, subscription_id, trigger_at,
                    status, attempt_count, lease_expires_at, next_attempt_at,
                    last_error_code, sent_at, created_at, updated_at
                )
                SELECT lower(hex(randomblob(16))), r.id, r.user_id, s.id,
                       r.next_trigger_at, 'pending', 0, ?, ?, NULL, NULL, ?, ?
                FROM reminders r
                JOIN push_subscriptions s ON s.user_id = r.user_id
                WHERE r.status = 'active'
                  AND r.next_trigger_at <= ?
                  AND s.disabled_at IS NULL
                """,
                (now_value, now_value, now_value, now_value, now_value),
            )
            rows = connection.execute(
                """
                SELECT d.*, r.title, r.timezone, r.repeat_type,
                       s.endpoint, s.p256dh, s.auth
                FROM reminder_deliveries d
                JOIN reminders r ON r.id = d.reminder_id
                JOIN push_subscriptions s ON s.id = d.subscription_id
                WHERE d.status <> 'sent'
                  AND d.attempt_count < ?
                  AND d.next_attempt_at <= ?
                  AND d.lease_expires_at <= ?
                  AND s.disabled_at IS NULL
                ORDER BY d.next_attempt_at, d.id
                LIMIT ?
                """,
                (max_attempts, now_value, now_value, limit),
            ).fetchall()
            claimed: list[dict[str, Any]] = []
            for row in rows:
                cursor = connection.execute(
                    """
                    UPDATE reminder_deliveries
                    SET status = 'pending', attempt_count = attempt_count + 1,
                        lease_expires_at = ?, updated_at = ?
                    WHERE id = ? AND status <> 'sent' AND lease_expires_at <= ?
                    """,
                    (lease_value, now_value, row["id"], now_value),
                )
                if cursor.rowcount == 1:
                    item = dict(row)
                    item["attempt_count"] = int(item["attempt_count"]) + 1
                    claimed.append(item)
        return claimed

    def mark_sent(self, delivery_id: str, *, sent_at: datetime) -> None:
        value = sent_at.astimezone(UTC).isoformat()
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE reminder_deliveries
                SET status = 'sent', sent_at = ?, last_error_code = NULL,
                    lease_expires_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (value, value, value, delivery_id),
            )
            connection.execute(
                """
                UPDATE push_subscriptions
                SET failure_count = 0, last_success_at = ?, updated_at = ?
                WHERE id = (
                    SELECT subscription_id FROM reminder_deliveries WHERE id = ?
                )
                """,
                (value, value, delivery_id),
            )

    def mark_failed(
        self,
        delivery_id: str,
        *,
        failed_at: datetime,
        retry_at: datetime,
        error_code: str,
        disable_subscription: bool,
    ) -> None:
        failed = failed_at.astimezone(UTC).isoformat()
        retry = retry_at.astimezone(UTC).isoformat()
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE reminder_deliveries
                SET status = 'failed', next_attempt_at = ?, lease_expires_at = ?,
                    last_error_code = ?, updated_at = ?
                WHERE id = ?
                """,
                (retry, failed, error_code[:64], failed, delivery_id),
            )
            connection.execute(
                """
                UPDATE push_subscriptions
                SET failure_count = failure_count + 1,
                    disabled_at = CASE WHEN ? THEN ? ELSE disabled_at END,
                    updated_at = ?
                WHERE id = (
                    SELECT subscription_id FROM reminder_deliveries WHERE id = ?
                )
                """,
                (1 if disable_subscription else 0, failed, failed, delivery_id),
            )
