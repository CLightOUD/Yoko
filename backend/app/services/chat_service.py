from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from backend.app.agent import AgentRuntime
from backend.app.agent.preferences import classify_task, extract_preferences
from backend.app.database import Database
from backend.app.repositories import (
    ChatRequestRepository,
    MessageRepository,
    UserRepository,
)
from backend.app.schemas import (
    ChatRequest,
    ChatResponse,
    RequestMetrics,
    RetrievedMemory,
)
from backend.app.services.errors import ResourceConflictError, ResourceNotFoundError
from backend.app.services.memory_service import MemoryService
from backend.app.services.metrics_service import MetricsService
from backend.app.services.reminder_service import ReminderService


logger = logging.getLogger("yoko.chat")


@dataclass(frozen=True)
class ChatExecution:
    request_id: UUID
    conversation_id: UUID
    user_message_id: UUID
    cached_response: ChatResponse | None = None


class ChatService:
    HISTORY_MESSAGE_LIMIT = 6
    REQUEST_LEASE_SECONDS = 120

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
        self.chat_requests = ChatRequestRepository(database)
        self.messages = MessageRepository(database)
        self.users = UserRepository(database)

    def run(
        self,
        request: ChatRequest,
        *,
        idempotency_key: str | None = None,
    ) -> ChatResponse:
        overall_started = perf_counter()
        execution = self._begin(request, idempotency_key=idempotency_key)
        if execution.cached_response is not None:
            return execution.cached_response

        try:
            return self._execute(request, execution, overall_started=overall_started)
        except Exception as exc:
            try:
                self.chat_requests.fail(
                    request_id=str(execution.request_id),
                    user_id=request.user_id,
                    failure_code=type(exc).__name__,
                )
            except Exception:
                logger.exception(
                    "failed_to_record_chat_failure",
                    extra={"chat_request_id": str(execution.request_id)},
                )
            raise

    def _begin(
        self,
        request: ChatRequest,
        *,
        idempotency_key: str | None,
    ) -> ChatExecution:
        request_hash = self._request_hash(request)
        with self.database.transaction(immediate=True) as connection:
            user = self.users.get(request.user_id, connection=connection)
            if user is None:
                raise ResourceNotFoundError("用户不存在")

            if idempotency_key is not None:
                existing = self.chat_requests.get_by_idempotency_key(
                    user_id=request.user_id,
                    idempotency_key=idempotency_key,
                    connection=connection,
                )
                if existing is not None:
                    return self._reuse_existing(
                        existing=existing,
                        request_hash=request_hash,
                        connection=connection,
                    )

            if request.conversation_id is None:
                conversation_id = uuid4()
            else:
                conversation_id = request.conversation_id
                if not self.messages.conversation_belongs_to_user(
                    str(conversation_id),
                    request.user_id,
                    connection=connection,
                ):
                    raise ResourceNotFoundError("会话不存在")

            request_id = uuid4()
            user_message = self.messages.create(
                user_id=request.user_id,
                conversation_id=str(conversation_id),
                role="user",
                content=request.message,
                request_id=str(request_id),
                connection=connection,
            )
            self.chat_requests.create(
                request_id=str(request_id),
                user_id=request.user_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                conversation_id=str(conversation_id),
                user_message_id=user_message["id"],
                lease_seconds=self.REQUEST_LEASE_SECONDS,
                connection=connection,
            )
        return ChatExecution(
            request_id=request_id,
            conversation_id=conversation_id,
            user_message_id=UUID(user_message["id"]),
        )

    def _reuse_existing(
        self,
        *,
        existing: dict,
        request_hash: str,
        connection: sqlite3.Connection,
    ) -> ChatExecution:
        if existing["request_hash"] != request_hash:
            raise ResourceConflictError("幂等键已用于不同的聊天请求")
        if existing["status"] == "completed":
            return ChatExecution(
                request_id=UUID(existing["id"]),
                conversation_id=UUID(existing["conversation_id"]),
                user_message_id=UUID(existing["user_message_id"]),
                cached_response=ChatResponse.model_validate_json(
                    existing["response_json"]
                ),
            )
        lease_expires_at = datetime.fromisoformat(existing["lease_expires_at"])
        if existing["status"] == "pending" and lease_expires_at > datetime.now(UTC):
            raise ResourceConflictError("相同请求正在处理中")
        reclaimed = self.chat_requests.reclaim(
            request_id=existing["id"],
            user_id=existing["user_id"],
            lease_seconds=self.REQUEST_LEASE_SECONDS,
            connection=connection,
        )
        if reclaimed is None:
            raise ResourceConflictError("聊天请求状态发生变化")
        return ChatExecution(
            request_id=UUID(reclaimed["id"]),
            conversation_id=UUID(reclaimed["conversation_id"]),
            user_message_id=UUID(reclaimed["user_message_id"]),
        )

    def _execute(
        self,
        request: ChatRequest,
        execution: ChatExecution,
        *,
        overall_started: float,
    ) -> ChatResponse:
        user = self.users.get(request.user_id)
        if user is None:
            raise ResourceNotFoundError("用户不存在")

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
            conversation_id=str(execution.conversation_id),
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

        with self.database.transaction(immediate=True) as connection:
            active = self.chat_requests.get_for_user(
                request_id=str(execution.request_id),
                user_id=request.user_id,
                connection=connection,
            )
            if active is None or active["status"] != "pending":
                raise ResourceConflictError("聊天请求状态发生变化")
            if used_ids:
                self.memory_service.mark_used(
                    user_id=request.user_id,
                    memory_ids=used_ids,
                    connection=connection,
                )
            memory_changes = [
                self.memory_service.upsert(
                    user_id=request.user_id,
                    scope=candidate.scope,
                    task_type=candidate.task_type,
                    memory_key=candidate.memory_key,
                    memory_value=candidate.memory_value,
                    display_text=candidate.display_text,
                    reason=candidate.reason,
                    source_message_id=execution.user_message_id,
                    connection=connection,
                )
                for candidate in extract_preferences(request.message)
            ]
            assistant_message = self.messages.create(
                user_id=request.user_id,
                conversation_id=str(execution.conversation_id),
                role="assistant",
                content=agent_result.reply,
                request_id=str(execution.request_id),
                connection=connection,
            )
            self.metrics_service.record(
                request_id=execution.request_id,
                user_id=request.user_id,
                metrics=metrics,
                retrieved_memory_ids=[memory.id for memory in memories],
                used_memory_ids=list(used_ids),
                connection=connection,
            )
            response = ChatResponse(
                request_id=execution.request_id,
                conversation_id=execution.conversation_id,
                user_message_id=execution.user_message_id,
                assistant_message_id=UUID(assistant_message["id"]),
                status=agent_result.status,
                reply=agent_result.reply,
                retrieved_memories=retrieved_memories,
                tool_calls=agent_result.tool_calls,
                memory_changes=memory_changes,
                metrics=metrics,
            )
            if not self.chat_requests.complete(
                request_id=str(execution.request_id),
                user_id=request.user_id,
                response_json=response.model_dump_json(by_alias=True),
                connection=connection,
            ):
                raise ResourceConflictError("聊天请求状态发生变化")
        return response

    @staticmethod
    def _request_hash(request: ChatRequest) -> str:
        encoded = json.dumps(
            request.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
