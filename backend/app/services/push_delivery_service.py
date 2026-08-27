from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from threading import Event, Thread
from typing import Any
from uuid import UUID

from pywebpush import WebPushException, webpush

from backend.app.database import Database
from backend.app.repositories import (
    PushSubscriptionRepository,
    ReminderDeliveryRepository,
)
from backend.app.schemas import (
    PushConfigResponse,
    PushSubscriptionBody,
    PushSubscriptionDeleteResponse,
    PushSubscriptionResponse,
)


logger = logging.getLogger("yoko.push")
PushSender = Callable[..., Any]


class PushDeliveryService:
    """Persist subscriptions and deliver each reminder occurrence once per device."""

    def __init__(
        self,
        database: Database,
        *,
        sender: PushSender = webpush,
        enabled: bool | None = None,
        vapid_private_key: str | None = None,
        vapid_public_key: str | None = None,
        vapid_subject: str | None = None,
        poll_seconds: float | None = None,
    ) -> None:
        self.database = database
        self.subscriptions = PushSubscriptionRepository(database)
        self.deliveries = ReminderDeliveryRepository(database)
        self._sender = sender
        self._enabled = self._env_flag("PUSH_ENABLED", False) if enabled is None else enabled
        self._private_key = vapid_private_key or os.getenv("VAPID_PRIVATE_KEY", "").strip()
        self._public_key = vapid_public_key or os.getenv("VAPID_PUBLIC_KEY", "").strip()
        self._subject = vapid_subject or os.getenv("VAPID_SUBJECT", "").strip()
        self._poll_seconds = (
            poll_seconds
            if poll_seconds is not None
            else self._positive_float("PUSH_POLL_SECONDS", 15)
        )
        self._stop = Event()
        self._thread: Thread | None = None
        if self._enabled and not (
            self._private_key and self._public_key and self._subject
        ):
            raise RuntimeError(
                "PUSH_ENABLED requires VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, and VAPID_SUBJECT"
            )

    def config(self) -> PushConfigResponse:
        return PushConfigResponse(
            enabled=self._enabled,
            application_server_key=self._public_key if self._enabled else None,
        )

    def subscribe(
        self,
        *,
        user_id: str,
        request: PushSubscriptionBody,
    ) -> PushSubscriptionResponse:
        subscription = self.subscriptions.upsert(
            user_id=user_id,
            endpoint=request.endpoint,
            p256dh=request.keys.p256dh,
            auth=request.keys.auth,
        )
        return PushSubscriptionResponse(id=UUID(subscription["id"]), active=True)

    def unsubscribe(
        self,
        *,
        user_id: str,
        endpoint: str,
    ) -> PushSubscriptionDeleteResponse:
        self.subscriptions.disable_for_user(
            user_id=user_id,
            endpoint=endpoint,
        )
        return PushSubscriptionDeleteResponse(deleted=True)

    def start(self) -> None:
        if not self._enabled or self._thread is not None:
            return
        self._stop.clear()
        self._thread = Thread(
            target=self._run,
            name="yoko-push-delivery",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(2.0, self._poll_seconds + 1.0))
        self._thread = None

    def deliver_once(self, *, now: datetime | None = None) -> int:
        if not self._enabled:
            return 0
        current = now or datetime.now(UTC)
        deliveries = self.deliveries.claim_due(
            now=current,
            limit=50,
            lease_seconds=60,
            max_attempts=5,
        )
        sent = 0
        for delivery in deliveries:
            payload = json.dumps(
                {
                    "title": "Yoko 提醒",
                    "body": delivery["title"][:200],
                    "url": "/?tab=reminders",
                    "reminder_id": delivery["reminder_id"],
                    "trigger_at": delivery["trigger_at"],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            try:
                self._sender(
                    subscription_info={
                        "endpoint": delivery["endpoint"],
                        "keys": {
                            "p256dh": delivery["p256dh"],
                            "auth": delivery["auth"],
                        },
                    },
                    data=payload,
                    vapid_private_key=self._private_key,
                    vapid_claims={"sub": self._subject},
                    ttl=86_400,
                    timeout=10,
                )
            except WebPushException as exc:
                response = getattr(exc, "response", None)
                status_code = getattr(response, "status_code", None)
                self._record_failure(
                    delivery,
                    current=current,
                    error_code=(
                        f"HTTP_{status_code}"
                        if isinstance(status_code, int)
                        else type(exc).__name__
                    ),
                    disable=status_code in {404, 410},
                )
            except Exception as exc:
                self._record_failure(
                    delivery,
                    current=current,
                    error_code=type(exc).__name__,
                    disable=False,
                )
            else:
                self.deliveries.mark_sent(delivery["id"], sent_at=current)
                sent += 1
        return sent

    def _record_failure(
        self,
        delivery: dict[str, Any],
        *,
        current: datetime,
        error_code: str,
        disable: bool,
    ) -> None:
        delay = min(3600, 60 * (2 ** max(0, int(delivery["attempt_count"]) - 1)))
        self.deliveries.mark_failed(
            delivery["id"],
            failed_at=current,
            retry_at=current + timedelta(seconds=delay),
            error_code=error_code,
            disable_subscription=disable,
        )
        logger.warning(
            "push_delivery_failed",
            extra={"error_type": error_code},
        )

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.deliver_once()
            except Exception as exc:
                logger.exception(
                    "push_worker_failed",
                    extra={"error_type": type(exc).__name__},
                )
            self._stop.wait(self._poll_seconds)

    @staticmethod
    def _env_flag(name: str, default: bool) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _positive_float(name: str, default: float) -> float:
        value = float(os.getenv(name, str(default)))
        if value <= 0:
            raise RuntimeError(f"{name} must be positive")
        return value
