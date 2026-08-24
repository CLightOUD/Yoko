from __future__ import annotations

from pydantic import (
    AwareDatetime,
    ConfigDict,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    model_validator,
)

from backend.app.schemas.common import APIModel, SessionBoundAPIModel, UserId


class MetricsSummaryParams(SessionBoundAPIModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    from_: AwareDatetime | None = Field(default=None, alias="from")
    to: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_time_range(self) -> MetricsSummaryQuery:
        if self.from_ is not None and self.to is not None and self.to < self.from_:
            raise ValueError("to cannot be earlier than from")
        return self


class MetricsSummaryQuery(MetricsSummaryParams):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    user_id: UserId


class MetricsSummaryResponse(APIModel):
    request_count: NonNegativeInt
    model_call_count: NonNegativeInt
    input_tokens: NonNegativeInt
    output_tokens: NonNegativeInt
    memory_tokens: NonNegativeInt
    requests_with_retrieved_memory: NonNegativeInt
    requests_with_used_memory: NonNegativeInt
    token_metrics_complete: bool
    average_retrieval_ms: NonNegativeFloat
    average_model_ms: NonNegativeFloat
    average_total_ms: NonNegativeFloat
    from_: AwareDatetime | None = Field(alias="from")
    to: AwareDatetime

    @model_validator(mode="after")
    def validate_summary(self) -> MetricsSummaryResponse:
        if self.memory_tokens > self.input_tokens:
            raise ValueError("memory_tokens cannot exceed input_tokens")
        if self.requests_with_retrieved_memory > self.request_count:
            raise ValueError(
                "requests_with_retrieved_memory cannot exceed request_count"
            )
        if self.requests_with_used_memory > self.requests_with_retrieved_memory:
            raise ValueError(
                "requests_with_used_memory cannot exceed retrieved-memory requests"
            )
        if self.from_ is not None and self.to < self.from_:
            raise ValueError("to cannot be earlier than from")
        if self.average_total_ms < max(
            self.average_retrieval_ms,
            self.average_model_ms,
        ):
            raise ValueError("average_total_ms cannot be lower than component averages")
        return self
