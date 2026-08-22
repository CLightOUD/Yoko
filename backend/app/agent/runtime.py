from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from time import perf_counter
from typing import Literal, Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

import tiktoken
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from backend.app.schemas import (
    MemoryView,
    ReminderCreateRequest,
    ReminderListQuery,
    ToolCallView,
)
from backend.app.services.errors import ModelUnavailableError
from backend.app.services.reminder_service import ReminderService


class AgentDecision(BaseModel):
    status: Literal["completed", "needs_clarification"]
    reply: str = Field(min_length=1, max_length=10_000)
    used_memory_ids: list[UUID] = Field(default_factory=list, max_length=3)


@dataclass(frozen=True)
class AgentRunResult:
    status: Literal["completed", "needs_clarification", "partial"]
    reply: str
    used_memory_ids: list[UUID]
    tool_calls: list[ToolCallView]
    model_call_count: int
    input_tokens: int | None
    output_tokens: int | None
    memory_tokens: int
    model_ms: int
    tool_ms: int


class AgentRuntime(Protocol):
    def run(
        self,
        *,
        user_id: str,
        message: str,
        timezone: str,
        now: datetime,
        memories: list[MemoryView],
        history: list[dict],
        reminder_service: ReminderService,
    ) -> AgentRunResult: ...


class LangChainAgent:
    def run(
        self,
        *,
        user_id: str,
        message: str,
        timezone: str,
        now: datetime,
        memories: list[MemoryView],
        history: list[dict],
        reminder_service: ReminderService,
    ) -> AgentRunResult:
        fast_result = self._memory_reminder_fast_path(
            user_id=user_id,
            message=message,
            timezone=timezone,
            now=now,
            memories=memories,
            reminder_service=reminder_service,
        )
        if fast_result is not None:
            return fast_result
        readback_result = self._existing_reminder_readback_fast_path(
            user_id=user_id,
            message=message,
            timezone=timezone,
            history=history,
            reminder_service=reminder_service,
        )
        if readback_result is not None:
            return readback_result
        incomplete_result = self._incomplete_reminder_fast_path(
            message=message,
            memories=memories,
            history=history,
        )
        if incomplete_result is not None:
            return incomplete_result
        model = self._build_model()
        tool_calls: list[ToolCallView] = []

        @tool
        def create_reminder(
            title: str,
            next_trigger_at: str,
            repeat_type: Literal["none", "daily", "weekly"] = "none",
        ) -> str:
            """Create a reminder; next_trigger_at must be a future ISO 8601 time with offset."""
            started = perf_counter()
            try:
                request = ReminderCreateRequest(
                    user_id=user_id,
                    title=title,
                    next_trigger_at=next_trigger_at,
                    timezone=timezone,
                    repeat_type=repeat_type,
                )
                reminder = reminder_service.create(request)
                summary = f"已创建提醒：{reminder.title}，{reminder.next_trigger_at.isoformat()}"
                status: Literal["success", "failed"] = "success"
            except Exception as exc:
                summary = f"提醒创建失败：{exc}"
                status = "failed"
            summary = summary[:500]
            latency_ms = max(0, round((perf_counter() - started) * 1000))
            tool_calls.append(
                ToolCallView(
                    tool_name="create_reminder",
                    status=status,
                    summary=summary,
                    latency_ms=latency_ms,
                )
            )
            return summary

        memory_context = self._memory_context(memories)
        system_prompt = (
            "你是面向老年用户的陪伴与提醒助手 Yoko。回答必须清晰、简短、尊重用户。\n"
            f"当前时间：{now.isoformat()}\n用户时区：{timezone}\n"
            "只有在用户明确给出提醒事项和可确定时间时才调用 create_reminder；"
            "能结合当前时间和用户时区唯一确定的自然语言日期（例如今天、明天、后天、"
            "周一、星期三、下周五）均视为确定时间，必须自行换算并直接创建提醒，"
            "不要再询问用户确认日期。未指定前缀的星期表示最近一次尚未过去的该星期；"
            "下周表示下一个自然周。只有确实无法唯一确定必要参数时才返回 "
            "needs_clarification，且不要调用工具。"
            "‘上午’‘下午’‘晚上’‘过会儿’‘晚一点’等只表示时间范围，不是可确定钟点；"
            "没有具体钟点且没有相关时间记忆时，严禁自行选择8点、9点等默认值，必须追问。"
            "用户询问、复述或确认刚刚已经创建的提醒时，只回答现有设置，严禁再次调用工具；"
            "只有用户明确要求新增提醒时才能再次创建。"
            "用户说每天或每日时使用 repeat_type=daily；说每周、每星期或每礼拜时使用 "
            "repeat_type=weekly；其余一次性提醒使用 repeat_type=none。"
            "若相关记忆已经提供了缺失的提醒时间或表达偏好，应将其视为用户已确认的默认值，"
            "直接用于回答和工具参数，不要再次询问；用户本次明确要求始终优先于记忆。"
            "工具的 next_trigger_at 必须是包含用户时区偏移的未来 ISO 8601 时间。"
            "不要提供诊断、处方或擅自修改药量。\n"
            "下面是系统检索到的用户记忆。只应用与当前任务相关的记忆，"
            "并在 used_memory_ids 中仅返回确实影响回答或工具参数的 ID：\n"
            f"{memory_context}"
        )
        messages = self._history_messages(history)
        started = perf_counter()
        try:
            graph = create_agent(
                model=model,
                tools=[create_reminder],
                system_prompt=system_prompt,
                response_format=ToolStrategy(AgentDecision),
                name="yoko_agent",
            )
            result = graph.invoke({"messages": messages})
        except Exception as exc:
            raise ModelUnavailableError(f"模型调用失败：{exc}") from exc
        elapsed_ms = max(0, round((perf_counter() - started) * 1000))

        structured = result.get("structured_response")
        if structured is None:
            raise ModelUnavailableError("模型未返回有效的结构化结果")
        decision = AgentDecision.model_validate(structured)
        available_ids = {memory.id for memory in memories}
        overridden_ids = (
            {
                memory.id
                for memory in memories
                if memory.memory_key == "preferred_time"
            }
            if self._contains_clock_time(message)
            else set()
        )
        used_ids = [
            memory_id
            for memory_id in dict.fromkeys(decision.used_memory_ids)
            if memory_id in available_ids and memory_id not in overridden_ids
        ]
        failed_tool = any(call.status == "failed" for call in tool_calls)
        if failed_tool:
            status: Literal["completed", "needs_clarification", "partial"] = "partial"
        elif tool_calls:
            status = "completed"
        else:
            status = decision.status
        reply = decision.reply
        if failed_tool and "未" not in reply and "失败" not in reply:
            reply = f"部分操作未完成。{reply}"

        new_messages = result.get("messages", [])[len(messages) :]
        model_call_count, input_tokens, output_tokens = self._usage(new_messages)
        tool_ms = sum(call.latency_ms for call in tool_calls)
        model_ms = max(0, elapsed_ms - tool_ms)
        memory_tokens = (
            self._count_tokens(memory_context, os.getenv("MODEL_NAME"))
            if memories
            else 0
        )
        if input_tokens is not None:
            memory_tokens = min(memory_tokens, input_tokens)
        return AgentRunResult(
            status=status,
            reply=reply,
            used_memory_ids=used_ids,
            tool_calls=tool_calls,
            model_call_count=max(1, model_call_count),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            memory_tokens=memory_tokens,
            model_ms=model_ms,
            tool_ms=tool_ms,
        )

    @staticmethod
    def _incomplete_reminder_fast_path(
        *,
        message: str,
        memories: list[MemoryView],
        history: list[dict],
    ) -> AgentRunResult | None:
        reminder_context = "提醒" in message or (
            LangChainAgent._previous_assistant_requested_time(history)
            and LangChainAgent._contains_date_or_time_range(message)
        )
        if not reminder_context or LangChainAgent._contains_explicit_time(message):
            return None
        if any(memory.memory_key == "preferred_time" for memory in memories):
            return None
        if any(
            marker in message
            for marker in ("加倍", "减量", "停药", "换药", "头晕", "不舒服")
        ):
            return None
        return AgentRunResult(
            status="needs_clarification",
            reply="好的。请再告诉我具体几点提醒您。",
            used_memory_ids=[],
            tool_calls=[],
            model_call_count=0,
            input_tokens=None,
            output_tokens=None,
            memory_tokens=0,
            model_ms=0,
            tool_ms=0,
        )

    @staticmethod
    def _existing_reminder_readback_fast_path(
        *,
        user_id: str,
        message: str,
        timezone: str,
        history: list[dict],
        reminder_service: ReminderService,
    ) -> AgentRunResult | None:
        previous_assistant = next(
            (
                item["content"]
                for item in reversed(history[:-1])
                if item["role"] == "assistant"
            ),
            None,
        )
        if (
            previous_assistant is None
            or "提醒" not in previous_assistant
            or not any(marker in previous_assistant for marker in ("已", "成功", "设置"))
        ):
            return None
        no_action = any(
            marker in message
            for marker in ("别再建", "不要再建", "不用再建", "只确认", "别改")
        )
        readback = any(
            marker in message
            for marker in ("哪天", "几点", "什么时候", "再说一遍", "刚才说的")
        )
        if not no_action and not readback:
            return None

        if no_action and not readback:
            reply = "好的，保留刚才的提醒，不再重复创建。"
        else:
            reminders = reminder_service.list(
                ReminderListQuery(user_id=user_id, limit=100)
            ).items
            if not reminders:
                return None
            latest = max(reminders, key=lambda item: (item.created_at, item.id.hex))
            local = latest.next_trigger_at.astimezone(ZoneInfo(timezone))
            weekday = "一二三四五六日"[local.weekday()]
            repeat = {"none": "一次性", "daily": "每天", "weekly": "每周"}[
                latest.repeat_type
            ]
            reply = (
                f"刚才设置的是{repeat}提醒：{local:%Y年%m月%d日}周{weekday} "
                f"{local:%H:%M}，"
                f"提醒您{latest.title}。"
            )
        return AgentRunResult(
            status="completed",
            reply=reply,
            used_memory_ids=[],
            tool_calls=[],
            model_call_count=0,
            input_tokens=None,
            output_tokens=None,
            memory_tokens=0,
            model_ms=0,
            tool_ms=0,
        )

    @staticmethod
    def _previous_assistant_requested_time(history: list[dict]) -> bool:
        previous_assistant = next(
            (
                item["content"]
                for item in reversed(history[:-1])
                if item["role"] == "assistant"
            ),
            "",
        )
        return any(
            marker in previous_assistant
            for marker in ("几点", "什么时候", "具体时间", "具体钟点")
        )

    @staticmethod
    def _contains_date_or_time_range(message: str) -> bool:
        return bool(
            re.search(
                r"今天|明天|后天|周|星期|礼拜|上午|下午|晚上|早上|早晨|中午|"
                r"过会儿|晚一点",
                message,
            )
        )

    @staticmethod
    def _memory_reminder_fast_path(
        *,
        user_id: str,
        message: str,
        timezone: str,
        now: datetime,
        memories: list[MemoryView],
        reminder_service: ReminderService,
    ) -> AgentRunResult | None:
        if "提醒" not in message or LangChainAgent._contains_clock_time(message):
            return None
        preferred = next(
            (memory for memory in memories if memory.memory_key == "preferred_time"),
            None,
        )
        if preferred is None:
            return None
        time_match = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", preferred.memory_value)
        if time_match is None:
            return None

        if any(marker in message for marker in ("每周", "每星期", "每个星期", "每礼拜", "每个礼拜")):
            repeat_type: Literal["none", "daily", "weekly"] = "weekly"
        elif any(marker in message for marker in ("每天", "每日")):
            repeat_type = "daily"
        else:
            repeat_type = "none"
        zone = ZoneInfo(timezone)
        local_now = now.astimezone(zone)
        trigger_time = time(int(time_match.group(1)), int(time_match.group(2)))
        day_offset = LangChainAgent._resolve_day_offset(
            message=message,
            local_now=local_now,
            trigger_time=trigger_time,
            repeat_type=repeat_type,
        )
        if day_offset is None:
            return None
        trigger_date = local_now.date() + timedelta(days=day_offset)
        trigger_at = datetime.combine(trigger_date, trigger_time, tzinfo=zone)
        if trigger_at <= local_now:
            if repeat_type in ("daily", "weekly"):
                trigger_at += timedelta(days=1 if repeat_type == "daily" else 7)
            else:
                return None

        title = re.sub(
            r"今天|明天|后天|每天|每日|(?:每|下|本)?(?:周|星期|礼拜)[一二三四五六日天1-7]"
            r"|请|帮我|提醒我|提醒",
            "",
            message,
        ).strip(" ，。,.！!")
        title = title or {
            "medication": "服药",
            "walking": "散步",
            "appointment": "预约",
        }.get(preferred.task_type, "待办事项")

        started = perf_counter()
        try:
            reminder = reminder_service.create(
                ReminderCreateRequest(
                    user_id=user_id,
                    title=title,
                    next_trigger_at=trigger_at,
                    timezone=timezone,
                    repeat_type=repeat_type,
                )
            )
            summary = f"已使用偏好创建提醒：{title}，{trigger_at.isoformat()}"[:500]
            call_status: Literal["success", "failed"] = "success"
            status: Literal["completed", "needs_clarification", "partial"] = "completed"
            reply = (
                f"好的，已按您的习惯设置提醒：{trigger_at.month}月{trigger_at.day}日"
                f" {trigger_at:%H:%M} 提醒您{reminder.title}。"
            )
        except Exception as exc:
            summary = f"提醒创建失败：{exc}"[:500]
            call_status = "failed"
            status = "partial"
            reply = "提醒暂时未能创建，请稍后重试。"
        tool_ms = max(0, round((perf_counter() - started) * 1000))
        return AgentRunResult(
            status=status,
            reply=reply,
            used_memory_ids=[preferred.id],
            tool_calls=[
                ToolCallView(
                    tool_name="create_reminder",
                    status=call_status,
                    summary=summary,
                    latency_ms=tool_ms,
                )
            ],
            model_call_count=0,
            input_tokens=None,
            output_tokens=None,
            memory_tokens=0,
            model_ms=0,
            tool_ms=tool_ms,
        )

    @staticmethod
    def _resolve_day_offset(
        *,
        message: str,
        local_now: datetime,
        trigger_time: time,
        repeat_type: Literal["none", "daily", "weekly"],
    ) -> int | None:
        if "后天" in message:
            return 2
        if "明天" in message:
            return 1
        if "今天" in message:
            return 0

        weekday_match = re.search(
            r"(?P<prefix>每|下|本)?(?:周|星期|礼拜)"
            r"(?P<weekday>[一二三四五六日天1-7])",
            message,
        )
        if weekday_match is not None:
            weekday_values = {
                "一": 0,
                "二": 1,
                "三": 2,
                "四": 3,
                "五": 4,
                "六": 5,
                "日": 6,
                "天": 6,
                "1": 0,
                "2": 1,
                "3": 2,
                "4": 3,
                "5": 4,
                "6": 5,
                "7": 6,
            }
            target_weekday = weekday_values[weekday_match.group("weekday")]
            prefix = weekday_match.group("prefix")
            if prefix == "下":
                return 7 - local_now.weekday() + target_weekday
            if prefix == "本":
                offset = target_weekday - local_now.weekday()
                if offset < 0:
                    return None
                if offset == 0 and trigger_time <= local_now.timetz().replace(tzinfo=None):
                    return None
                return offset

            offset = (target_weekday - local_now.weekday()) % 7
            if offset == 0 and trigger_time <= local_now.timetz().replace(tzinfo=None):
                return 7
            return offset

        if repeat_type == "daily":
            return 0
        return None

    @staticmethod
    def _contains_clock_time(message: str) -> bool:
        return bool(
            re.search(
                r"(?:\d{1,2}|[零一二两三四五六七八九十]{1,3})\s*"
                r"(?:点|时|[:：])",
                message,
            )
        )

    @staticmethod
    def _contains_explicit_time(message: str) -> bool:
        if LangChainAgent._contains_clock_time(message):
            return True
        return bool(
            re.search(
                r"(?:\d{1,3}|[一二两三四五六七八九十百]{1,3})\s*"
                r"(?:分钟|小时)后",
                message,
            )
        )

    @staticmethod
    def _build_model() -> ChatOpenAI:
        provider = os.getenv("MODEL_PROVIDER", "openai").strip().lower()
        model_name = os.getenv("MODEL_NAME", "").strip()
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
        if provider != "openai":
            raise ModelUnavailableError(f"暂不支持模型供应商：{provider}")
        if not model_name:
            raise ModelUnavailableError("未配置 MODEL_NAME")
        if not api_key and base_url is None:
            raise ModelUnavailableError("未配置 OPENAI_API_KEY")
        options = {}
        if base_url is not None and "api.deepseek.com" in base_url.lower():
            options["extra_body"] = {"thinking": {"type": "disabled"}}
        return ChatOpenAI(
            model=model_name,
            api_key=api_key or "not-required",
            base_url=base_url,
            temperature=0,
            max_retries=1,
            timeout=30,
            **options,
        )

    @staticmethod
    def _memory_context(memories: list[MemoryView]) -> str:
        if not memories:
            return "（没有相关记忆）"
        return "\n".join(
            f"- [{memory.id}] {memory.display_text}" for memory in memories
        )

    @staticmethod
    def _history_messages(history: list[dict]) -> list:
        converted = []
        for item in history:
            role = item["role"]
            content = item["content"]
            if role == "assistant":
                converted.append(AIMessage(content=content))
            elif role == "system":
                converted.append(SystemMessage(content=content))
            else:
                converted.append(HumanMessage(content=content))
        return converted

    @staticmethod
    def _usage(messages: list) -> tuple[int, int | None, int | None]:
        ai_messages = [message for message in messages if isinstance(message, AIMessage)]
        if not ai_messages:
            return 0, None, None
        input_total = 0
        output_total = 0
        complete = True
        for message in ai_messages:
            usage = message.usage_metadata
            if not usage:
                complete = False
                continue
            input_total += int(usage.get("input_tokens", 0))
            output_total += int(usage.get("output_tokens", 0))
        return (
            len(ai_messages),
            input_total if complete else None,
            output_total if complete else None,
        )

    @staticmethod
    def _count_tokens(text: str, model_name: str | None) -> int:
        try:
            encoding = tiktoken.encoding_for_model(model_name or "gpt-4o-mini")
        except Exception:
            try:
                encoding = tiktoken.get_encoding("cl100k_base")
            except Exception:
                return max(1, len(text))
        return len(encoding.encode(text))
