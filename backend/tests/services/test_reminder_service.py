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


def test_create_deduplicates_and_merges_same_schedule(database: Database) -> None:
    service = ReminderService(database)
    trigger = datetime.now(UTC) + timedelta(days=2)

    first = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="服药",
            next_trigger_at=trigger,
            repeat_type="weekly",
        )
    )
    duplicate = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="服药",
            next_trigger_at=trigger,
            repeat_type="weekly",
        )
    )
    merged = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="测量血压",
            next_trigger_at=trigger,
            repeat_type="weekly",
        )
    )

    listed = service.list(ReminderListQuery(user_id="demo-user"))
    assert duplicate.id == first.id
    assert merged.id == first.id
    assert merged.title == "服药；测量血压"
    assert listed.total == 1
    assert listed.items == [merged]


def test_same_time_with_different_titles_and_repeat_types_is_rejected(
    database: Database,
) -> None:
    service = ReminderService(database)
    trigger = datetime.now(UTC) + timedelta(days=2)

    one_time = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="本周复诊",
            next_trigger_at=trigger,
            repeat_type="none",
        )
    )
    with pytest.raises(ResourceConflictError):
        service.create(
            ReminderCreateRequest(
                user_id="demo-user",
                title="每周量血压",
                next_trigger_at=trigger,
                repeat_type="weekly",
            )
        )

    assert service.list(ReminderListQuery(user_id="demo-user")).items == [one_time]


def test_recurring_reminder_covers_same_one_time_reminder(database: Database) -> None:
    service = ReminderService(database)
    first_trigger = datetime.now(UTC) + timedelta(days=2)
    second_trigger = first_trigger + timedelta(days=1, hours=1)

    one_time = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="吃降压药",
            next_trigger_at=first_trigger,
            repeat_type="none",
        )
    )
    promoted = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="吃降压药",
            next_trigger_at=first_trigger,
            repeat_type="daily",
        )
    )
    daily = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="测量血压",
            next_trigger_at=second_trigger,
            repeat_type="daily",
        )
    )
    suppressed = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="测量血压",
            next_trigger_at=second_trigger,
            repeat_type="none",
        )
    )

    listed = service.list(ReminderListQuery(user_id="demo-user"))
    assert promoted.id == one_time.id
    assert promoted.repeat_type == "daily"
    assert suppressed.id == daily.id
    assert suppressed.repeat_type == "daily"
    assert listed.total == 2


def test_recurring_reminder_covers_equivalent_future_one_time_reminder(
    database: Database,
) -> None:
    service = ReminderService(database)
    first_trigger = datetime.now(UTC) + timedelta(days=2)
    daily = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="服用降压药",
            next_trigger_at=first_trigger,
            timezone="Asia/Shanghai",
            repeat_type="daily",
        )
    )

    covered = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="吃降压药",
            next_trigger_at=first_trigger + timedelta(days=3),
            timezone="Asia/Shanghai",
            repeat_type="none",
        )
    )

    assert covered.id == daily.id
    assert service.list(ReminderListQuery(user_id="demo-user")).items == [daily]


def test_different_content_cannot_overlap_a_future_recurring_occurrence(
    database: Database,
) -> None:
    service = ReminderService(database)
    first_trigger = datetime.now(UTC) + timedelta(days=2)
    daily = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="服用降压药",
            next_trigger_at=first_trigger,
            timezone="Asia/Shanghai",
            repeat_type="daily",
        )
    )

    with pytest.raises(ResourceConflictError):
        service.create(
            ReminderCreateRequest(
                user_id="demo-user",
                title="去买菜",
                next_trigger_at=first_trigger + timedelta(days=1),
                timezone="Asia/Shanghai",
                repeat_type="none",
            )
        )

    assert service.list(ReminderListQuery(user_id="demo-user")).items == [daily]


def test_update_into_existing_schedule_merges_and_keeps_updated_id(
    database: Database,
) -> None:
    service = ReminderService(database)
    first_trigger = datetime.now(UTC) + timedelta(days=2)
    second_trigger = first_trigger + timedelta(hours=1)
    moved = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="服药",
            next_trigger_at=first_trigger,
        )
    )
    existing = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="测量血压",
            next_trigger_at=second_trigger,
        )
    )

    merged = service.update(
        moved.id,
        ReminderUpdateRequest(
            user_id="demo-user",
            next_trigger_at=second_trigger,
        ),
    )

    assert merged.id == moved.id
    assert merged.title == "服药；测量血压"
    assert service.list(ReminderListQuery(user_id="demo-user")).items == [merged]
    deleted = service.list(
        ReminderListQuery(user_id="demo-user", status="deleted")
    )
    assert deleted.total == 1
    assert deleted.items[0].id == existing.id


def test_update_cannot_overlap_a_different_recurring_reminder(
    database: Database,
) -> None:
    service = ReminderService(database)
    first_trigger = datetime.now(UTC) + timedelta(days=2)
    daily = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="服用降压药",
            next_trigger_at=first_trigger,
            repeat_type="daily",
        )
    )
    groceries = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="去买菜",
            next_trigger_at=first_trigger + timedelta(hours=1),
            repeat_type="none",
        )
    )

    with pytest.raises(ResourceConflictError):
        service.update(
            groceries.id,
            ReminderUpdateRequest(
                user_id="demo-user",
                next_trigger_at=first_trigger + timedelta(days=1),
            ),
        )

    active = service.list(ReminderListQuery(user_id="demo-user"))
    assert active.total == 2
    assert {item.id for item in active.items} == {daily.id, groceries.id}


def test_update_into_stronger_schedule_returns_survivor_without_duplicate(
    database: Database,
) -> None:
    service = ReminderService(database)
    target_trigger = datetime.now(UTC) + timedelta(days=2)
    other_trigger = target_trigger + timedelta(hours=1)
    daily = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="吃降压药",
            next_trigger_at=target_trigger,
            repeat_type="daily",
        )
    )
    one_time = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="吃降压药",
            next_trigger_at=other_trigger,
            repeat_type="none",
        )
    )

    survivor = service.update(
        one_time.id,
        ReminderUpdateRequest(
            user_id="demo-user",
            next_trigger_at=target_trigger,
        ),
    )

    active = service.list(ReminderListQuery(user_id="demo-user"))
    deleted = service.list(
        ReminderListQuery(user_id="demo-user", status="deleted")
    )
    assert survivor.id == daily.id
    assert survivor.repeat_type == "daily"
    assert active.items == [daily]
    assert deleted.total == 1
    assert deleted.items[0].id == one_time.id


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


def test_weekly_ack_uses_next_local_week_across_dst(database: Database) -> None:
    service = ReminderService(database)
    created = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="每周散步",
            next_trigger_at="2027-03-07T09:00:00-05:00",
            timezone="America/New_York",
            repeat_type="weekly",
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
    assert acknowledged.reminder.status == "active"
    assert (next_local.month, next_local.day, next_local.hour) == (3, 14, 9)
    assert acknowledged.reminder.next_trigger_at - created.next_trigger_at == timedelta(
        hours=167
    )


def test_delayed_daily_ack_advances_until_next_trigger_is_future(
    database: Database,
) -> None:
    service = ReminderService(database)
    repository = ReminderRepository(database)
    now = datetime(2027, 1, 10, 10, 0, tzinfo=UTC)
    due = repository.create(
        user_id="demo-user",
        title="吃降压药",
        next_trigger_at="2027-01-07T19:00:00+08:00",
        timezone="Asia/Shanghai",
        repeat_type="daily",
    )

    acknowledged = service.acknowledge(
        UUID(due["id"]),
        ReminderAckRequest(
            user_id="demo-user",
            expected_trigger_at=due["next_trigger_at"],
        ),
        now=now,
    )

    next_local = acknowledged.reminder.next_trigger_at.astimezone(
        ZoneInfo("Asia/Shanghai")
    )
    assert acknowledged.reminder.next_trigger_at > now
    assert (next_local.month, next_local.day, next_local.hour) == (1, 10, 19)
    assert service.list_due(
        DueReminderQuery(user_id="demo-user"), now=now
    ).total == 0


def test_recurring_ack_merges_reminder_at_advanced_schedule(
    database: Database,
) -> None:
    service = ReminderService(database)
    repository = ReminderRepository(database)
    now = datetime(2027, 1, 10, 10, 0, tzinfo=UTC)
    due = repository.create(
        user_id="demo-user",
        title="吃降压药",
        next_trigger_at="2027-01-09T19:00:00+08:00",
        timezone="Asia/Shanghai",
        repeat_type="daily",
    )
    future = repository.create(
        user_id="demo-user",
        title="测量血压",
        next_trigger_at="2027-01-10T19:00:00+08:00",
        timezone="Asia/Shanghai",
        repeat_type="daily",
    )

    acknowledged = service.acknowledge(
        UUID(due["id"]),
        ReminderAckRequest(
            user_id="demo-user",
            expected_trigger_at=due["next_trigger_at"],
        ),
        now=now,
    )

    active = service.list(ReminderListQuery(user_id="demo-user"))
    deleted = service.list(
        ReminderListQuery(user_id="demo-user", status="deleted")
    )
    assert acknowledged.reminder.id == UUID(due["id"])
    assert acknowledged.reminder.title == "吃降压药；测量血压"
    assert active.total == 1
    assert deleted.total == 1
    assert deleted.items[0].id == UUID(future["id"])


def test_recurring_ack_completes_reminder_covered_at_advanced_schedule(
    database: Database,
) -> None:
    service = ReminderService(database)
    repository = ReminderRepository(database)
    now = datetime(2027, 1, 10, 10, 0, tzinfo=UTC)
    weekly = repository.create(
        user_id="demo-user",
        title="吃降压药",
        next_trigger_at="2027-01-03T19:00:00+08:00",
        timezone="Asia/Shanghai",
        repeat_type="weekly",
    )
    daily = repository.create(
        user_id="demo-user",
        title="吃降压药",
        next_trigger_at="2027-01-10T19:00:00+08:00",
        timezone="Asia/Shanghai",
        repeat_type="daily",
    )
    request = ReminderAckRequest(
        user_id="demo-user",
        expected_trigger_at=weekly["next_trigger_at"],
    )

    first = service.acknowledge(UUID(weekly["id"]), request, now=now)
    repeated = service.acknowledge(UUID(weekly["id"]), request, now=now)

    active = service.list(ReminderListQuery(user_id="demo-user"))
    completed = service.list(
        ReminderListQuery(user_id="demo-user", status="completed")
    )
    assert first.reminder.id == UUID(weekly["id"])
    assert first.reminder.status == "completed"
    assert repeated.reminder == first.reminder
    assert repeated.already_acknowledged is True
    assert active.total == 1
    assert active.items[0].id == UUID(daily["id"])
    assert completed.items == [first.reminder]


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


def test_create_deduplicates_high_confidence_medication_synonyms(
    database: Database,
) -> None:
    service = ReminderService(database)
    trigger_at = datetime.now(UTC) + timedelta(days=2)
    daily = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="吃降压药",
            next_trigger_at=trigger_at,
            timezone="Asia/Shanghai",
            repeat_type="daily",
        )
    )

    result = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="服用降压药",
            next_trigger_at=trigger_at,
            timezone="Asia/Shanghai",
            repeat_type="none",
        )
    )

    active = service.list(ReminderListQuery(user_id="demo-user"))
    assert result.id == daily.id
    assert result.repeat_type == "daily"
    assert active.total == 1


def test_same_schedule_merge_does_not_repeat_synonymous_title(
    database: Database,
) -> None:
    service = ReminderService(database)
    trigger_at = datetime.now(UTC) + timedelta(days=2)
    first = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="去遛弯",
            next_trigger_at=trigger_at,
            timezone="Asia/Shanghai",
            repeat_type="weekly",
        )
    )

    result = service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="散步",
            next_trigger_at=trigger_at,
            timezone="Asia/Shanghai",
            repeat_type="weekly",
        )
    )

    assert result.id == first.id
    assert result.title == "去遛弯"
    assert service.list(ReminderListQuery(user_id="demo-user")).total == 1


def test_synonym_rules_do_not_merge_different_medications(
    database: Database,
) -> None:
    service = ReminderService(database)
    trigger_at = datetime.now(UTC) + timedelta(days=2)
    service.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="吃降压药",
            next_trigger_at=trigger_at,
            timezone="Asia/Shanghai",
            repeat_type="daily",
        )
    )
    with pytest.raises(ResourceConflictError):
        service.create(
            ReminderCreateRequest(
                user_id="demo-user",
                title="服用感冒药",
                next_trigger_at=trigger_at,
                timezone="Asia/Shanghai",
                repeat_type="none",
            )
        )

    active = service.list(ReminderListQuery(user_id="demo-user"))
    assert active.total == 1
    assert active.items[0].title == "吃降压药"
