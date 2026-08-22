from __future__ import annotations

import hashlib
import json
import sqlite3
from time import perf_counter
from uuid import UUID

from backend.app.agent.preferences import PreferenceCandidate, extract_preferences
from backend.app.database import Database
from backend.app.repositories import (
    FeedbackRepository,
    MemoryEventRepository,
    MemoryRepository,
    MessageRepository,
    UserRepository,
)
from backend.app.schemas import (
    FeedbackMetrics,
    FeedbackRequest,
    FeedbackResponse,
    MemoryChange,
    MemoryView,
)
from backend.app.services.errors import ResourceNotFoundError
from backend.app.services.memory_service import MemoryService


class FeedbackService:
    def __init__(self, database: Database, memory_service: MemoryService) -> None:
        self.database = database
        self.memory_service = memory_service
        self.feedbacks = FeedbackRepository(database)
        self.messages = MessageRepository(database)
        self.memories = MemoryRepository(database)
        self.events = MemoryEventRepository(database)
        self.users = UserRepository(database)

    def process(self, request: FeedbackRequest) -> FeedbackResponse:
        started = perf_counter()
        dedup_key = self._dedup_key(request)
        candidates = extract_preferences(
            " ".join(
                part
                for part in (request.feedback_text, request.corrected_reply)
                if part
            )
        )

        with self.database.transaction(immediate=True) as connection:
            if not self.users.exists(request.user_id, connection=connection):
                raise ResourceNotFoundError("用户不存在")
            request_messages = self.messages.list_for_request(
                user_id=request.user_id,
                request_id=str(request.request_id),
                connection=connection,
            )
            if not request_messages:
                raise ResourceNotFoundError("请求不存在")

            existing = self.feedbacks.get_by_dedup_key(
                dedup_key, connection=connection
            )
            if existing is not None:
                changes = self._existing_changes(
                    existing=existing,
                    candidates=candidates,
                    connection=connection,
                )
                return self._response(existing, changes, started)

            feedback_message = self.messages.create(
                user_id=request.user_id,
                conversation_id=request_messages[0]["conversation_id"],
                role="user",
                content=self._message_content(request),
                request_id=str(request.request_id),
                connection=connection,
            )
            if not candidates:
                changes = [
                    MemoryChange(
                        action="skipped",
                        memory=None,
                        reason="反馈未包含明确且长期适用的偏好",
                    )
                ]
            else:
                changes = [
                    self.memory_service.upsert(
                        user_id=request.user_id,
                        scope=candidate.scope,
                        task_type=candidate.task_type,
                        memory_key=candidate.memory_key,
                        memory_value=candidate.memory_value,
                        display_text=candidate.display_text,
                        reason=candidate.reason,
                        source_message_id=UUID(feedback_message["id"]),
                        connection=connection,
                    )
                    for candidate in candidates
                ]
            feedback = self.feedbacks.create(
                user_id=request.user_id,
                request_id=str(request.request_id),
                feedback_message_id=feedback_message["id"],
                feedback_text=request.feedback_text,
                corrected_reply=request.corrected_reply,
                rating=request.rating,
                dedup_key=dedup_key,
                connection=connection,
            )
        return self._response(feedback, changes, started)

    def _existing_changes(
        self,
        *,
        existing: dict,
        candidates: list[PreferenceCandidate],
        connection: sqlite3.Connection,
    ) -> list[MemoryChange]:
        if not candidates:
            return [
                MemoryChange(
                    action="skipped",
                    memory=None,
                    reason="反馈未包含明确且长期适用的偏好",
                )
            ]
        events = self.events.list_by_source_message(
            source_message_id=existing["feedback_message_id"],
            user_id=existing["user_id"],
            connection=connection,
        )
        if not events:
            return [
                MemoryChange(
                    action="skipped",
                    memory=None,
                    reason="重复反馈已处理，不重复写入记忆",
                )
            ]
        changes: list[MemoryChange] = []
        for event in events:
            memory = self.memories.get_for_user(
                event["memory_id"], existing["user_id"], connection=connection
            )
            candidate = next(
                (
                    item
                    for item in candidates
                    if memory is not None
                    and item.task_type == memory["task_type"]
                    and item.memory_key == memory["memory_key"]
                ),
                None,
            )
            action = (
                event["action"]
                if event["action"] in {"created", "updated"}
                else "skipped"
            )
            memory_view = None
            if action != "skipped" and memory is not None:
                memory_view = MemoryView.model_validate(
                    {field: memory[field] for field in MemoryView.model_fields}
                )
            changes.append(
                MemoryChange(
                    action=action,
                    memory=memory_view,
                    reason=(
                        candidate.reason
                        if candidate is not None
                        else "重复反馈已处理，不重复写入记忆"
                    ),
                )
            )
        return changes

    @staticmethod
    def _dedup_key(request: FeedbackRequest) -> str:
        canonical = {
            "user_id": request.user_id,
            "request_id": str(request.request_id),
            "feedback_text": FeedbackService._normalize(request.feedback_text),
            "corrected_reply": FeedbackService._normalize(request.corrected_reply),
            "rating": request.rating,
        }
        encoded = json.dumps(
            canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize(value: str | None) -> str | None:
        return None if value is None else " ".join(value.casefold().split())

    @staticmethod
    def _message_content(request: FeedbackRequest) -> str:
        parts = []
        if request.feedback_text:
            parts.append(request.feedback_text)
        if request.corrected_reply:
            parts.append(f"修正结果：{request.corrected_reply}")
        if request.rating:
            parts.append(f"评分：{request.rating}")
        return "\n".join(parts)

    @staticmethod
    def _response(
        feedback: dict,
        changes: list[MemoryChange],
        started: float,
    ) -> FeedbackResponse:
        return FeedbackResponse(
            feedback_id=UUID(feedback["id"]),
            feedback_message_id=UUID(feedback["feedback_message_id"]),
            status="processed",
            memory_changes=changes,
            metrics=FeedbackMetrics(
                model_call_count=0,
                input_tokens=None,
                output_tokens=None,
                total_ms=max(0, round((perf_counter() - started) * 1000)),
            ),
        )
