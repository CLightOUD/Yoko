from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class APIModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        populate_by_name=True,
        serialize_by_alias=True,
        str_strip_whitespace=True,
    )


class SessionBoundAPIModel(APIModel):
    """Public input that discards only the legacy client-supplied user ID."""

    @model_validator(mode="before")
    @classmethod
    def discard_legacy_user_id(cls, value: Any) -> Any:
        if "user_id" in cls.model_fields or not isinstance(value, Mapping):
            return value
        cleaned = dict(value)
        cleaned.pop("user_id", None)
        return cleaned


UserId = Annotated[str, StringConstraints(min_length=1, max_length=64)]
ErrorCode = Literal[
    "AUTHENTICATION_REQUIRED",
    "AUTHENTICATION_UNAVAILABLE",
    "INVALID_CREDENTIALS",
    "INVALID_REQUEST",
    "ORIGIN_NOT_ALLOWED",
    "RESOURCE_NOT_FOUND",
    "RESOURCE_CONFLICT",
    "TOO_MANY_ATTEMPTS",
    "USERNAME_ALREADY_EXISTS",
    "MODEL_UNAVAILABLE",
    "TOOL_EXECUTION_FAILED",
    "DATABASE_UNAVAILABLE",
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


class ReadinessResponse(APIModel):
    status: Literal["ok"]
    database: Literal["ok"]
    model: Literal["ok"]
    schema_version: int = Field(ge=1)


class DeleteResponse(APIModel):
    id: UUID
    deleted: Literal[True]
