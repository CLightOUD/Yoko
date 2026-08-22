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
