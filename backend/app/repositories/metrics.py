from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any
from uuid import uuid4

from backend.app.repositories._common import (
    BaseRepository,
    decode_json,
    encode_json,
    normalize_datetime,
    row_to_dict,
    utc_now_iso,
)


class MetricsRepository(BaseRepository):
    def create(
        self,
        *,
        request_id: str,
        user_id: str,
        model_call_count: int,
        input_tokens: int | None,
        output_tokens: int | None,
        memory_tokens: int,
        retrieved_memory_count: int,
        used_memory_count: int,
        retrieval_ms: int,
        model_ms: int,
        tool_ms: int,
        total_ms: int,
        retrieved_memory_ids: list[str] | None = None,
        used_memory_ids: list[str] | None = None,
        metric_id: str | None = None,
        created_at: datetime | str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        metric_id = metric_id or str(uuid4())
        created_at_value = (
            normalize_datetime(created_at) if created_at is not None else utc_now_iso()
        )
        with self._connection(connection, write=True) as active_connection:
            active_connection.execute(
                """
                INSERT INTO request_metrics (
                    id, request_id, user_id, model_call_count, input_tokens,
                    output_tokens, memory_tokens, retrieved_memory_count,
                    used_memory_count, retrieval_ms, model_ms, tool_ms, total_ms,
                    retrieved_memory_ids, used_memory_ids, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metric_id,
                    request_id,
                    user_id,
                    model_call_count,
                    input_tokens,
                    output_tokens,
                    memory_tokens,
                    retrieved_memory_count,
                    used_memory_count,
                    retrieval_ms,
                    model_ms,
                    tool_ms,
                    total_ms,
                    encode_json(retrieved_memory_ids or []),
                    encode_json(used_memory_ids or []),
                    created_at_value,
                ),
            )
            row = active_connection.execute(
                "SELECT * FROM request_metrics WHERE id = ?", (metric_id,)
            ).fetchone()
        return self._convert_row(row)

    def get_by_request(
        self,
        request_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        with self._connection(connection) as active_connection:
            row = active_connection.execute(
                "SELECT * FROM request_metrics WHERE request_id = ?", (request_id,)
            ).fetchone()
        return self._convert_row(row)

    def summary(
        self,
        *,
        user_id: str,
        from_: datetime | str | None = None,
        to: datetime | str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        conditions = ["user_id = ?"]
        parameters: list[Any] = [user_id]
        if from_ is not None:
            conditions.append("created_at >= ?")
            parameters.append(normalize_datetime(from_))
        if to is not None:
            conditions.append("created_at <= ?")
            parameters.append(normalize_datetime(to))
        where = " AND ".join(conditions)
        with self._connection(connection) as active_connection:
            row = active_connection.execute(
                f"""
                SELECT
                    COUNT(*) AS request_count,
                    COALESCE(SUM(model_call_count), 0) AS model_call_count,
                    COALESCE(SUM(input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens,
                    COALESCE(SUM(memory_tokens), 0) AS memory_tokens,
                    COALESCE(SUM(retrieved_memory_count > 0), 0)
                        AS requests_with_retrieved_memory,
                    COALESCE(SUM(used_memory_count > 0), 0)
                        AS requests_with_used_memory,
                    CASE WHEN COUNT(*) = 0 THEN 1
                         WHEN COUNT(input_tokens) = COUNT(*)
                          AND COUNT(output_tokens) = COUNT(*) THEN 1
                         ELSE 0 END AS token_metrics_complete,
                    COALESCE(AVG(retrieval_ms), 0.0) AS average_retrieval_ms,
                    COALESCE(AVG(model_ms), 0.0) AS average_model_ms,
                    COALESCE(AVG(total_ms), 0.0) AS average_total_ms,
                    MIN(created_at) AS earliest_created_at,
                    MAX(created_at) AS latest_created_at
                FROM request_metrics
                WHERE {where}
                """,
                parameters,
            ).fetchone()
        result = dict(row)
        result["token_metrics_complete"] = bool(result["token_metrics_complete"])
        return result

    @staticmethod
    def _convert_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        result = row_to_dict(row)
        if result is not None:
            result["retrieved_memory_ids"] = decode_json(
                result["retrieved_memory_ids"]
            )
            result["used_memory_ids"] = decode_json(result["used_memory_ids"])
        return result
