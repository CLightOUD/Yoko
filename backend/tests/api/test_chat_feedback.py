from datetime import UTC, datetime, timedelta

from backend.app.schemas import ChatRequest


def test_feedback_memory_is_retrieved_and_used_by_later_chat(client) -> None:
    first = client.post(
        "/api/chat",
        json={"user_id": "demo-user", "message": "你好"},
    )
    assert first.status_code == 200
    request_id = first.json()["request_id"]

    feedback_payload = {
        "user_id": "demo-user",
        "request_id": request_id,
        "feedback_text": "太晚了，以后服药都在晚上7点提醒",
        "rating": "down",
    }
    feedback = client.post("/api/feedback", json=feedback_payload)
    duplicate = client.post("/api/feedback", json=feedback_payload)
    assert feedback.status_code == 200
    assert feedback.json()["memory_changes"][0]["action"] == "created"
    assert feedback.json()["memory_changes"][0]["memory"]["memory_value"] == "19:00"
    assert duplicate.status_code == 200
    assert duplicate.json()["feedback_id"] == feedback.json()["feedback_id"]
    assert duplicate.json()["feedback_message_id"] == feedback.json()[
        "feedback_message_id"
    ]

    second = client.post(
        "/api/chat",
        json={"user_id": "demo-user", "message": "明天提醒我吃降压药"},
    )
    assert second.status_code == 200
    result = second.json()
    assert result["retrieved_memories"][0]["used"] is True
    assert "19:00" in result["reply"]
    assert result["metrics"]["retrieved_memory_count"] == 1
    assert result["metrics"]["used_memory_count"] == 1
    assert result["metrics"]["memory_tokens"] == 10

    summary = client.get(
        "/api/metrics/summary", params={"user_id": "demo-user"}
    )
    assert summary.status_code == 200
    assert summary.json()["request_count"] == 2
    assert summary.json()["requests_with_retrieved_memory"] == 1
    assert summary.json()["requests_with_used_memory"] == 1


def test_rating_only_feedback_is_recorded_without_memory(client) -> None:
    chat = client.post(
        "/api/chat",
        json={"user_id": "demo-user", "message": "你好"},
    ).json()
    feedback = client.post(
        "/api/feedback",
        json={
            "user_id": "demo-user",
            "request_id": chat["request_id"],
            "rating": "up",
        },
    )
    assert feedback.status_code == 200
    assert feedback.json()["memory_changes"] == [
        {
            "action": "skipped",
            "memory": None,
            "reason": "反馈未包含明确且长期适用的偏好",
        }
    ]


def test_compound_feedback_writes_and_deduplicates_multiple_memories(client) -> None:
    chat = client.post(
        "/api/chat",
        json={"user_id": "demo-user", "message": "你好"},
    ).json()
    payload = {
        "user_id": "demo-user",
        "request_id": chat["request_id"],
        "feedback_text": (
            "以后回答简短一点，并且服药都在晚上7点提醒，默认使用中文"
        ),
    }

    created = client.post("/api/feedback", json=payload)
    duplicate = client.post("/api/feedback", json=payload)

    assert created.status_code == 200
    assert duplicate.status_code == 200
    assert len(created.json()["memory_changes"]) == 3
    assert len(duplicate.json()["memory_changes"]) == 3
    assert {
        change["memory"]["memory_key"]
        for change in created.json()["memory_changes"]
    } == {"response_style", "preferred_time", "language"}
    memories = client.get("/api/memories", params={"user_id": "demo-user"})
    assert memories.status_code == 200
    assert memories.json()["total"] == 3


def test_chat_statuses_and_agent_tool_side_effect(client) -> None:
    clarification = client.post(
        "/api/chat",
        json={"user_id": "demo-user", "message": "信息不足"},
    )
    assert clarification.json()["status"] == "needs_clarification"
    assert clarification.json()["tool_calls"] == []

    partial = client.post(
        "/api/chat",
        json={"user_id": "demo-user", "message": "工具失败"},
    )
    assert partial.json()["status"] == "partial"
    assert partial.json()["tool_calls"][0]["status"] == "failed"

    created = client.post(
        "/api/chat",
        json={"user_id": "demo-user", "message": "创建每日提醒"},
    )
    assert created.json()["status"] == "completed"
    assert created.json()["tool_calls"][0]["status"] == "success"
    reminders = client.get("/api/reminders", params={"user_id": "demo-user"})
    assert reminders.json()["total"] == 1


def test_feedback_rejects_request_owned_by_no_user(client) -> None:
    response = client.post(
        "/api/feedback",
        json={
            "user_id": "demo-user",
            "request_id": "64e7398e-811a-4b2c-b301-e46ad4d180ba",
            "rating": "down",
        },
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_chat_sends_only_six_recent_messages_to_agent(client) -> None:
    conversation_id = None
    for index in range(5):
        payload = {
            "user_id": "demo-user",
            "conversation_id": conversation_id,
            "message": f"第{index + 1}条消息",
        }
        response = client.post("/api/chat", json=payload)
        assert response.status_code == 200
        conversation_id = response.json()["conversation_id"]

    history = client.app.state.test_agent.last_history
    assert len(history) == 5
    assert history[0]["role"] == "user"
    assert history[-1]["content"] == "第5条消息"
    assert all(item["content"] != "第1条消息" for item in history)


def test_chat_idempotency_returns_cached_response_without_duplicate_writes(client) -> None:
    payload = {"user_id": "demo-user", "message": "同一请求只处理一次"}
    headers = {"Idempotency-Key": "chat-request-0001"}

    first = client.post("/api/chat", json=payload, headers=headers)
    second = client.post("/api/chat", json=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert client.app.state.test_agent.call_count == 1
    with client.app.state.database.connection() as connection:
        message_count = connection.execute(
            "SELECT COUNT(*) FROM messages WHERE request_id = ?",
            (first.json()["request_id"],),
        ).fetchone()[0]
        metric_count = connection.execute(
            "SELECT COUNT(*) FROM request_metrics WHERE request_id = ?",
            (first.json()["request_id"],),
        ).fetchone()[0]
        request_row = connection.execute(
            "SELECT status, attempt_count FROM chat_requests WHERE id = ?",
            (first.json()["request_id"],),
        ).fetchone()

    assert message_count == 2
    assert metric_count == 1
    assert dict(request_row) == {"status": "completed", "attempt_count": 1}


def test_chat_idempotency_rejects_reusing_key_for_different_payload(client) -> None:
    headers = {"Idempotency-Key": "chat-request-0002"}
    first = client.post(
        "/api/chat",
        json={"user_id": "demo-user", "message": "第一条"},
        headers=headers,
    )
    conflict = client.post(
        "/api/chat",
        json={"user_id": "demo-user", "message": "第二条"},
        headers=headers,
    )

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "RESOURCE_CONFLICT"


def test_failed_chat_retry_reuses_user_message_and_request_id(client, monkeypatch) -> None:
    agent = client.app.state.test_agent
    original_run = agent.run
    attempts = 0

    def fail_once(**kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("simulated agent failure")
        return original_run(**kwargs)

    monkeypatch.setattr(agent, "run", fail_once)
    payload = {"user_id": "demo-user", "message": "失败后安全重试"}
    headers = {"Idempotency-Key": "chat-request-0003"}

    failed = client.post("/api/chat", json=payload, headers=headers)
    recovered = client.post("/api/chat", json=payload, headers=headers)

    assert failed.status_code == 500
    assert recovered.status_code == 200
    with client.app.state.database.connection() as connection:
        request_row = connection.execute(
            """
            SELECT id, status, attempt_count FROM chat_requests
            WHERE idempotency_key = ?
            """,
            (headers["Idempotency-Key"],),
        ).fetchone()
        user_message_count = connection.execute(
            """
            SELECT COUNT(*) FROM messages
            WHERE request_id = ? AND role = 'user'
            """,
            (request_row["id"],),
        ).fetchone()[0]

    assert recovered.json()["request_id"] == request_row["id"]
    assert request_row["status"] == "completed"
    assert request_row["attempt_count"] == 2
    assert user_message_count == 1


def test_chat_finalization_rolls_back_and_can_retry(client, monkeypatch) -> None:
    metrics_service = client.app.state.metrics_service
    original_record = metrics_service.record
    attempts = 0

    def fail_once(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("simulated metrics failure")
        return original_record(*args, **kwargs)

    monkeypatch.setattr(metrics_service, "record", fail_once)
    payload = {
        "user_id": "demo-user",
        "message": "以后回答简短一点",
    }
    headers = {"Idempotency-Key": "chat-request-0004"}

    failed = client.post("/api/chat", json=payload, headers=headers)
    with client.app.state.database.connection() as connection:
        failed_row = connection.execute(
            "SELECT id, status FROM chat_requests WHERE idempotency_key = ?",
            (headers["Idempotency-Key"],),
        ).fetchone()
        assistant_count = connection.execute(
            "SELECT COUNT(*) FROM messages WHERE request_id = ? AND role = 'assistant'",
            (failed_row["id"],),
        ).fetchone()[0]
        memory_count = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        metric_count = connection.execute(
            "SELECT COUNT(*) FROM request_metrics WHERE request_id = ?",
            (failed_row["id"],),
        ).fetchone()[0]

    recovered = client.post("/api/chat", json=payload, headers=headers)

    assert failed.status_code == 500
    assert failed_row["status"] == "failed"
    assert assistant_count == 0
    assert memory_count == 0
    assert metric_count == 0
    assert recovered.status_code == 200
    assert recovered.json()["memory_changes"][0]["action"] == "created"


def test_pending_chat_conflicts_until_lease_expires_then_recovers(client) -> None:
    payload = {"user_id": "demo-user", "message": "租约恢复测试"}
    key = "chat-request-0005"
    execution = client.app.state.chat_service._begin(
        ChatRequest.model_validate(payload),
        idempotency_key=key,
    )

    conflict = client.post(
        "/api/chat",
        json=payload,
        headers={"Idempotency-Key": key},
    )
    assert conflict.status_code == 409
    assert client.app.state.test_agent.call_count == 0

    with client.app.state.database.transaction() as connection:
        connection.execute(
            "UPDATE chat_requests SET lease_expires_at = ? WHERE id = ?",
            ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(), str(execution.request_id)),
        )

    recovered = client.post(
        "/api/chat",
        json=payload,
        headers={"Idempotency-Key": key},
    )

    assert recovered.status_code == 200
    assert recovered.json()["request_id"] == str(execution.request_id)
    assert client.app.state.test_agent.call_count == 1
