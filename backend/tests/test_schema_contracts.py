from __future__ import annotations

from backend.app import schemas


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
