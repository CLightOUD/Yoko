from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from backend.app.database import Database
from backend.app.repositories import ReminderRepository
from backend.app.schemas import (
    DueReminderQuery,
    ReminderAckRequest,
    ReminderCreateRequest,
    ReminderListQuery,
    ReminderUpdateRequest,
)
from backend.app.services import (
    InvalidRequestError,
    ReminderService,
    ResourceConflictError,
    ResourceNotFoundError,
)


def test_create_list_update_and_delete_reminder(database: Database) -> None:
    service = ReminderService(database)
    trigger = datetime.now(UTC) + timedelta(days=2)
    created = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="服药",
            next_trigger_at=trigger,
            repeat_type="none",
        )
    )

    listed = service.list(ReminderListQuery(user_id="demo-user"))
    assert listed.total == 1
    assert listed.items == [created]

    updated = service.update(
        created.id,
        ReminderUpdateRequest(user_id="demo-user", title="按时服药"),
    )
    assert updated.title == "按时服药"

    deleted = service.delete(created.id, "demo-user")
    assert deleted.id == created.id
    assert service.delete(created.id, "demo-user") == deleted
    assert service.list(ReminderListQuery(user_id="demo-user")).total == 0


def test_unknown_and_cross_user_reminders_are_not_disclosed(
    database: Database,
    other_user: str,
) -> None:
    service = ReminderService(database)
    created = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="服药",
            next_trigger_at=datetime.now(UTC) + timedelta(days=1),
        )
    )

    with pytest.raises(ResourceNotFoundError, match="提醒不存在"):
        service.delete(created.id, other_user)

    with pytest.raises(ResourceNotFoundError, match="用户不存在"):
        service.list(ReminderListQuery(user_id="missing-user"))


def test_one_time_acknowledgement_is_idempotent(database: Database) -> None:
    service = ReminderService(database)
    trigger = datetime.now(UTC) + timedelta(days=1)
    created = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="预约",
            next_trigger_at=trigger,
            repeat_type="none",
        )
    )
    request = ReminderAckRequest(
        user_id="demo-user",
        expected_trigger_at=created.next_trigger_at,
    )

    first = service.acknowledge(created.id, request)
    second = service.acknowledge(created.id, request)

    assert first.already_acknowledged is False
    assert first.reminder.status == "completed"
    assert first.reminder.last_triggered_at == created.next_trigger_at
    assert second.already_acknowledged is True
    assert second.reminder.next_trigger_at == first.reminder.next_trigger_at


def test_daily_ack_uses_next_local_day_across_dst(database: Database) -> None:
    service = ReminderService(database)
    created = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="晨间散步",
            next_trigger_at="2027-03-13T09:00:00-05:00",
            timezone="America/New_York",
            repeat_type="daily",
        )
    )

    acknowledged = service.acknowledge(
        created.id,
        ReminderAckRequest(
            user_id="demo-user",
            expected_trigger_at=created.next_trigger_at,
        ),
    )

    next_local = acknowledged.reminder.next_trigger_at.astimezone(
        ZoneInfo("America/New_York")
    )
    assert (next_local.hour, next_local.minute) == (9, 0)
    assert acknowledged.reminder.next_trigger_at - created.next_trigger_at == timedelta(
        hours=23
    )


def test_ack_rejects_stale_trigger_and_due_query_uses_server_time(
    database: Database,
) -> None:
    service = ReminderService(database)
    repository = ReminderRepository(database)
    now = datetime.now(UTC)
    due = repository.create(
        user_id="demo-user",
        title="到期",
        next_trigger_at=now - timedelta(minutes=1),
        timezone="Asia/Shanghai",
        repeat_type="none",
    )
    result = service.list_due(DueReminderQuery(user_id="demo-user"), now=now)
    assert result.total == 1
    assert result.items[0].id == UUID(due["id"])

    with pytest.raises(ResourceConflictError, match="已经变化"):
        service.acknowledge(
            UUID(due["id"]),
            ReminderAckRequest(
                user_id="demo-user",
                expected_trigger_at=now - timedelta(minutes=2),
            ),
        )

    with pytest.raises(InvalidRequestError, match="晚于当前时间"):
        service.update(
            UUID(due["id"]),
            ReminderUpdateRequest(user_id="demo-user", title="仍然到期"),
            now=now,
        )
