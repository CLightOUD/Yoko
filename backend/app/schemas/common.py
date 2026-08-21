from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class APIModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        populate_by_name=True,
        serialize_by_alias=True,
        str_strip_whitespace=True,
    )


UserId = Annotated[str, StringConstraints(min_length=1, max_length=64)]
ErrorCode = Literal[
    "INVALID_REQUEST",
    "RESOURCE_NOT_FOUND",
    "RESOURCE_CONFLICT",
    "MODEL_UNAVAILABLE",
    "TOOL_EXECUTION_FAILED",
    "INTERNAL_ERROR",
]


def validate_timezone_name(value: str) -> str:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("timezone must be a valid IANA timezone") from exc
    return value


class ErrorDetail(APIModel):
    code: ErrorCode
    message: str = Field(min_length=1, max_length=500)
    details: dict[str, Any] | list[Any] | str | None


class ErrorResponse(APIModel):
    error: ErrorDetail
    request_id: UUID


class HealthResponse(APIModel):
    status: Literal["ok"]


class DeleteResponse(APIModel):
    id: UUID
    deleted: Literal[True]
