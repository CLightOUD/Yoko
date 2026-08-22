from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.app.database import Database
from backend.app.repositories import MetricsRepository
from backend.app.schemas import MetricsSummaryQuery, RequestMetrics
from backend.app.services import InvalidRequestError, MetricsService


def make_metrics(*, with_memory: bool = True) -> RequestMetrics:
    return RequestMetrics(
        model_call_count=1,
        input_tokens=100,
        output_tokens=20,
        memory_tokens=10 if with_memory else 0,
        retrieved_memory_count=1 if with_memory else 0,
        used_memory_count=1 if with_memory else 0,
        retrieval_ms=5,
        model_ms=50,
        tool_ms=5,
        total_ms=70,
    )


def test_record_is_idempotent_and_summary_uses_requested_range(
    database: Database,
) -> None:
    service = MetricsService(database)
    memory_id = uuid4()
    request_id = uuid4()
    start = datetime.now(UTC) - timedelta(hours=1)
    metrics = make_metrics()

    first = service.record(
        request_id=request_id,
        user_id="demo-user",
        metrics=metrics,
        retrieved_memory_ids=[memory_id],
        used_memory_ids=[memory_id],
        created_at=start,
    )
    second = service.record(
        request_id=request_id,
        user_id="demo-user",
        metrics=metrics,
        retrieved_memory_ids=[memory_id],
        used_memory_ids=[memory_id],
        created_at=start,
    )

    assert first == second == metrics
    assert MetricsRepository(database).summary(user_id="demo-user")[
        "request_count"
    ] == 1
    end = datetime.now(UTC)
    summary = service.summarize(
        MetricsSummaryQuery.model_validate(
            {"user_id": "demo-user", "from": start, "to": end}
        )
    )
    assert summary.request_count == 1
    assert summary.requests_with_retrieved_memory == 1
    assert summary.token_metrics_complete is True
    assert summary.from_ == start
    assert summary.to == end


def test_summary_marks_missing_token_metrics_and_zero_range(database: Database) -> None:
    service = MetricsService(database)
    request_id = uuid4()
    incomplete = RequestMetrics(
        model_call_count=1,
        input_tokens=None,
        output_tokens=None,
        memory_tokens=0,
        retrieved_memory_count=0,
        used_memory_count=0,
        retrieval_ms=0,
        model_ms=10,
        tool_ms=0,
        total_ms=12,
    )
    service.record(
        request_id=request_id,
        user_id="demo-user",
        metrics=incomplete,
    )
    assert service.summarize(
        MetricsSummaryQuery(user_id="demo-user")
    ).token_metrics_complete is False

    future = datetime.now(UTC) + timedelta(days=1)
    empty = service.summarize(
        MetricsSummaryQuery.model_validate(
            {"user_id": "demo-user", "from": future}
        ),
        now=future + timedelta(days=1),
    )
    assert empty.request_count == 0
    assert empty.average_total_ms == 0.0
    assert empty.token_metrics_complete is True


def test_record_rejects_inconsistent_memory_id_counts(database: Database) -> None:
    service = MetricsService(database)
    with pytest.raises(InvalidRequestError, match="检索记忆 ID"):
        service.record(
            request_id=uuid4(),
            user_id="demo-user",
            metrics=make_metrics(),
            retrieved_memory_ids=[],
            used_memory_ids=[],
        )
