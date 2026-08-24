from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)
from pydantic.experimental.missing_sentinel import MISSING

from backend.app.schemas.common import APIModel, SessionBoundAPIModel, UserId


MemoryScope = Literal["global", "task"]
TaskType = Literal["global", "medication", "walking", "appointment", "other"]
MemoryAction = Literal["created", "updated", "skipped"]

MemoryKey = Annotated[str, StringConstraints(min_length=1, max_length=64)]
MemoryValue = Annotated[str, StringConstraints(min_length=1, max_length=500)]
MemoryDisplayText = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class MemoryView(APIModel):
    id: UUID
    scope: MemoryScope
    task_type: TaskType
    memory_key: MemoryKey
    memory_value: MemoryValue
    display_text: MemoryDisplayText
    active: bool
    source_message_id: UUID | None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    last_used_at: AwareDatetime | None

    @model_validator(mode="after")
    def validate_scope_and_task_type(self) -> MemoryView:
        if self.scope == "global" and self.task_type != "global":
            raise ValueError("global memories must use task_type='global'")
        if self.scope == "task" and self.task_type == "global":
            raise ValueError("task memories cannot use task_type='global'")
        return self


class MemoryChange(APIModel):
    action: MemoryAction
    memory: MemoryView | None
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_memory_for_action(self) -> MemoryChange:
        if self.action == "skipped" and self.memory is not None:
            raise ValueError("skipped changes must not contain a memory")
        if self.action != "skipped" and self.memory is None:
            raise ValueError("created and updated changes must contain a memory")
        return self


class MemoryListParams(SessionBoundAPIModel):
    active: bool | None = True
    task_type: TaskType | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class MemoryListQuery(MemoryListParams):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: UserId


class MemoryListResponse(APIModel):
    items: list[MemoryView]
    total: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_total(self) -> MemoryListResponse:
        if self.total < len(self.items):
            raise ValueError("total cannot be lower than items length")
        return self


class MemoryUpdateBody(SessionBoundAPIModel):
    memory_value: MemoryValue | MISSING = MISSING
    display_text: MemoryDisplayText | MISSING = MISSING
    active: bool | MISSING = MISSING

    @model_validator(mode="after")
    def validate_patch_fields(self) -> MemoryUpdateRequest:
        update_fields = {"memory_value", "display_text", "active"}
        provided = self.model_fields_set & update_fields
        if not provided:
            raise ValueError("at least one memory field must be provided")
        return self


class MemoryUpdateRequest(MemoryUpdateBody):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: UserId
