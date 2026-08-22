from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.agent import AgentRunResult
from backend.app.database import Database
from backend.app.main import create_app
from backend.app.schemas import ReminderCreateRequest, ToolCallView


class FakeAgent:
    def __init__(self) -> None:
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
    ) -> AgentRunResult:
        self.last_history = history
        used_ids = [memories[0].id] if memories else []
        tool_calls = []
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
            reminder = reminder_service.create(
                ReminderCreateRequest(
                    user_id=user_id,
                    title="服药",
                    next_trigger_at=now + timedelta(days=1),
                    timezone=timezone,
                    repeat_type="daily",
                )
            )
            reply = f"已创建提醒：{reminder.title}。"
            tool_calls = [
                ToolCallView(
                    tool_name="create_reminder",
                    status="success",
                    summary="创建每日服药提醒",
                    latency_ms=1,
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
    with TestClient(api_app, raise_server_exceptions=False) as active_client:
        yield active_client
