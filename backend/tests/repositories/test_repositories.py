from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.app.database import Database
from backend.app.repositories import (
    FeedbackRepository,
    MemoryEventRepository,
    MemoryRepository,
    MessageRepository,
    MetricsRepository,
    ReminderRepository,
)


def test_messages_are_isolated_by_user_and_keep_recent_order(
    database: Database,
    second_user: str,
) -> None:
    repository = MessageRepository(database)
    conversation_id = str(uuid4())
    first = repository.create(
        user_id="demo-user",
        conversation_id=conversation_id,
        role="user",
        content="第一条",
    )
    second = repository.create(
        user_id="demo-user",
        conversation_id=conversation_id,
        role="assistant",
        content="第二条",
    )

    assert repository.get_for_user(first["id"], second_user) is None
    assert repository.conversation_belongs_to_user(conversation_id, "demo-user")
    assert not repository.conversation_belongs_to_user(conversation_id, second_user)
    assert [item["id"] for item in repository.list_recent(
        user_id="demo-user", conversation_id=conversation_id
    )] == [first["id"], second["id"]]


def test_reminder_repository_lists_due_items_and_soft_deletes(
    database: Database,
    second_user: str,
) -> None:
    repository = ReminderRepository(database)
    now = datetime.now(UTC)
    due = repository.create(
        user_id="demo-user",
        title="已到期",
        next_trigger_at=now - timedelta(minutes=1),
        timezone="Asia/Shanghai",
        repeat_type="none",
    )
    future = repository.create(
        user_id="demo-user",
        title="稍后",
        next_trigger_at=now + timedelta(hours=1),
        timezone="Asia/Shanghai",
        repeat_type="daily",
    )
    repository.create(
        user_id=second_user,
        title="其他用户",
        next_trigger_at=now - timedelta(minutes=1),
        timezone="Asia/Shanghai",
        repeat_type="none",
    )

    items, total = repository.list_due(user_id="demo-user", due_at=now)
    assert total == 1
    assert [item["id"] for item in items] == [due["id"]]

    all_items, total = repository.list(user_id="demo-user", status="all")
    assert total == 2
    assert [item["id"] for item in all_items] == [due["id"], future["id"]]

    assert repository.soft_delete(reminder_id=due["id"], user_id="demo-user")
    assert repository.soft_delete(reminder_id=due["id"], user_id="demo-user")
    assert repository.get_for_user(due["id"], "demo-user")["status"] == "deleted"
    assert not repository.soft_delete(reminder_id=due["id"], user_id=second_user)


def test_reminder_times_are_normalized_before_sqlite_comparison(
    database: Database,
) -> None:
    repository = ReminderRepository(database)
    repository.create(
        user_id="demo-user",
        title="相同时刻",
        next_trigger_at="2026-08-23T08:00:00+08:00",
        timezone="Asia/Shanghai",
        repeat_type="none",
    )

    items, total = repository.list_due(
        user_id="demo-user",
        due_at="2026-08-23T00:00:00+00:00",
    )

    assert total == 1
    assert items[0]["next_trigger_at"] == "2026-08-23T00:00:00+00:00"


def test_memories_enforce_one_active_key_and_filter_irrelevant_tasks(
    database: Database,
) -> None:
    repository = MemoryRepository(database)
    global_memory = repository.create(
        user_id="demo-user",
        scope="global",
        task_type="global",
        memory_key="language",
        memory_value="zh-CN",
        display_text="偏好使用中文",
    )
    medication = repository.create(
        user_id="demo-user",
        scope="task",
        task_type="medication",
        memory_key="preferred_time",
        memory_value="19:00",
        display_text="服药提醒时间为晚上7点",
    )
    repository.create(
        user_id="demo-user",
        scope="task",
        task_type="walking",
        memory_key="preferred_time",
        memory_value="07:00",
        display_text="散步时间为早上7点",
    )

    with pytest.raises(sqlite3.IntegrityError):
        repository.create(
            user_id="demo-user",
            scope="task",
            task_type="medication",
            memory_key="preferred_time",
            memory_value="20:00",
            display_text="重复有效偏好",
        )

    retrieved = repository.retrieve(user_id="demo-user", task_type="medication")
    assert [item["id"] for item in retrieved] == [medication["id"], global_memory["id"]]
    assert all(item["active"] is True for item in retrieved)

    assert repository.mark_used(
        memory_ids=[medication["id"]], user_id="demo-user"
    ) == 1
    assert repository.get_for_user(
        medication["id"], "demo-user"
    )["last_used_at"] is not None


def test_memory_events_preserve_before_and_after_snapshots(database: Database) -> None:
    memories = MemoryRepository(database)
    events = MemoryEventRepository(database)
    memory = memories.create(
        user_id="demo-user",
        scope="task",
        task_type="appointment",
        memory_key="lead_time",
        memory_value="30m",
        display_text="预约前30分钟提醒",
    )

    event = events.create(
        memory_id=memory["id"],
        user_id="demo-user",
        action="updated",
        before_value={"memory_value": "15m"},
        after_value={"memory_value": "30m"},
    )

    assert events.list_for_memory(
        memory_id=memory["id"], user_id="demo-user"
    ) == [event]
    assert event["before_value"] == '{"memory_value":"15m"}'
    assert event["after_value"] == '{"memory_value":"30m"}'


def test_metrics_store_memory_ids_and_summarize_completeness(database: Database) -> None:
    repository = MetricsRepository(database)
    now = datetime.now(UTC)
    first_request = str(uuid4())
    first = repository.create(
        request_id=first_request,
        user_id="demo-user",
        model_call_count=1,
        input_tokens=100,
        output_tokens=20,
        memory_tokens=10,
        retrieved_memory_count=1,
        used_memory_count=1,
        retrieval_ms=5,
        model_ms=50,
        tool_ms=5,
        total_ms=70,
        retrieved_memory_ids=["m1"],
        used_memory_ids=["m1"],
        created_at=now - timedelta(minutes=1),
    )
    repository.create(
        request_id=str(uuid4()),
        user_id="demo-user",
        model_call_count=1,
        input_tokens=None,
        output_tokens=None,
        memory_tokens=0,
        retrieved_memory_count=0,
        used_memory_count=0,
        retrieval_ms=0,
        model_ms=30,
        tool_ms=0,
        total_ms=35,
        created_at=now,
    )

    assert repository.get_by_request(first_request) == first
    assert first["retrieved_memory_ids"] == ["m1"]
    summary = repository.summary(user_id="demo-user")
    assert summary["request_count"] == 2
    assert summary["model_call_count"] == 2
    assert summary["input_tokens"] == 100
    assert summary["requests_with_retrieved_memory"] == 1
    assert summary["requests_with_used_memory"] == 1
    assert summary["token_metrics_complete"] is False


def test_feedback_dedup_key_is_unique(database: Database) -> None:
    messages = MessageRepository(database)
    feedbacks = FeedbackRepository(database)
    message = messages.create(
        user_id="demo-user",
        conversation_id=str(uuid4()),
        role="user",
        content="以后晚上7点提醒",
        request_id=str(uuid4()),
    )
    created = feedbacks.create(
        user_id="demo-user",
        request_id=message["request_id"],
        feedback_message_id=message["id"],
        feedback_text="以后晚上7点提醒",
        corrected_reply=None,
        rating="down",
        dedup_key="same-feedback",
    )

    assert feedbacks.get_by_dedup_key("same-feedback") == created
    with pytest.raises(sqlite3.IntegrityError):
        feedbacks.create(
            user_id="demo-user",
            request_id=message["request_id"],
            feedback_message_id=message["id"],
            feedback_text="以后晚上7点提醒",
            dedup_key="same-feedback",
        )
