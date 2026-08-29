from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app import schemas
from backend.app.schemas.chat import MAX_CHAT_IMAGE_BYTES


def memory_payload() -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "id": uuid4(),
        "scope": "task",
        "task_type": "medication",
        "memory_key": "preferred_time",
        "memory_value": "19:00",
        "display_text": "服药提醒时间为晚上7点",
        "active": True,
        "source_message_id": uuid4(),
        "created_at": now,
        "updated_at": now,
        "last_used_at": None,
    }


def reminder_payload() -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "id": uuid4(),
        "user_id": "demo-user",
        "title": "服用降压药",
        "next_trigger_at": now + timedelta(hours=1),
        "timezone": "Asia/Shanghai",
        "repeat_type": "daily",
        "status": "active",
        "last_triggered_at": None,
        "created_at": now,
        "updated_at": now,
    }


def request_metrics_payload() -> dict[str, object]:
    return {
        "model_call_count": 1,
        "input_tokens": 120,
        "output_tokens": 30,
        "memory_tokens": 20,
        "retrieved_memory_count": 1,
        "used_memory_count": 1,
        "retrieval_ms": 5,
        "model_ms": 100,
        "tool_ms": 10,
        "total_ms": 130,
    }


def test_all_exported_models_generate_json_schema() -> None:
    for name in schemas.__all__:
        model = getattr(schemas, name)
        assert model.model_json_schema()["title"] == name


def test_fixed_success_and_error_literals_are_enforced() -> None:
    assert schemas.HealthResponse(status="ok").status == "ok"
    assert schemas.ReadinessResponse(
        status="ok", database="ok", model="ok", schema_version=2
    ).schema_version == 2
    assert schemas.DeleteResponse(id=uuid4(), deleted=True).deleted is True

    with pytest.raises(ValidationError):
        schemas.HealthResponse(status="down")

    with pytest.raises(ValidationError):
        schemas.ErrorDetail(code="UNKNOWN", message="未知错误", details=None)

    with pytest.raises(ValidationError):
        schemas.ErrorDetail(code="INVALID_REQUEST", message="缺少详情字段")


def test_app_timezone_configures_request_defaults(monkeypatch) -> None:
    monkeypatch.setenv("APP_TIMEZONE", "Europe/London")

    registered = schemas.RegisterRequest(
        username="timezone_user",
        password="correct-horse-2026",
        display_name="时区用户",
    )
    reminder = schemas.ReminderCreateRequest(
        user_id="demo-user",
        title="散步",
        next_trigger_at=datetime.now(UTC) + timedelta(days=1),
    )

    assert registered.timezone == "Europe/London"
    assert reminder.timezone == "Europe/London"


def test_chat_request_trims_text_and_rejects_extra_fields() -> None:
    request = schemas.ChatRequest(
        user_id=" demo-user ",
        message=" 提醒我吃药 ",
        timezone="Asia/Shanghai",
    )

    assert request.user_id == "demo-user"
    assert request.message == "提醒我吃药"

    with pytest.raises(ValidationError):
        schemas.ChatRequest(
            user_id="demo-user",
            message="提醒我吃药",
            unexpected=True,
        )

    public = schemas.ChatRequestBody(
        user_id="attacker-selected-user",
        message="提醒我吃药",
    )
    assert "user_id" not in public.model_dump()
    with pytest.raises(ValidationError):
        schemas.ChatRequestBody(message="提醒我吃药", unexpected=True)


def test_chat_request_rejects_invalid_timezone() -> None:
    with pytest.raises(ValidationError, match="valid IANA timezone"):
        schemas.ChatRequest(
            user_id="demo-user",
            message="提醒我吃药",
            timezone="Mars/Olympus",
        )


def test_chat_request_accepts_one_bounded_image_without_breaking_text_only() -> None:
    text_only = schemas.ChatRequestBody(message="你好")
    assert text_only.image is None

    image_data = base64.b64encode(b"small-image-placeholder").decode("ascii")
    request = schemas.ChatRequestBody(
        message="帮我看看图片上的字",
        image={"media_type": "image/png", "data": image_data},
    )

    assert request.image is not None
    assert request.image.media_type == "image/png"
    assert request.image.detail == "original"
    assert request.image.data == image_data


@pytest.mark.parametrize(
    "image",
    [
        {"media_type": "image/gif", "data": "AA=="},
        {"media_type": "image/jpeg", "data": "not-base64"},
        {
            "media_type": "image/jpeg",
            "data": "data:image/jpeg;base64,AA==",
        },
        {"media_type": "image/png", "data": "AA==", "detail": "auto"},
    ],
)
def test_chat_request_rejects_unsupported_or_malformed_images(image) -> None:
    with pytest.raises(ValidationError):
        schemas.ChatRequestBody(message="查看图片", image=image)


def test_chat_request_rejects_image_larger_than_five_mib() -> None:
    oversized = base64.b64encode(b"x" * (MAX_CHAT_IMAGE_BYTES + 1)).decode(
        "ascii"
    )

    with pytest.raises(ValidationError):
        schemas.ChatRequestBody(
            message="查看图片",
            image={"media_type": "image/jpeg", "data": oversized},
        )


def test_feedback_requires_at_least_one_feedback_field() -> None:
    with pytest.raises(ValidationError, match="at least one feedback field"):
        schemas.FeedbackRequest(user_id="demo-user", request_id=uuid4())

    request = schemas.FeedbackRequest(
        user_id="demo-user",
        request_id=uuid4(),
        rating="up",
    )
    assert request.rating == "up"


def test_memory_models_enforce_scope_and_change_action() -> None:
    payload = memory_payload()
    memory = schemas.MemoryView.model_validate(payload)
    change = schemas.MemoryChange(
        action="updated",
        memory=memory,
        reason="用户明确修改",
    )
    assert change.memory == memory

    invalid_scope = {**payload, "scope": "global"}
    with pytest.raises(ValidationError, match="task_type='global'"):
        schemas.MemoryView.model_validate(invalid_scope)

    with pytest.raises(ValidationError, match="must not contain a memory"):
        schemas.MemoryChange(action="skipped", memory=memory, reason="无需保存")


def test_memory_update_distinguishes_omitted_and_null_fields() -> None:
    with pytest.raises(ValidationError, match="at least one memory field"):
        schemas.MemoryUpdateRequest(user_id="demo-user")

    with pytest.raises(ValidationError):
        schemas.MemoryUpdateRequest(user_id="demo-user", active=None)

    update = schemas.MemoryUpdateRequest(user_id="demo-user", active=False)
    assert update.active is False


def test_reminder_create_requires_future_aware_time_and_valid_timezone() -> None:
    future = datetime.now(UTC) + timedelta(hours=1)
    request = schemas.ReminderCreateRequest(
        user_id="demo-user",
        title="服用降压药",
        next_trigger_at=future,
    )
    assert request.repeat_type == "none"
    assert request.timezone == "Asia/Shanghai"

    with pytest.raises(ValidationError, match="in the future"):
        schemas.ReminderCreateRequest(
            user_id="demo-user",
            title="服用降压药",
            next_trigger_at=datetime.now(UTC) - timedelta(seconds=1),
        )

    with pytest.raises(ValidationError):
        schemas.ReminderCreateRequest(
            user_id="demo-user",
            title="服用降压药",
            next_trigger_at=datetime.now() + timedelta(hours=1),
        )


def test_reminder_update_requires_non_null_change() -> None:
    with pytest.raises(ValidationError, match="at least one reminder field"):
        schemas.ReminderUpdateRequest(user_id="demo-user")

    with pytest.raises(ValidationError):
        schemas.ReminderUpdateRequest(user_id="demo-user", title=None)

    update = schemas.ReminderUpdateRequest(
        user_id="demo-user",
        status="completed",
    )
    assert update.status == "completed"


def test_list_query_defaults_and_limits() -> None:
    reminders = schemas.ReminderListQuery(user_id="demo-user")
    memories = schemas.MemoryListQuery(user_id="demo-user")

    assert reminders.status == "active"
    assert reminders.limit == 50
    assert memories.active is True
    assert memories.offset == 0

    with pytest.raises(ValidationError):
        schemas.DueReminderQuery(user_id="demo-user", limit=51)


def test_list_responses_reject_total_below_items_length() -> None:
    with pytest.raises(ValidationError, match="items length"):
        schemas.MemoryListResponse(items=[memory_payload()], total=0)

    with pytest.raises(ValidationError, match="items length"):
        schemas.ReminderListResponse(items=[reminder_payload()], total=0)


def test_chat_response_matches_memory_metrics_and_tool_status() -> None:
    memory = schemas.RetrievedMemory(
        id=uuid4(),
        display_text="服药提醒时间为晚上7点",
        scope="task",
        task_type="medication",
        used=True,
    )
    base = {
        "request_id": uuid4(),
        "conversation_id": uuid4(),
        "user_message_id": uuid4(),
        "assistant_message_id": uuid4(),
        "reply": "已创建提醒。",
        "retrieved_memories": [memory],
        "memory_changes": [],
        "metrics": request_metrics_payload(),
    }

    completed = schemas.ChatResponse(
        **base,
        status="completed",
        tool_calls=[
            schemas.ToolCallView(
                tool_name="create_reminder",
                status="success",
                summary="提醒已创建",
                latency_ms=10,
            )
        ],
    )
    assert completed.status == "completed"
    assert completed.sources == []

    source = schemas.WebSource(
        title="政策通知",
        url="https://example.gov.cn/policy",
        snippet="公开政策摘要",
    )
    assert source.source == "bing"
    alternative_source = schemas.WebSource(
        title="玩家评价",
        url="https://example.com/review",
        snippet="公开评价摘要",
        source="duckduckgo",
    )
    assert alternative_source.source == "duckduckgo"

    with pytest.raises(ValidationError, match="partial responses"):
        schemas.ChatResponse(
            **base,
            status="partial",
            tool_calls=[],
        )

    with pytest.raises(ValidationError, match="cannot include tool calls"):
        schemas.ChatResponse(
            **base,
            status="needs_clarification",
            tool_calls=[
                schemas.ToolCallView(
                    tool_name="create_reminder",
                    status="success",
                    summary="不应执行",
                    latency_ms=10,
                )
            ],
        )

    bad_metrics = {**request_metrics_payload(), "used_memory_count": 0}
    with pytest.raises(ValidationError, match="used_memory_count"):
        schemas.ChatResponse(
            **{**base, "metrics": bad_metrics},
            status="completed",
            tool_calls=[],
        )


def test_metrics_query_uses_from_alias_and_checks_range() -> None:
    start = datetime.now(UTC) - timedelta(days=1)
    end = datetime.now(UTC)
    query = schemas.MetricsSummaryQuery.model_validate(
        {"user_id": "demo-user", "from": start, "to": end}
    )

    dumped = query.model_dump()
    assert dumped["from"] == start
    assert "from_" not in dumped

    with pytest.raises(ValidationError, match="earlier than from"):
        schemas.MetricsSummaryQuery.model_validate(
            {"user_id": "demo-user", "from": end, "to": start}
        )


def test_metrics_summary_rejects_impossible_counts() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError, match="cannot exceed request_count"):
        schemas.MetricsSummaryResponse.model_validate(
            {
                "request_count": 1,
                "model_call_count": 1,
                "input_tokens": 10,
                "output_tokens": 5,
                "memory_tokens": 2,
                "requests_with_retrieved_memory": 2,
                "requests_with_used_memory": 1,
                "token_metrics_complete": True,
                "average_retrieval_ms": 1.0,
                "average_model_ms": 2.0,
                "average_total_ms": 3.0,
                "from": now - timedelta(days=1),
                "to": now,
            }
        )


def test_metrics_reject_impossible_token_and_latency_totals() -> None:
    metrics = request_metrics_payload()
    metrics["total_ms"] = 110
    with pytest.raises(ValidationError, match="summed component latency"):
        schemas.RequestMetrics.model_validate(metrics)

    now = datetime.now(UTC)
    summary = {
        "request_count": 1,
        "model_call_count": 1,
        "input_tokens": 10,
        "output_tokens": 5,
        "memory_tokens": 11,
        "requests_with_retrieved_memory": 1,
        "requests_with_used_memory": 1,
        "token_metrics_complete": True,
        "average_retrieval_ms": 1.0,
        "average_model_ms": 2.0,
        "average_total_ms": 3.0,
        "from": now - timedelta(days=1),
        "to": now,
    }
    with pytest.raises(ValidationError, match="memory_tokens"):
        schemas.MetricsSummaryResponse.model_validate(summary)

    summary["memory_tokens"] = 2
    summary["average_total_ms"] = 1.0
    with pytest.raises(ValidationError, match="component averages"):
        schemas.MetricsSummaryResponse.model_validate(summary)
