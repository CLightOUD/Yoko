from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from uuid import UUID

from backend.app.database import Database
from backend.app.repositories import MetricsRepository, UserRepository
from backend.app.schemas import (
    MetricsSummaryQuery,
    MetricsSummaryResponse,
    RequestMetrics,
)
from backend.app.services.errors import InvalidRequestError, ResourceNotFoundError


class MetricsService:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.metrics = MetricsRepository(database)
        self.users = UserRepository(database)

    def record(
        self,
        *,
        request_id: UUID,
        user_id: str,
        metrics: RequestMetrics,
        retrieved_memory_ids: list[UUID] | None = None,
        used_memory_ids: list[UUID] | None = None,
        created_at: datetime | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> RequestMetrics:
        self._require_user(user_id, connection=connection)
        retrieved_ids = [str(memory_id) for memory_id in (retrieved_memory_ids or [])]
        used_ids = [str(memory_id) for memory_id in (used_memory_ids or [])]
        if len(retrieved_ids) != metrics.retrieved_memory_count:
            raise InvalidRequestError("检索记忆 ID 数量与指标不一致")
        if len(used_ids) != metrics.used_memory_count:
            raise InvalidRequestError("使用记忆 ID 数量与指标不一致")
        if not set(used_ids).issubset(retrieved_ids):
            raise InvalidRequestError("实际使用的记忆必须来自检索结果")
        existing = self.metrics.get_by_request(
            str(request_id), connection=connection
        )
        if existing is None:
            self.metrics.create(
                request_id=str(request_id),
                user_id=user_id,
                **metrics.model_dump(),
                retrieved_memory_ids=retrieved_ids,
                used_memory_ids=used_ids,
                created_at=created_at,
                connection=connection,
            )
            return metrics
        if existing["user_id"] != user_id:
            raise ResourceNotFoundError("请求不存在")
        metric_fields = RequestMetrics.model_fields
        return RequestMetrics.model_validate(
            {field: existing[field] for field in metric_fields}
        )

    def summarize(
        self,
        query: MetricsSummaryQuery,
        *,
        now: datetime | None = None,
    ) -> MetricsSummaryResponse:
        self._require_user(query.user_id)
        end = query.to or now or datetime.now(UTC)
        summary = self.metrics.summary(
            user_id=query.user_id,
            from_=query.from_,
            to=end,
        )
        earliest = summary.pop("earliest_created_at")
        response_from = query.from_ or earliest
        summary.pop("latest_created_at")
        return MetricsSummaryResponse(
            **summary,
            from_=response_from,
            to=end,
        )

    def _require_user(
        self,
        user_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if not self.users.exists(user_id, connection=connection):
            raise ResourceNotFoundError("用户不存在")
