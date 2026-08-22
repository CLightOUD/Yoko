from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from backend.app.database import Database
from backend.app.repositories import MemoryEventRepository, MessageRepository
from backend.app.schemas import MemoryListQuery, MemoryUpdateRequest
from backend.app.services import (
    InvalidRequestError,
    MemoryService,
    ResourceNotFoundError,
)


def test_upsert_updates_same_memory_and_writes_auditable_events(
    database: Database,
) -> None:
    service = MemoryService(database)
    messages = MessageRepository(database)
    conversation_id = str(uuid4())
    source = messages.create(
        user_id="demo-user",
        conversation_id=conversation_id,
        role="user",
        content="以后晚上七点提醒",
    )

    created = service.upsert(
        user_id="demo-user",
        scope="task",
        task_type="medication",
        memory_key="preferred_time",
        memory_value="19:30",
        display_text="服药提醒时间为晚上7点半",
        reason="用户明确表达长期偏好",
        source_message_id=UUID(source["id"]),
    )
    updated = service.upsert(
        user_id="demo-user",
        scope="task",
        task_type="medication",
        memory_key="preferred_time",
        memory_value="19:00",
        display_text="服药提醒时间为晚上7点",
        reason="用户修正长期偏好",
        source_message_id=UUID(source["id"]),
    )

    assert created.action == "created"
    assert updated.action == "updated"
    assert updated.memory.id == created.memory.id
    assert updated.memory.memory_value == "19:00"
    events = MemoryEventRepository(database).list_for_memory(
        memory_id=str(created.memory.id), user_id="demo-user"
    )
    assert [event["action"] for event in events] == ["created", "updated"]


def test_retrieve_returns_task_then_global_and_marks_only_owned_memory(
    database: Database,
    other_user: str,
) -> None:
    service = MemoryService(database)
    global_memory = service.upsert(
        user_id="demo-user",
        scope="global",
        task_type="global",
        memory_key="language",
        memory_value="zh-CN",
        display_text="偏好中文",
        reason="明确长期偏好",
    ).memory
    task_memory = service.upsert(
        user_id="demo-user",
        scope="task",
        task_type="walking",
        memory_key="preferred_time",
        memory_value="07:00",
        display_text="早上7点散步",
        reason="明确长期偏好",
    ).memory
    other_memory = service.upsert(
        user_id=other_user,
        scope="task",
        task_type="walking",
        memory_key="preferred_time",
        memory_value="08:00",
        display_text="早上8点散步",
        reason="明确长期偏好",
    ).memory

    retrieved = service.retrieve(user_id="demo-user", task_type="walking")
    assert [item.id for item in retrieved] == [task_memory.id, global_memory.id]
    assert service.mark_used(
        user_id="demo-user", memory_ids=[task_memory.id, other_memory.id]
    ) == 1


def test_manual_update_and_delete_are_logged_and_delete_is_idempotent(
    database: Database,
) -> None:
    service = MemoryService(database)
    memory = service.upsert(
        user_id="demo-user",
        scope="task",
        task_type="appointment",
        memory_key="lead_time",
        memory_value="15m",
        display_text="提前15分钟提醒",
        reason="明确长期偏好",
    ).memory

    updated = service.update(
        memory.id,
        MemoryUpdateRequest(
            user_id="demo-user",
            memory_value="30m",
            display_text="提前30分钟提醒",
        ),
    )
    assert updated.memory_value == "30m"
    assert service.delete(memory.id, "demo-user").deleted
    assert service.delete(memory.id, "demo-user").deleted
    events = MemoryEventRepository(database).list_for_memory(
        memory_id=str(memory.id), user_id="demo-user"
    )
    assert [event["action"] for event in events] == [
        "created",
        "updated",
        "deleted",
    ]
    assert service.list(
        MemoryListQuery(user_id="demo-user", active=False)
    ).total == 1


def test_memory_write_rolls_back_when_event_write_fails(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemoryService(database)

    def fail_event(**_: object) -> None:
        raise RuntimeError("event failed")

    monkeypatch.setattr(service.events, "create", fail_event)
    with pytest.raises(RuntimeError, match="event failed"):
        service.upsert(
            user_id="demo-user",
            scope="task",
            task_type="other",
            memory_key="tone",
            memory_value="gentle",
            display_text="使用温和语气",
            reason="明确长期偏好",
        )

    assert service.list(MemoryListQuery(user_id="demo-user")).total == 0


def test_memory_validates_scope_and_source_ownership(
    database: Database,
    other_user: str,
) -> None:
    service = MemoryService(database)
    source = MessageRepository(database).create(
        user_id=other_user,
        conversation_id=str(uuid4()),
        role="user",
        content="其他用户消息",
    )

    with pytest.raises(InvalidRequestError, match="不匹配"):
        service.upsert(
            user_id="demo-user",
            scope="global",
            task_type="walking",
            memory_key="bad",
            memory_value="bad",
            display_text="错误范围",
            reason="测试",
        )

    with pytest.raises(ResourceNotFoundError, match="来源消息不存在"):
        service.upsert(
            user_id="demo-user",
            scope="task",
            task_type="other",
            memory_key="tone",
            memory_value="gentle",
            display_text="使用温和语气",
            reason="明确长期偏好",
            source_message_id=UUID(source["id"]),
        )
