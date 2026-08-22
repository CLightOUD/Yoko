from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from langchain_core.messages import AIMessage

from backend.app.agent import LangChainAgent
from backend.app.database import Database
from backend.app.schemas import ReminderCreateRequest, ReminderListQuery
from backend.app.services import MemoryService, ReminderService
from backend.app.services.errors import ModelUnavailableError


def test_langchain_agent_requires_model_configuration(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.delenv("MODEL_NAME", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    with pytest.raises(ModelUnavailableError, match="MODEL_NAME"):
        LangChainAgent._build_model()


@pytest.mark.parametrize(
    "message",
    [
        "明天上午提醒我吃药",
        "明天提醒我吃药",
        "过会儿提醒我吃药",
        "每天提醒我吃药",
    ],
)
def test_incomplete_reminder_fast_path_does_not_guess_a_time(
    monkeypatch, tmp_path, message
) -> None:
    database = Database(tmp_path / "incomplete-reminder.db")
    database.initialize()
    monkeypatch.setattr(
        LangChainAgent,
        "_build_model",
        staticmethod(lambda: pytest.fail("incomplete request should not call model")),
    )

    result = LangChainAgent().run(
        user_id="demo-user",
        message=message,
        timezone="Asia/Shanghai",
        now=datetime.now(UTC),
        memories=[],
        history=[{"role": "user", "content": message}],
        reminder_service=ReminderService(database),
    )

    assert result.status == "needs_clarification"
    assert result.tool_calls == []
    assert result.model_call_count == 0
    assert ReminderService(database).list(
        ReminderListQuery(user_id="demo-user")
    ).total == 0


def test_exact_relative_time_is_not_blocked_by_incomplete_fast_path() -> None:
    assert LangChainAgent._contains_explicit_time("30分钟后提醒我吃药") is True


def test_incomplete_followup_inherits_reminder_context(monkeypatch, tmp_path) -> None:
    database = Database(tmp_path / "incomplete-followup.db")
    database.initialize()
    monkeypatch.setattr(
        LangChainAgent,
        "_build_model",
        staticmethod(lambda: pytest.fail("incomplete followup should not call model")),
    )

    result = LangChainAgent().run(
        user_id="demo-user",
        message="下礼拜二上午",
        timezone="Asia/Shanghai",
        now=datetime.now(UTC),
        memories=[],
        history=[
            {"role": "user", "content": "提醒我去医院"},
            {"role": "assistant", "content": "请问具体哪天几点提醒您？"},
            {"role": "user", "content": "下礼拜二上午"},
        ],
        reminder_service=ReminderService(database),
    )

    assert result.status == "needs_clarification"
    assert result.model_call_count == 0
    assert result.tool_calls == []


def test_readback_of_existing_reminder_does_not_create_again(
    monkeypatch, tmp_path
) -> None:
    database = Database(tmp_path / "reminder-readback.db")
    database.initialize()
    reminders = ReminderService(database)
    reminders.create(
        ReminderCreateRequest(
            user_id="demo-user",
            title="复诊",
            next_trigger_at=datetime.now(UTC) + timedelta(days=2),
            timezone="Asia/Shanghai",
            repeat_type="none",
        )
    )
    monkeypatch.setattr(
        LangChainAgent,
        "_build_model",
        staticmethod(lambda: pytest.fail("readback should not call model")),
    )

    result = LangChainAgent().run(
        user_id="demo-user",
        message="你再说一遍，定的是哪天几点？",
        timezone="Asia/Shanghai",
        now=datetime.now(UTC),
        memories=[],
        history=[
            {"role": "user", "content": "后天晚上7点提醒我复诊"},
            {"role": "assistant", "content": "好的，提醒已经设置成功。"},
            {"role": "user", "content": "你再说一遍，定的是哪天几点？"},
        ],
        reminder_service=reminders,
    )

    assert result.status == "completed"
    assert result.model_call_count == 0
    assert result.tool_calls == []
    assert "周" in result.reply
    assert reminders.list(ReminderListQuery(user_id="demo-user")).total == 1


def test_explicit_time_cannot_be_reported_as_using_preferred_time(
    monkeypatch, tmp_path
) -> None:
    class FakeGraph:
        def invoke(self, state):
            return {
                "messages": [
                    *state["messages"],
                    AIMessage(
                        content="",
                        usage_metadata={
                            "input_tokens": 30,
                            "output_tokens": 8,
                            "total_tokens": 38,
                        },
                    ),
                ],
                "structured_response": {
                    "status": "completed",
                    "reply": "明天早上8点提醒。",
                    "used_memory_ids": [str(memory.id)],
                },
            }

    database = Database(tmp_path / "explicit-time-memory.db")
    database.initialize()
    memory = MemoryService(database).upsert(
        user_id="demo-user",
        scope="task",
        task_type="medication",
        memory_key="preferred_time",
        memory_value="19:00",
        display_text="服药提醒时间偏好为19:00",
        reason="测试",
    ).memory
    assert memory is not None
    monkeypatch.setattr(LangChainAgent, "_build_model", staticmethod(lambda: object()))
    monkeypatch.setattr(
        "backend.app.agent.runtime.create_agent",
        lambda **kwargs: FakeGraph(),
    )

    result = LangChainAgent().run(
        user_id="demo-user",
        message="明天早上8点提醒我吃药",
        timezone="Asia/Shanghai",
        now=datetime.now(UTC),
        memories=[memory],
        history=[{"role": "user", "content": "明天早上8点提醒我吃药"}],
        reminder_service=ReminderService(database),
    )

    assert result.used_memory_ids == []


def test_deepseek_model_disables_thinking_for_structured_tools(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("MODEL_NAME", "deepseek-v4-flash")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")

    model = LangChainAgent._build_model()

    assert model.extra_body == {"thinking": {"type": "disabled"}}


def test_langchain_agent_collects_usage_without_network(monkeypatch, tmp_path) -> None:
    class FakeGraph:
        def invoke(self, state):
            return {
                "messages": [
                    *state["messages"],
                    AIMessage(
                        content="",
                        usage_metadata={
                            "input_tokens": 30,
                            "output_tokens": 8,
                            "total_tokens": 38,
                        },
                    ),
                ],
                "structured_response": {
                    "status": "completed",
                    "reply": "已收到。",
                    "used_memory_ids": [],
                },
            }

    monkeypatch.setattr(LangChainAgent, "_build_model", staticmethod(lambda: object()))
    monkeypatch.setattr(
        "backend.app.agent.runtime.create_agent",
        lambda **kwargs: FakeGraph(),
    )
    database = Database(tmp_path / "agent.db")
    database.initialize()
    result = LangChainAgent().run(
        user_id="demo-user",
        message="你好",
        timezone="Asia/Shanghai",
        now=datetime.now(UTC) + timedelta(seconds=1),
        memories=[],
        history=[{"role": "user", "content": "你好"}],
        reminder_service=ReminderService(database),
    )

    assert result.status == "completed"
    assert result.model_call_count == 1
    assert result.input_tokens == 30
    assert result.output_tokens == 8
    assert result.memory_tokens == 0


def test_langchain_agent_tool_calls_service_without_http(monkeypatch, tmp_path) -> None:
    now = datetime.now(UTC)
    trigger_at = now + timedelta(days=1)

    class ToolGraph:
        def __init__(self, reminder_tool):
            self.reminder_tool = reminder_tool

        def invoke(self, state):
            self.reminder_tool.invoke(
                {
                    "title": "服药",
                    "next_trigger_at": trigger_at.isoformat(),
                    "repeat_type": "daily",
                }
            )
            return {
                "messages": [
                    *state["messages"],
                    AIMessage(
                        content="",
                        usage_metadata={
                            "input_tokens": 40,
                            "output_tokens": 10,
                            "total_tokens": 50,
                        },
                    ),
                ],
                "structured_response": {
                    "status": "needs_clarification",
                    "reply": "提醒已经创建。",
                    "used_memory_ids": [],
                },
            }

    monkeypatch.setattr(LangChainAgent, "_build_model", staticmethod(lambda: object()))
    monkeypatch.setattr(
        "backend.app.agent.runtime.create_agent",
        lambda **kwargs: ToolGraph(kwargs["tools"][0]),
    )
    database = Database(tmp_path / "agent-tool.db")
    database.initialize()
    reminders = ReminderService(database)
    result = LangChainAgent().run(
        user_id="demo-user",
        message="每天晚上8点提醒我服药",
        timezone="Asia/Shanghai",
        now=now,
        memories=[],
        history=[{"role": "user", "content": "每天晚上8点提醒我服药"}],
        reminder_service=reminders,
    )

    assert result.status == "completed"
    assert result.tool_calls[0].status == "success"
    assert reminders.list(ReminderListQuery(user_id="demo-user")).total == 1


def test_memory_reminder_fast_path_applies_preference_without_model(
    monkeypatch, tmp_path
) -> None:
    database = Database(tmp_path / "memory-fast-path.db")
    database.initialize()
    memory = MemoryService(database).upsert(
        user_id="demo-user",
        scope="task",
        task_type="medication",
        memory_key="preferred_time",
        memory_value="19:00",
        display_text="服药提醒时间偏好为19:00",
        reason="测试偏好",
    ).memory
    assert memory is not None
    reminders = ReminderService(database)
    monkeypatch.setattr(
        LangChainAgent,
        "_build_model",
        staticmethod(lambda: pytest.fail("memory fast path should not call the model")),
    )

    result = LangChainAgent().run(
        user_id="demo-user",
        message="后天提醒我吃降压药",
        timezone="Asia/Shanghai",
        now=datetime(2026, 8, 22, 12, 0, tzinfo=UTC),
        memories=[memory],
        history=[{"role": "user", "content": "后天提醒我吃降压药"}],
        reminder_service=reminders,
    )

    created = reminders.list(ReminderListQuery(user_id="demo-user")).items[0]
    assert result.status == "completed"
    assert result.model_call_count == 0
    assert result.memory_tokens == 0
    assert result.used_memory_ids == [memory.id]
    assert result.tool_calls[0].status == "success"
    assert created.next_trigger_at.astimezone(ZoneInfo("Asia/Shanghai")).hour == 19


@pytest.mark.parametrize(
    ("message", "now", "expected_date"),
    [
        (
            "周一提醒我吃降压药",
            datetime(2026, 8, 22, 12, 0, tzinfo=UTC),
            "2026-08-24",
        ),
        (
            "星期一提醒我吃降压药",
            datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
            "2026-08-31",
        ),
        (
            "下周三提醒我吃降压药",
            datetime(2026, 8, 22, 12, 0, tzinfo=UTC),
            "2026-08-26",
        ),
    ],
)
def test_memory_reminder_fast_path_resolves_weekdays_without_model(
    monkeypatch, tmp_path, message, now, expected_date
) -> None:
    database = Database(tmp_path / "weekday-fast-path.db")
    database.initialize()
    memory = MemoryService(database).upsert(
        user_id="demo-user",
        scope="task",
        task_type="medication",
        memory_key="preferred_time",
        memory_value="19:00",
        display_text="服药提醒时间偏好为19:00",
        reason="测试偏好",
    ).memory
    assert memory is not None
    reminders = ReminderService(database)
    monkeypatch.setattr(
        LangChainAgent,
        "_build_model",
        staticmethod(lambda: pytest.fail("weekday fast path should not call the model")),
    )

    result = LangChainAgent().run(
        user_id="demo-user",
        message=message,
        timezone="Asia/Shanghai",
        now=now,
        memories=[memory],
        history=[{"role": "user", "content": message}],
        reminder_service=reminders,
    )

    created = reminders.list(ReminderListQuery(user_id="demo-user")).items[0]
    local_trigger = created.next_trigger_at.astimezone(ZoneInfo("Asia/Shanghai"))
    assert result.status == "completed"
    assert result.model_call_count == 0
    assert result.used_memory_ids == [memory.id]
    assert local_trigger.date().isoformat() == expected_date
    assert local_trigger.hour == 19
    assert "周一" not in created.title
    assert "星期一" not in created.title


def test_memory_reminder_fast_path_creates_weekly_reminder(
    monkeypatch, tmp_path
) -> None:
    database = Database(tmp_path / "weekly-fast-path.db")
    database.initialize()
    memory = MemoryService(database).upsert(
        user_id="demo-user",
        scope="task",
        task_type="medication",
        memory_key="preferred_time",
        memory_value="19:00",
        display_text="服药提醒时间偏好为19:00",
        reason="测试偏好",
    ).memory
    assert memory is not None
    reminders = ReminderService(database)
    monkeypatch.setattr(
        LangChainAgent,
        "_build_model",
        staticmethod(lambda: pytest.fail("weekly fast path should not call the model")),
    )

    result = LangChainAgent().run(
        user_id="demo-user",
        message="每周一提醒我吃降压药",
        timezone="Asia/Shanghai",
        now=datetime(2026, 8, 22, 12, 0, tzinfo=UTC),
        memories=[memory],
        history=[{"role": "user", "content": "每周一提醒我吃降压药"}],
        reminder_service=reminders,
    )

    created = reminders.list(ReminderListQuery(user_id="demo-user")).items[0]
    assert result.status == "completed"
    assert result.model_call_count == 0
    assert created.repeat_type == "weekly"
    assert created.title == "吃降压药"
