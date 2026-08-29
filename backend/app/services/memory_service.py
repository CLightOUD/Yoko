from __future__ import annotations

import sqlite3
from typing import Iterable
from uuid import UUID

from backend.app.database import Database
from backend.app.repositories import (
    MemoryEventRepository,
    MemoryRepository,
    MessageRepository,
    UserRepository,
)
from backend.app.schemas import (
    DeleteResponse,
    MemoryChange,
    MemoryListQuery,
    MemoryListResponse,
    MemoryUpdateRequest,
    MemoryView,
)
from backend.app.schemas.memory import MemoryScope, TaskType
from backend.app.services.errors import (
    InvalidRequestError,
    ResourceConflictError,
    ResourceNotFoundError,
)


class MemoryService:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.memories = MemoryRepository(database)
        self.events = MemoryEventRepository(database)
        self.messages = MessageRepository(database)
        self.users = UserRepository(database)

    def upsert(
        self,
        *,
        user_id: str,
        scope: MemoryScope,
        task_type: TaskType,
        memory_key: str,
        memory_value: str,
        display_text: str,
        reason: str,
        source_message_id: UUID | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> MemoryChange:
        if connection is not None:
            return self._upsert_in_connection(
                connection=connection,
                user_id=user_id,
                scope=scope,
                task_type=task_type,
                memory_key=memory_key,
                memory_value=memory_value,
                display_text=display_text,
                reason=reason,
                source_message_id=source_message_id,
            )
        with self.database.transaction(immediate=True) as active_connection:
            return self._upsert_in_connection(
                connection=active_connection,
                user_id=user_id,
                scope=scope,
                task_type=task_type,
                memory_key=memory_key,
                memory_value=memory_value,
                display_text=display_text,
                reason=reason,
                source_message_id=source_message_id,
            )

    def _upsert_in_connection(
        self,
        *,
        connection: sqlite3.Connection,
        user_id: str,
        scope: MemoryScope,
        task_type: TaskType,
        memory_key: str,
        memory_value: str,
        display_text: str,
        reason: str,
        source_message_id: UUID | None,
    ) -> MemoryChange:
        if (scope == "global") != (task_type == "global"):
            raise InvalidRequestError("记忆 scope 与 task_type 不匹配")
        source_id = str(source_message_id) if source_message_id is not None else None
        self._require_user(user_id, connection=connection)
        self._require_source_message(
            source_id, user_id=user_id, connection=connection
        )
        current = self.memories.find_latest_by_key(
            user_id=user_id,
            task_type=task_type,
            memory_key=memory_key,
            connection=connection,
        )
        if current is None:
            memory = self.memories.create(
                user_id=user_id,
                scope=scope,
                task_type=task_type,
                memory_key=memory_key,
                memory_value=memory_value,
                display_text=display_text,
                source_message_id=source_id,
                connection=connection,
            )
            action = "created"
            before = None
        else:
            before = current
            try:
                memory = self.memories.update(
                    memory_id=current["id"],
                    user_id=user_id,
                    updates={
                        "memory_value": memory_value,
                        "display_text": display_text,
                        "source_message_id": source_id,
                        "active": True,
                    },
                    connection=connection,
                )
            except sqlite3.IntegrityError as exc:
                raise ResourceConflictError("存在相同键的有效记忆") from exc
            action = "updated"
        self.events.create(
            memory_id=memory["id"],
            user_id=user_id,
            action=action,
            before_value=self._snapshot(before),
            after_value=self._snapshot(memory),
            source_message_id=source_id,
            connection=connection,
        )
        return MemoryChange(
            action=action,
            memory=self._to_view(memory),
            reason=reason,
        )

    def retrieve(
        self,
        *,
        user_id: str,
        task_type: TaskType,
        limit: int = 3,
    ) -> list[MemoryView]:
        self._require_user(user_id)
        items = self.memories.retrieve(
            user_id=user_id,
            task_type=task_type,
            limit=limit,
        )
        return [self._to_view(item) for item in items]

    def retrieve_candidates(
        self,
        *,
        user_id: str,
        query_text: str | None = None,
        limit: int = 10,
    ) -> list[MemoryView]:
        """Return a bounded, task-diverse pool for model-side relevance decisions."""
        self._require_user(user_id)
        if not 1 <= limit <= 10:
            raise ValueError("memory candidate limit must be between 1 and 10")
        items, _ = self.memories.list(
            user_id=user_id,
            active=True,
            limit=100,
        )
        selected: list[dict] = []
        selected_ids: set[str] = set()

        # Keep a named fact visible even when newer, unrelated memories fill the pool.
        normalized_query = "".join((query_text or "").split())
        for item in items:
            key = item["memory_key"]
            if not key.startswith("personal_fact:"):
                continue
            subject = key.removeprefix("personal_fact:")
            if subject and subject in normalized_query and len(selected) < limit:
                selected.append(item)
                selected_ids.add(item["id"])

        # Reserve one slot for every task represented in the recent pool. This keeps
        # unrelated recent memories from completely hiding an older relevant task.
        for task_type in ("global", "medication", "walking", "appointment", "other"):
            item = next((row for row in items if row["task_type"] == task_type), None)
            if (
                item is not None
                and item["id"] not in selected_ids
                and len(selected) < limit
            ):
                selected.append(item)
                selected_ids.add(item["id"])
        for item in items:
            if len(selected) >= limit:
                break
            if item["id"] not in selected_ids:
                selected.append(item)
                selected_ids.add(item["id"])
        return [self._to_view(item) for item in selected]

    def mark_used(
        self,
        *,
        user_id: str,
        memory_ids: Iterable[UUID],
        connection: sqlite3.Connection | None = None,
    ) -> int:
        self._require_user(user_id, connection=connection)
        return self.memories.mark_used(
            memory_ids=[str(memory_id) for memory_id in memory_ids],
            user_id=user_id,
            connection=connection,
        )

    def list(self, query: MemoryListQuery) -> MemoryListResponse:
        self._require_user(query.user_id)
        items, total = self.memories.list(
            user_id=query.user_id,
            active=query.active,
            task_type=query.task_type,
            limit=query.limit,
            offset=query.offset,
        )
        return MemoryListResponse(
            items=[self._to_view(item) for item in items], total=total
        )

    def update(
        self,
        memory_id: UUID,
        request: MemoryUpdateRequest,
    ) -> MemoryView:
        updates = request.model_dump(exclude={"user_id"}, exclude_unset=True)
        with self.database.transaction(immediate=True) as connection:
            self._require_user(request.user_id, connection=connection)
            current = self.memories.get_for_user(
                str(memory_id), request.user_id, connection=connection
            )
            if current is None:
                raise ResourceNotFoundError("记忆不存在")
            try:
                updated = self.memories.update(
                    memory_id=str(memory_id),
                    user_id=request.user_id,
                    updates=updates,
                    connection=connection,
                )
            except sqlite3.IntegrityError as exc:
                raise ResourceConflictError("重新启用会造成有效记忆冲突") from exc
            self.events.create(
                memory_id=str(memory_id),
                user_id=request.user_id,
                action="updated",
                before_value=self._snapshot(current),
                after_value=self._snapshot(updated),
                connection=connection,
            )
        return self._to_view(updated)

    def delete(self, memory_id: UUID, user_id: str) -> DeleteResponse:
        with self.database.transaction(immediate=True) as connection:
            self._require_user(user_id, connection=connection)
            current = self.memories.get_for_user(
                str(memory_id), user_id, connection=connection
            )
            if current is None:
                raise ResourceNotFoundError("记忆不存在")
            if current["active"]:
                updated = self.memories.update(
                    memory_id=str(memory_id),
                    user_id=user_id,
                    updates={"active": False},
                    connection=connection,
                )
                self.events.create(
                    memory_id=str(memory_id),
                    user_id=user_id,
                    action="deleted",
                    before_value=self._snapshot(current),
                    after_value=self._snapshot(updated),
                    connection=connection,
                )
        return DeleteResponse(id=memory_id, deleted=True)

    def _require_user(
        self,
        user_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if not self.users.exists(user_id, connection=connection):
            raise ResourceNotFoundError("用户不存在")

    def _require_source_message(
        self,
        source_message_id: str | None,
        *,
        user_id: str,
        connection: sqlite3.Connection,
    ) -> None:
        if source_message_id is None:
            return
        if self.messages.get_for_user(
            source_message_id, user_id, connection=connection
        ) is None:
            raise ResourceNotFoundError("来源消息不存在")

    @staticmethod
    def _snapshot(memory: dict | None) -> dict | None:
        if memory is None:
            return None
        fields = (
            "memory_value",
            "display_text",
            "active",
            "source_message_id",
        )
        return {field: memory[field] for field in fields}

    @staticmethod
    def _to_view(memory: dict) -> MemoryView:
        fields = MemoryView.model_fields
        return MemoryView.model_validate(
            {field: memory[field] for field in fields}
        )
