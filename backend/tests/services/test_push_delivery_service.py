from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from pywebpush import WebPushException

from backend.app.repositories import ReminderRepository
from backend.app.schemas import PushSubscriptionBody, PushSubscriptionKeys
from backend.app.services.push_delivery_service import PushDeliveryService


def test_push_delivery_sends_each_occurrence_once(database) -> None:
    sent = []

    def sender(**kwargs):
        sent.append(kwargs)

    service = PushDeliveryService(
        database,
        sender=sender,
        enabled=True,
        vapid_private_key="private-key-for-test",
        vapid_public_key="public-key-for-test",
        vapid_subject="mailto:test@example.com",
        poll_seconds=60,
    )
    service.subscribe(
        user_id="demo-user",
        request=PushSubscriptionBody(
            endpoint="https://push.example.test/subscription/one",
            keys=PushSubscriptionKeys(
                p256dh="abcdefghijklmnop",
                auth="qrstuvwxyzABCDEF",
            ),
        ),
    )
    due = datetime.now(UTC) - timedelta(minutes=1)
    ReminderRepository(database).create(
        user_id="demo-user",
        title="按时服药",
        next_trigger_at=due,
        timezone="Asia/Shanghai",
        repeat_type="none",
    )

    assert service.deliver_once(now=datetime.now(UTC)) == 1
    assert service.deliver_once(now=datetime.now(UTC)) == 0
    assert len(sent) == 1
    assert "按时服药" in sent[0]["data"]

    with database.connection() as connection:
        delivery = connection.execute(
            "SELECT status, attempt_count FROM reminder_deliveries"
        ).fetchone()
    assert dict(delivery) == {"status": "sent", "attempt_count": 1}


def test_push_subscription_can_be_disabled_idempotently(database) -> None:
    service = PushDeliveryService(database, enabled=False)
    request = PushSubscriptionBody(
        endpoint="https://push.example.test/subscription/two",
        keys=PushSubscriptionKeys(
            p256dh="abcdefghijklmnop",
            auth="qrstuvwxyzABCDEF",
        ),
    )
    service.subscribe(user_id="demo-user", request=request)

    assert service.unsubscribe(
        user_id="demo-user", endpoint=request.endpoint
    ).deleted is True
    assert service.unsubscribe(
        user_id="demo-user",
        endpoint="https://push.example.test/subscription/unknown",
    ).deleted is True
    assert service.unsubscribe(
        user_id="demo-user", endpoint=request.endpoint
    ).deleted is True


def test_gone_push_endpoint_is_disabled_without_retry(database) -> None:
    def sender(**kwargs):
        del kwargs
        raise WebPushException(
            "subscription expired",
            response=SimpleNamespace(status_code=410, text="gone"),
        )

    service = PushDeliveryService(
        database,
        sender=sender,
        enabled=True,
        vapid_private_key="private-key-for-test",
        vapid_public_key="public-key-for-test",
        vapid_subject="mailto:test@example.com",
    )
    service.subscribe(
        user_id="demo-user",
        request=PushSubscriptionBody(
            endpoint="https://push.example.test/subscription/gone",
            keys=PushSubscriptionKeys(
                p256dh="abcdefghijklmnop",
                auth="qrstuvwxyzABCDEF",
            ),
        ),
    )
    current = datetime.now(UTC)
    ReminderRepository(database).create(
        user_id="demo-user",
        title="失效订阅测试",
        next_trigger_at=current - timedelta(minutes=1),
        timezone="Asia/Shanghai",
        repeat_type="none",
    )

    assert service.deliver_once(now=current) == 0
    assert service.deliver_once(now=current + timedelta(hours=2)) == 0
    with database.connection() as connection:
        subscription = connection.execute(
            "SELECT failure_count, disabled_at FROM push_subscriptions"
        ).fetchone()
        delivery = connection.execute(
            "SELECT status, attempt_count, last_error_code FROM reminder_deliveries"
        ).fetchone()

    assert subscription["failure_count"] == 1
    assert subscription["disabled_at"] is not None
    assert dict(delivery) == {
        "status": "failed",
        "attempt_count": 1,
        "last_error_code": "HTTP_410",
    }
