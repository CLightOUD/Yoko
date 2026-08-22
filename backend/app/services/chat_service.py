from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from backend.app.agent import AgentRuntime
from backend.app.agent.preferences import classify_task, extract_preferences
from backend.app.database import Database
from backend.app.repositories import MessageRepository, UserRepository
from backend.app.schemas import (
    ChatRequest,
    ChatResponse,
    RequestMetrics,
    RetrievedMemory,
)
from backend.app.services.errors import ResourceNotFoundError
from backend.app.services.memory_service import MemoryService
from backend.app.services.metrics_service import MetricsService
from backend.app.services.reminder_service import ReminderService


class ChatService:
    HISTORY_MESSAGE_LIMIT = 6

    def __init__(
        self,
        database: Database,
        *,
        memory_service: MemoryService,
        reminder_service: ReminderService,
        metrics_service: MetricsService,
        agent: AgentRuntime,
    ) -> None:
        self.database = database
        self.memory_service = memory_service
        self.reminder_service = reminder_service
        self.metrics_service = metrics_service
        self.agent = agent
        self.messages = MessageRepository(database)
        self.users = UserRepository(database)

    def run(self, request: ChatRequest) -> ChatResponse:
        overall_started = perf_counter()
        user = self.users.get(request.user_id)
        if user is None:
            raise ResourceNotFoundError("用户不存在")

        if request.conversation_id is None:
            conversation_id = uuid4()
        else:
            conversation_id = request.conversation_id
            if not self.messages.conversation_belongs_to_user(
                str(conversation_id), request.user_id
            ):
                raise ResourceNotFoundError("会话不存在")

        request_id = uuid4()
        user_message = self.messages.create(
            user_id=request.user_id,
            conversation_id=str(conversation_id),
            role="user",
            content=request.message,
            request_id=str(request_id),
        )

        task_type = classify_task(request.message)
        retrieval_started = perf_counter()
        memories = self.memory_service.retrieve(
            user_id=request.user_id,
            task_type=task_type,
            limit=3,
        )
        retrieval_ms = max(0, round((perf_counter() - retrieval_started) * 1000))
        history = self.messages.list_recent(
            user_id=request.user_id,
            conversation_id=str(conversation_id),
            limit=self.HISTORY_MESSAGE_LIMIT,
        )
        if history and history[0]["role"] == "assistant":
            history = history[1:]
        timezone = request.timezone or user["timezone"] or "Asia/Shanghai"
        local_now = datetime.now(UTC).astimezone(ZoneInfo(timezone))
        agent_result = self.agent.run(
            user_id=request.user_id,
            message=request.message,
            timezone=timezone,
            now=local_now,
            memories=memories,
            history=history,
            reminder_service=self.reminder_service,
        )

        used_ids = set(agent_result.used_memory_ids)
        retrieved_memories = [
            RetrievedMemory(
                id=memory.id,
                display_text=memory.display_text,
                scope=memory.scope,
                task_type=memory.task_type,
                used=memory.id in used_ids,
            )
            for memory in memories
        ]
        if used_ids:
            self.memory_service.mark_used(
                user_id=request.user_id,
                memory_ids=used_ids,
            )

        memory_changes = []
        for candidate in extract_preferences(request.message):
            memory_changes.append(
                self.memory_service.upsert(
                    user_id=request.user_id,
                    scope=candidate.scope,
                    task_type=candidate.task_type,
                    memory_key=candidate.memory_key,
                    memory_value=candidate.memory_value,
                    display_text=candidate.display_text,
                    reason=candidate.reason,
                    source_message_id=UUID(user_message["id"]),
                )
            )

        assistant_message = self.messages.create(
            user_id=request.user_id,
            conversation_id=str(conversation_id),
            role="assistant",
            content=agent_result.reply,
            request_id=str(request_id),
        )
        minimum_total = retrieval_ms + agent_result.model_ms + agent_result.tool_ms
        total_ms = max(
            minimum_total,
            round((perf_counter() - overall_started) * 1000),
        )
        metrics = RequestMetrics(
            model_call_count=agent_result.model_call_count,
            input_tokens=agent_result.input_tokens,
            output_tokens=agent_result.output_tokens,
            memory_tokens=agent_result.memory_tokens,
            retrieved_memory_count=len(retrieved_memories),
            used_memory_count=len(used_ids),
            retrieval_ms=retrieval_ms,
            model_ms=agent_result.model_ms,
            tool_ms=agent_result.tool_ms,
            total_ms=total_ms,
        )
        self.metrics_service.record(
            request_id=request_id,
            user_id=request.user_id,
            metrics=metrics,
            retrieved_memory_ids=[memory.id for memory in memories],
            used_memory_ids=list(used_ids),
        )
        return ChatResponse(
            request_id=request_id,
            conversation_id=conversation_id,
            user_message_id=UUID(user_message["id"]),
            assistant_message_id=UUID(assistant_message["id"]),
            status=agent_result.status,
            reply=agent_result.reply,
            retrieved_memories=retrieved_memories,
            tool_calls=agent_result.tool_calls,
            memory_changes=memory_changes,
            metrics=metrics,
        )
