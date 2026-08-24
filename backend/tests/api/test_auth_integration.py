from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from backend.app.database import Database
from backend.app.main import create_app


def test_business_routes_require_a_valid_session(tmp_path) -> None:
    app = create_app(database=Database(tmp_path / "unauthenticated.db"))
    with TestClient(
        app,
        raise_server_exceptions=False,
        headers={"Origin": "http://127.0.0.1:5173"},
    ) as client:
        response = client.get("/api/reminders")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_session_identity_ignores_client_user_id_and_isolates_accounts(client) -> None:
    first_user_id = client.app.state.test_user_id
    trigger_at = datetime.now(UTC) + timedelta(days=2)
    reminder = client.post(
        "/api/reminders",
        json={
            "user_id": "demo-user",
            "title": "第一位用户的提醒",
            "next_trigger_at": trigger_at.isoformat(),
            "timezone": "Asia/Shanghai",
            "repeat_type": "none",
        },
    )
    assert reminder.status_code == 201
    assert reminder.json()["user_id"] == first_user_id

    chat = client.post(
        "/api/chat",
        json={"user_id": "demo-user", "message": "你好"},
    )
    assert chat.status_code == 200
    feedback = client.post(
        "/api/feedback",
        json={
            "user_id": "demo-user",
            "request_id": chat.json()["request_id"],
            "feedback_text": "以后回答简短一点",
        },
    )
    assert feedback.status_code == 200
    memory_id = feedback.json()["memory_changes"][0]["memory"]["id"]

    second = client.post(
        "/api/auth/register",
        json={
            "username": "second_api_user",
            "password": "correct-horse-2026",
            "display_name": "第二位用户",
            "timezone": "Asia/Shanghai",
        },
    )
    assert second.status_code == 201
    second_user_id = second.json()["user"]["id"]
    assert second_user_id != first_user_id

    assert client.get(
        "/api/reminders", params={"user_id": first_user_id}
    ).json()["total"] == 0
    assert client.get(
        "/api/memories", params={"user_id": first_user_id}
    ).json()["total"] == 0
    assert client.get(
        "/api/metrics/summary", params={"user_id": first_user_id}
    ).json()["request_count"] == 0

    assert client.patch(
        f"/api/reminders/{reminder.json()['id']}",
        json={"user_id": first_user_id, "title": "越权修改"},
    ).status_code == 404
    assert client.patch(
        f"/api/memories/{memory_id}",
        json={"user_id": first_user_id, "display_text": "越权修改"},
    ).status_code == 404
    assert client.post(
        "/api/feedback",
        json={
            "user_id": first_user_id,
            "request_id": chat.json()["request_id"],
            "rating": "down",
        },
    ).status_code == 404

    prior_agent_calls = client.app.state.test_agent.call_count
    isolated_chat = client.post(
        "/api/chat",
        json={
            "user_id": first_user_id,
            "conversation_id": chat.json()["conversation_id"],
            "message": "第二位用户的新消息",
        },
    )
    assert isolated_chat.status_code == 404
    assert isolated_chat.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert client.app.state.test_agent.call_count == prior_agent_calls


def test_authenticated_write_rejects_untrusted_origin(client) -> None:
    response = client.post(
        "/api/chat",
        headers={"Origin": "https://attacker.example"},
        json={"message": "你好"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"


def test_openapi_does_not_accept_client_user_id(api_app) -> None:
    document = api_app.openapi()
    body_operations = (
        ("/api/chat", "post"),
        ("/api/feedback", "post"),
        ("/api/reminders", "post"),
        ("/api/reminders/{id}", "patch"),
        ("/api/reminders/{id}/ack", "post"),
        ("/api/memories/{id}", "patch"),
    )
    for path, method in body_operations:
        schema = document["paths"][path][method]["requestBody"]["content"][
            "application/json"
        ]["schema"]
        reference = schema["$ref"].rsplit("/", 1)[-1]
        properties = document["components"]["schemas"][reference]["properties"]
        assert "user_id" not in properties, (path, method)

    for path in (
        "/api/reminders",
        "/api/reminders/due",
        "/api/memories",
        "/api/metrics/summary",
    ):
        names = {
            parameter["name"]
            for parameter in document["paths"][path]["get"].get("parameters", [])
        }
        assert "user_id" not in names, path

    for path in ("/api/reminders/{id}", "/api/memories/{id}"):
        names = {
            parameter["name"]
            for parameter in document["paths"][path]["delete"].get(
                "parameters", []
            )
        }
        assert "user_id" not in names, path
