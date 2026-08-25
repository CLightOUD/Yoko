from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    ConfigDict,
    Field,
    NonNegativeInt,
    StringConstraints,
    field_validator,
    model_validator,
)

from backend.app.schemas.common import (
    APIModel,
    SessionBoundAPIModel,
    UserId,
    validate_timezone_name,
)
from backend.app.schemas.memory import MemoryChange, MemoryScope, TaskType


ChatStatus = Literal["completed", "needs_clarification", "partial"]
ToolStatus = Literal["success", "failed"]
ChatMessage = Annotated[str, StringConstraints(min_length=1, max_length=2000)]


class ChatRequestBody(SessionBoundAPIModel):
    conversation_id: UUID | None = None
    message: ChatMessage
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return validate_timezone_name(value)


class ChatRequest(ChatRequestBody):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: UserId


class RetrievedMemory(APIModel):
    id: UUID
    display_text: str = Field(min_length=1, max_length=200)
    scope: MemoryScope
    task_type: TaskType
    used: bool


class ToolCallView(APIModel):
    tool_name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    status: ToolStatus
    summary: str = Field(min_length=1, max_length=500)
    latency_ms: NonNegativeInt


class WebSource(APIModel):
    title: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=10, max_length=2048, pattern=r"^https?://")
    snippet: str = Field(max_length=500)
    source: Literal["bing"] = "bing"


class RequestMetrics(APIModel):
    model_call_count: NonNegativeInt
    input_tokens: NonNegativeInt | None
    output_tokens: NonNegativeInt | None
    memory_tokens: NonNegativeInt
    retrieved_memory_count: NonNegativeInt
    used_memory_count: NonNegativeInt
    retrieval_ms: NonNegativeInt
    model_ms: NonNegativeInt
    tool_ms: NonNegativeInt
    total_ms: NonNegativeInt

    @model_validator(mode="after")
    def validate_counts_and_timings(self) -> RequestMetrics:
        if self.used_memory_count > self.retrieved_memory_count:
            raise ValueError("used_memory_count cannot exceed retrieved_memory_count")
        if self.input_tokens is not None and self.memory_tokens > self.input_tokens:
            raise ValueError("memory_tokens cannot exceed input_tokens")
        component_total = self.retrieval_ms + self.model_ms + self.tool_ms
        if self.total_ms < component_total:
            raise ValueError("total_ms cannot be lower than summed component latency")
        return self


class ChatResponse(APIModel):
    request_id: UUID
    conversation_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
    status: ChatStatus
    reply: str = Field(min_length=1, max_length=10_000)
    retrieved_memories: list[RetrievedMemory] = Field(max_length=3)
    tool_calls: list[ToolCallView]
    sources: list[WebSource] = Field(default_factory=list, max_length=5)
    memory_changes: list[MemoryChange]
    metrics: RequestMetrics

    @model_validator(mode="after")
    def validate_status_and_metrics(self) -> ChatResponse:
        failed_tools = any(tool.status == "failed" for tool in self.tool_calls)
        if self.status == "partial" and not failed_tools:
            raise ValueError("partial responses must include a failed tool call")
        if self.status == "completed" and failed_tools:
            raise ValueError("completed responses cannot include failed tool calls")
        if self.status == "needs_clarification" and self.tool_calls:
            raise ValueError("needs_clarification responses cannot include tool calls")
        if self.metrics.retrieved_memory_count != len(self.retrieved_memories):
            raise ValueError(
                "retrieved_memory_count must match retrieved_memories length"
            )
        used_count = sum(memory.used for memory in self.retrieved_memories)
        if self.metrics.used_memory_count != used_count:
            raise ValueError("used_memory_count must match used memory entries")
        return self
