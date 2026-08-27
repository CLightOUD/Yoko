from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from threading import BoundedSemaphore, Event, Thread
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from backend.app.agent import AgentRuntime
from backend.app.config import default_timezone
from backend.app.database import Database
from backend.app.repositories import (
    ChatRequestRepository,
    MessageRepository,
    UserRepository,
)
from backend.app.schemas import (
    ChatRequest,
    ChatRequestStatusResponse,
    ChatResponse,
    RequestMetrics,
    RetrievedMemory,
)
from backend.app.services.errors import (
    ModelNotReadyError,
    ResourceConflictError,
    ResourceNotFoundError,
    TooManyAttemptsError,
)
from backend.app.services.image_validation import (
    ValidatedChatImage,
    validate_chat_image,
)
from backend.app.services.memory_service import MemoryService
from backend.app.services.metrics_service import MetricsService
from backend.app.services.reminder_service import ReminderService
from backend.app.services.vision_contract import VisionAnalyzer, VisionObservation


logger = logging.getLogger("yoko.chat")


@dataclass(frozen=True)
class ChatExecution:
    request_id: UUID
    conversation_id: UUID
    user_message_id: UUID
    attempt_count: int
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
        vision_analyzer: VisionAnalyzer | None = None,
    ) -> None:
        self.database = database
        self.memory_service = memory_service
        self.reminder_service = reminder_service
        self.metrics_service = metrics_service
        self.agent = agent
        self.vision_analyzer = vision_analyzer
        self.chat_requests = ChatRequestRepository(database)
        self.messages = MessageRepository(database)
        self.users = UserRepository(database)
        max_concurrent = int(os.getenv("MAX_CONCURRENT_CHAT_REQUESTS", "4"))
        if max_concurrent <= 0:
            raise RuntimeError("MAX_CONCURRENT_CHAT_REQUESTS must be positive")
        self._chat_slots = BoundedSemaphore(max_concurrent)

    def check_model_readiness(self) -> None:
        checker = getattr(self.agent, "check_readiness", None)
        if checker is not None:
            checker()

    def run(
        self,
        request: ChatRequest,
        *,
        idempotency_key: str | None = None,
    ) -> ChatResponse:
        if not self._chat_slots.acquire(blocking=False):
            raise TooManyAttemptsError("聊天请求繁忙，请稍后重试")
        try:
            return self._run_with_slot(
                request,
                idempotency_key=idempotency_key,
            )
        finally:
            self._chat_slots.release()

    def _run_with_slot(
        self,
        request: ChatRequest,
        *,
        idempotency_key: str | None = None,
    ) -> ChatResponse:
        validated_image = None
        if request.image is not None:
            if self.vision_analyzer is None:
                raise ModelNotReadyError("图片理解服务尚未接入")
            validated_image = validate_chat_image(request.image)
        overall_started = perf_counter()
        execution = self._begin(request, idempotency_key=idempotency_key)
        if execution.cached_response is not None:
            return execution.cached_response

        try:
            with self._lease_heartbeat(execution, user_id=request.user_id):
                return self._execute(
                    request,
                    execution,
                    overall_started=overall_started,
                    validated_image=validated_image,
                )
        except Exception as exc:
            try:
                self.chat_requests.fail(
                    request_id=str(execution.request_id),
                    user_id=request.user_id,
                    failure_code=type(exc).__name__,
                    expected_attempt_count=execution.attempt_count,
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
            attempt_count=1,
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
                attempt_count=int(existing["attempt_count"]),
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
            attempt_count=int(reclaimed["attempt_count"]),
        )

    def _execute(
        self,
        request: ChatRequest,
        execution: ChatExecution,
        *,
        overall_started: float,
        validated_image: ValidatedChatImage | None,
    ) -> ChatResponse:
        user = self.users.get(request.user_id)
        if user is None:
            raise ResourceNotFoundError("用户不存在")

        vision_observation = None
        vision_ms = 0
        if validated_image is not None:
            vision_observation, vision_ms = self._analyze_image(
                request=request,
                execution=execution,
                validated_image=validated_image,
            )

        retrieval_started = perf_counter()
        memories = self.memory_service.retrieve_candidates(
            user_id=request.user_id,
            limit=10,
        )
        retrieval_ms = max(0, round((perf_counter() - retrieval_started) * 1000))
        history = self.messages.list_recent(
            user_id=request.user_id,
            conversation_id=str(execution.conversation_id),
            limit=self.HISTORY_MESSAGE_LIMIT,
        )
        if history and history[0]["role"] == "assistant":
            history = history[1:]
        timezone = request.timezone or user["timezone"] or default_timezone()
        local_now = datetime.now(UTC).astimezone(ZoneInfo(timezone))
        agent_result = self.agent.run(
            user_id=request.user_id,
            message=request.message,
            timezone=timezone,
            now=local_now,
            memories=memories,
            history=history,
            reminder_service=self.reminder_service,
            defer_mutations=True,
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
        with self.database.transaction(immediate=True) as connection:
            active = self.chat_requests.get_for_user(
                request_id=str(execution.request_id),
                user_id=request.user_id,
                connection=connection,
            )
            if (
                active is None
                or active["status"] != "pending"
                or int(active["attempt_count"]) != execution.attempt_count
            ):
                raise ResourceConflictError("聊天请求状态发生变化")
            agent_result = agent_result.commit_reminder_mutation(
                connection=connection
            )
            combined_model_ms = agent_result.model_ms + vision_ms
            minimum_total = retrieval_ms + combined_model_ms + agent_result.tool_ms
            total_ms = max(
                minimum_total,
                round((perf_counter() - overall_started) * 1000),
            )
            metrics = RequestMetrics(
                model_call_count=agent_result.model_call_count
                + (1 if vision_observation is not None else 0),
                input_tokens=(
                    None
                    if vision_observation is not None
                    else agent_result.input_tokens
                ),
                output_tokens=(
                    None
                    if vision_observation is not None
                    else agent_result.output_tokens
                ),
                memory_tokens=agent_result.memory_tokens,
                retrieved_memory_count=len(retrieved_memories),
                used_memory_count=len(used_ids),
                retrieval_ms=retrieval_ms,
                model_ms=combined_model_ms,
                tool_ms=agent_result.tool_ms,
                total_ms=total_ms,
            )
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
                for candidate in agent_result.memory_candidates
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
                sources=agent_result.sources,
                memory_changes=memory_changes,
                metrics=metrics,
            )
            if not self.chat_requests.complete(
                request_id=str(execution.request_id),
                user_id=request.user_id,
                response_json=response.model_dump_json(by_alias=True),
                expected_attempt_count=execution.attempt_count,
                connection=connection,
            ):
                raise ResourceConflictError("聊天请求状态发生变化")
        return response

    @contextmanager
    def _lease_heartbeat(
        self,
        execution: ChatExecution,
        *,
        user_id: str,
    ) -> Iterator[None]:
        stop = Event()
        interval = max(0.05, min(30.0, self.REQUEST_LEASE_SECONDS / 3))

        def renew() -> None:
            while not stop.wait(interval):
                try:
                    renewed = self.chat_requests.renew_lease(
                        request_id=str(execution.request_id),
                        user_id=user_id,
                        expected_attempt_count=execution.attempt_count,
                        lease_seconds=self.REQUEST_LEASE_SECONDS,
                    )
                except Exception:
                    logger.exception(
                        "chat_lease_heartbeat_failed",
                        extra={"chat_request_id": str(execution.request_id)},
                    )
                    continue
                if not renewed:
                    return

        thread = Thread(
            target=renew,
            name=f"chat-lease-{execution.request_id}",
            daemon=True,
        )
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join(timeout=interval + 1)

    def get_request_status(
        self,
        *,
        user_id: str,
        idempotency_key: str,
    ) -> ChatRequestStatusResponse:
        request = self.chat_requests.get_by_idempotency_key(
            user_id=user_id,
            idempotency_key=idempotency_key,
        )
        if request is None:
            raise ResourceNotFoundError("聊天请求不存在")
        response = None
        if request["status"] == "completed":
            response = ChatResponse.model_validate_json(request["response_json"])
        return ChatRequestStatusResponse(
            request_id=request["id"],
            status=request["status"],
            response=response,
        )

    def _analyze_image(
        self,
        *,
        request: ChatRequest,
        execution: ChatExecution,
        validated_image: ValidatedChatImage,
    ) -> tuple[VisionObservation, int]:
        assert request.image is not None
        assert self.vision_analyzer is not None
        stored = self.messages.get_for_user(
            str(execution.user_message_id), request.user_id
        )
        if (
            stored is not None
            and stored.get("image_sha256") == validated_image.sha256
            and stored.get("vision_observation")
        ):
            return VisionObservation.model_validate_json(
                stored["vision_observation"]
            ), int(stored.get("vision_model_ms") or 0)

        started = perf_counter()
        observation = self.vision_analyzer.analyze(
            image=request.image,
            message=request.message,
        )
        vision_ms = max(0, round((perf_counter() - started) * 1000))
        self.messages.set_vision_observation(
            str(execution.user_message_id),
            request.user_id,
            image_sha256=validated_image.sha256,
            vision_observation=observation.model_dump_json(),
            vision_confidence=observation.confidence,
            vision_model_ms=vision_ms,
        )
        return observation, vision_ms

    @staticmethod
    def _request_hash(request: ChatRequest) -> str:
        encoded = json.dumps(
            request.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
