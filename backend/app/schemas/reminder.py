from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic.experimental.missing_sentinel import MISSING

from backend.app.schemas.common import (
    APIModel,
    SessionBoundAPIModel,
    UserId,
    validate_timezone_name,
)


RepeatType = Literal["none", "daily", "weekly"]
ReminderStatus = Literal["active", "completed", "deleted"]
ReminderListStatus = Literal["active", "completed", "deleted", "all"]
ReminderInputTitle = Annotated[str, StringConstraints(min_length=1, max_length=200)]
ReminderTitle = Annotated[str, StringConstraints(min_length=1, max_length=4000)]


def _validate_future(value: AwareDatetime) -> AwareDatetime:
    if value <= datetime.now(UTC):
        raise ValueError("next_trigger_at must be in the future")
    return value


class ReminderView(APIModel):
    id: UUID
    user_id: UserId
    title: ReminderTitle
    next_trigger_at: AwareDatetime
    timezone: str
    repeat_type: RepeatType
    status: ReminderStatus
    last_triggered_at: AwareDatetime | None
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        return validate_timezone_name(value)


class ReminderCreateBody(SessionBoundAPIModel):
    title: ReminderInputTitle
    next_trigger_at: AwareDatetime
    timezone: str = "Asia/Shanghai"
    repeat_type: RepeatType = "none"

    @field_validator("next_trigger_at")
    @classmethod
    def validate_trigger_time(cls, value: AwareDatetime) -> AwareDatetime:
        return _validate_future(value)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        return validate_timezone_name(value)


class ReminderCreateRequest(ReminderCreateBody):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: UserId


class ReminderUpdateBody(SessionBoundAPIModel):
    title: ReminderInputTitle | MISSING = MISSING
    next_trigger_at: AwareDatetime | MISSING = MISSING
    timezone: str | MISSING = MISSING
    repeat_type: RepeatType | MISSING = MISSING
    status: Literal["active", "completed"] | MISSING = MISSING

    @field_validator("next_trigger_at")
    @classmethod
    def validate_trigger_time(
        cls, value: AwareDatetime
    ) -> AwareDatetime:
        return _validate_future(value)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        return validate_timezone_name(value)

    @model_validator(mode="after")
    def validate_patch_fields(self) -> ReminderUpdateRequest:
        update_fields = {
            "title",
            "next_trigger_at",
            "timezone",
            "repeat_type",
            "status",
        }
        provided = self.model_fields_set & update_fields
        if not provided:
            raise ValueError("at least one reminder field must be provided")
        return self


class ReminderUpdateRequest(ReminderUpdateBody):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: UserId


class ReminderListParams(SessionBoundAPIModel):
    status: ReminderListStatus = "active"
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ReminderListQuery(ReminderListParams):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: UserId


class DueReminderParams(SessionBoundAPIModel):
    limit: int = Field(default=20, ge=1, le=50)


class DueReminderQuery(DueReminderParams):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: UserId


class ReminderListResponse(APIModel):
    items: list[ReminderView]
    total: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_total(self) -> ReminderListResponse:
        if self.total < len(self.items):
            raise ValueError("total cannot be lower than items length")
        return self


class ReminderAckBody(SessionBoundAPIModel):
    expected_trigger_at: AwareDatetime


class ReminderAckRequest(ReminderAckBody):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: UserId


class ReminderAckResponse(APIModel):
    reminder: ReminderView
    already_acknowledged: bool
