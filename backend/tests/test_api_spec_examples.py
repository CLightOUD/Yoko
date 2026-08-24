from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from backend.app import schemas


API_SPEC_PATH = Path(__file__).parents[2] / "API_SPEC.md"
JSON_BLOCK_PATTERN = re.compile(r"^```json\s*\n(.*?)^```\s*$", re.MULTILINE | re.DOTALL)


def models_for_example(data: dict[str, Any]) -> tuple[type[BaseModel], ...]:
    keys = set(data)

    if "error" in keys:
        return (schemas.ErrorResponse,)
    if keys == {"username", "password", "display_name", "timezone"}:
        return (schemas.RegisterRequest,)
    if keys == {"username", "password"}:
        return (schemas.LoginRequest,)
    if keys == {"user", "session_expires_at"}:
        return (schemas.AuthResponse,)
    if keys == {"logged_out"}:
        return (schemas.LogoutResponse,)
    if keys == {"status"}:
        return (schemas.HealthResponse,)
    if keys == {"id", "deleted"}:
        return (schemas.DeleteResponse,)
    if "request_count" in keys:
        return (schemas.MetricsSummaryResponse,)
    if "request_id" in keys and "conversation_id" in keys:
        return (schemas.ChatResponse,)
    if "message" in keys:
        return (schemas.ChatRequestBody,)
    if "feedback_id" in keys:
        return (schemas.FeedbackResponse,)
    if "feedback_text" in keys or "corrected_reply" in keys or "rating" in keys:
        return (schemas.FeedbackRequestBody,)
    if "reminder" in keys and "already_acknowledged" in keys:
        return (schemas.ReminderAckResponse,)
    if keys == {"expected_trigger_at"}:
        return (schemas.ReminderAckBody,)
    if keys == {"items", "total"}:
        return (schemas.ReminderListResponse, schemas.MemoryListResponse)
    if "memory_value" in keys and "id" not in keys:
        return (schemas.MemoryUpdateBody,)
    if "next_trigger_at" in keys and "id" not in keys:
        if "status" in keys:
            return (schemas.ReminderUpdateBody,)
        return (schemas.ReminderCreateBody,)
    if "next_trigger_at" in keys and "id" in keys:
        return (schemas.ReminderView,)
    if "memory_key" in keys:
        return (schemas.MemoryView,)
    if keys == {"id", "display_text", "scope", "task_type", "used"}:
        return (schemas.RetrievedMemory,)
    if "retrieved_memory_count" in keys:
        return (schemas.RequestMetrics,)

    raise AssertionError(f"unmapped API example with keys: {sorted(keys)}")


def test_all_api_spec_json_examples_match_pydantic_models() -> None:
    content = API_SPEC_PATH.read_text(encoding="utf-8")
    blocks = JSON_BLOCK_PATTERN.findall(content)

    assert len(blocks) == 27

    for block in blocks:
        data = json.loads(block)
        models = models_for_example(data)

        if any(
            model in {schemas.ReminderCreateBody, schemas.ReminderUpdateBody}
            for model in models
        ):
            data["next_trigger_at"] = datetime.now(UTC) + timedelta(days=1)

        for model in models:
            model.model_validate(data)


def test_patch_json_schemas_allow_omission_but_not_null() -> None:
    memory_schema = schemas.MemoryUpdateRequest.model_json_schema()
    reminder_schema = schemas.ReminderUpdateRequest.model_json_schema()

    assert memory_schema["required"] == ["user_id"]
    assert reminder_schema["required"] == ["user_id"]
    assert memory_schema["properties"]["active"]["type"] == "boolean"
    assert reminder_schema["properties"]["title"]["type"] == "string"


def test_response_models_keep_nullable_fields_required() -> None:
    expected_required = {
        schemas.ErrorDetail: {"code", "message", "details"},
        schemas.MemoryView: {
            "id",
            "scope",
            "task_type",
            "memory_key",
            "memory_value",
            "display_text",
            "active",
            "source_message_id",
            "created_at",
            "updated_at",
            "last_used_at",
        },
        schemas.ReminderView: {
            "id",
            "user_id",
            "title",
            "next_trigger_at",
            "timezone",
            "repeat_type",
            "status",
            "last_triggered_at",
            "created_at",
            "updated_at",
        },
        schemas.RequestMetrics: {
            "model_call_count",
            "input_tokens",
            "output_tokens",
            "memory_tokens",
            "retrieved_memory_count",
            "used_memory_count",
            "retrieval_ms",
            "model_ms",
            "tool_ms",
            "total_ms",
        },
        schemas.FeedbackMetrics: {
            "model_call_count",
            "input_tokens",
            "output_tokens",
            "total_ms",
        },
        schemas.MetricsSummaryResponse: {
            "request_count",
            "model_call_count",
            "input_tokens",
            "output_tokens",
            "memory_tokens",
            "requests_with_retrieved_memory",
            "requests_with_used_memory",
            "token_metrics_complete",
            "average_retrieval_ms",
            "average_model_ms",
            "average_total_ms",
            "from",
            "to",
        },
    }

    for model, required in expected_required.items():
        assert set(model.model_json_schema()["required"]) == required
