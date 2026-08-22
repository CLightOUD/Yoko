from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from backend.app.database import Database
from backend.app.main import create_app


def test_openapi_contains_all_contract_operations(api_app) -> None:
    expected_operations = {
        ("get", "/api/health"),
        ("post", "/api/chat"),
        ("post", "/api/feedback"),
        ("post", "/api/reminders"),
        ("get", "/api/reminders"),
        ("get", "/api/reminders/due"),
        ("patch", "/api/reminders/{id}"),
        ("delete", "/api/reminders/{id}"),
        ("post", "/api/reminders/{id}/ack"),
        ("get", "/api/memories"),
        ("patch", "/api/memories/{id}"),
        ("delete", "/api/memories/{id}"),
        ("get", "/api/metrics/summary"),
    }
    document = api_app.openapi()
    actual_operations = {
        (method, path)
        for path, operations in document["paths"].items()
        for method in operations
        if method in {"get", "post", "patch", "delete"}
    }

    assert actual_operations == expected_operations

    for path, operations in document["paths"].items():
        for method, operation in operations.items():
            if method not in {"get", "post", "patch", "delete"}:
                continue
            for status_code, response in operation["responses"].items():
                if status_code.startswith("2"):
                    continue
                schema = response["content"]["application/json"]["schema"]
                assert schema == {"$ref": "#/components/schemas/ErrorResponse"}, (
                    path,
                    method,
                    status_code,
                )


def test_reminder_crud_and_idempotent_acknowledgement(client) -> None:
    trigger_at = datetime.now(UTC) + timedelta(days=2)
    created_response = client.post(
        "/api/reminders",
        json={
            "user_id": "demo-user",
            "title": "服药",
            "next_trigger_at": trigger_at.isoformat(),
            "timezone": "Asia/Shanghai",
            "repeat_type": "daily",
        },
    )
    assert created_response.status_code == 201
    reminder = created_response.json()
    reminder_id = reminder["id"]

    listed = client.get("/api/reminders", params={"user_id": "demo-user"})
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    updated = client.patch(
        f"/api/reminders/{reminder_id}",
        json={"user_id": "demo-user", "title": "晚上服药"},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "晚上服药"

    acknowledgement = {
        "user_id": "demo-user",
        "expected_trigger_at": reminder["next_trigger_at"],
    }
    first_ack = client.post(
        f"/api/reminders/{reminder_id}/ack", json=acknowledgement
    )
    second_ack = client.post(
        f"/api/reminders/{reminder_id}/ack", json=acknowledgement
    )
    assert first_ack.status_code == 200
    assert first_ack.json()["already_acknowledged"] is False
    assert second_ack.status_code == 200
    assert second_ack.json()["already_acknowledged"] is True
    assert second_ack.json()["reminder"]["next_trigger_at"] == first_ack.json()[
        "reminder"
    ]["next_trigger_at"]

    deleted = client.delete(
        f"/api/reminders/{reminder_id}", params={"user_id": "demo-user"}
    )
    deleted_again = client.delete(
        f"/api/reminders/{reminder_id}", params={"user_id": "demo-user"}
    )
    assert deleted.json() == {"id": reminder_id, "deleted": True}
    assert deleted_again.json() == deleted.json()


def test_validation_and_service_errors_use_error_response(client) -> None:
    invalid = client.post(
        "/api/chat",
        json={"user_id": "demo-user", "message": "   "},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_REQUEST"
    UUID(invalid.json()["request_id"])
    assert UUID(invalid.headers["X-Request-ID"]) == UUID(invalid.json()["request_id"])

    missing = client.delete(
        f"/api/reminders/{uuid4()}", params={"user_id": "demo-user"}
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_unconfigured_model_returns_documented_502(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("MODEL_NAME", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    app = create_app(database=Database(tmp_path / "no-model.db"))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/chat",
            json={"user_id": "demo-user", "message": "你好"},
        )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "MODEL_UNAVAILABLE"


def test_memory_patch_and_delete_routes(client) -> None:
    chat = client.post(
        "/api/chat",
        json={"user_id": "demo-user", "message": "你好"},
    ).json()
    feedback = client.post(
        "/api/feedback",
        json={
            "user_id": "demo-user",
            "request_id": chat["request_id"],
            "feedback_text": "以后回答简短一点",
        },
    ).json()
    memory_id = feedback["memory_changes"][0]["memory"]["id"]

    updated = client.patch(
        f"/api/memories/{memory_id}",
        json={
            "user_id": "demo-user",
            "display_text": "默认使用简短回答",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["display_text"] == "默认使用简短回答"

    deleted = client.delete(
        f"/api/memories/{memory_id}", params={"user_id": "demo-user"}
    )
    assert deleted.status_code == 200
    inactive = client.get(
        "/api/memories",
        params={"user_id": "demo-user", "active": "false"},
    )
    assert inactive.json()["total"] == 1
