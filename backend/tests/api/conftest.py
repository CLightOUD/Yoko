from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.agent import AgentRunResult, PendingReminderMutation
from backend.app.agent.preferences import extract_preferences
from backend.app.database import Database
from backend.app.main import create_app
from backend.app.schemas import ReminderCreateRequest, ToolCallView, WebSource


class FakeAgent:
    def __init__(self) -> None:
        self.call_count = 0
        self.last_history = []

    def run(
        self,
        *,
        user_id,
        message,
        timezone,
        now,
        memories,
        history,
        reminder_service,
        defer_mutations=False,
    ) -> AgentRunResult:
        self.call_count += 1
        self.last_history = history
        used_ids = [memories[0].id] if memories else []
        tool_calls = []
        sources = []
        pending_mutation = None
        status = "completed"
        if "信息不足" in message:
            status = "needs_clarification"
            reply = "您希望我几点提醒您？"
        elif "工具失败" in message:
            status = "partial"
            reply = "提醒未能创建，请稍后重试。"
            tool_calls = [
                ToolCallView(
                    tool_name="create_reminder",
                    status="failed",
                    summary="模拟工具失败",
                    latency_ms=1,
                )
            ]
        elif "创建每日提醒" in message:
            reminder_request = ReminderCreateRequest(
                user_id=user_id,
                title="服药",
                next_trigger_at=now + timedelta(days=1),
                timezone=timezone,
                repeat_type="daily",
            )
            reply = "已创建提醒：服药。"

            def create_reminder(connection):
                reminder_service.create(
                    reminder_request,
                    connection=connection,
                )
                return "创建每日服药提醒"

            pending_mutation = PendingReminderMutation(
                tool_name="create_reminder",
                execute=create_reminder,
                validation_reply="请重新说明提醒事项和时间。",
            )
        elif "联网查询" in message:
            reply = "已查询公开信息。"
            tool_calls = [
                ToolCallView(
                    tool_name="web_search",
                    status="success",
                    summary="模拟必应查询",
                    latency_ms=1,
                )
            ]
            sources = [
                WebSource(
                    title="公开信息",
                    url="https://example.gov.cn/information",
                    snippet="公开信息摘要",
                )
            ]
        elif memories:
            reply = f"已参考您的偏好：{memories[0].display_text}。"
        else:
            reply = "已收到您的消息。"
        return AgentRunResult(
            status=status,
            reply=reply,
            used_memory_ids=used_ids,
            tool_calls=tool_calls,
            model_call_count=1,
            input_tokens=100,
            output_tokens=20,
            memory_tokens=10 if memories else 0,
            model_ms=2,
            tool_ms=sum(call.latency_ms for call in tool_calls),
            memory_candidates=extract_preferences(message),
            sources=sources,
            pending_reminder_mutation=pending_mutation,
        )


@pytest.fixture
def api_app(tmp_path: Path) -> FastAPI:
    agent = FakeAgent()
    app = create_app(
        database=Database(tmp_path / "api.db"),
        agent=agent,
    )
    app.state.test_agent = agent
    return app


@pytest.fixture
def client(api_app: FastAPI):
    with TestClient(
        api_app,
        raise_server_exceptions=False,
        headers={"Origin": "http://127.0.0.1:5173"},
    ) as active_client:
        registered = active_client.post(
            "/api/auth/register",
            json={
                "username": "api_test_user",
                "password": "correct-horse-2026",
                "display_name": "接口测试用户",
                "timezone": "Asia/Shanghai",
            },
        )
        assert registered.status_code == 201
        api_app.state.test_user_id = registered.json()["user"]["id"]
        yield active_client
