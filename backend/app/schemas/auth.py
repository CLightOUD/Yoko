from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, SecretStr, StringConstraints, field_validator

from backend.app.schemas.common import APIModel, validate_timezone_name


Username = Annotated[
    str,
    StringConstraints(
        min_length=3,
        max_length=32,
        pattern=r"^[A-Za-z0-9_]+$",
    ),
]
DisplayName = Annotated[str, StringConstraints(min_length=1, max_length=32)]


class RegisterRequest(APIModel):
    username: Username
    password: SecretStr = Field(min_length=8, max_length=128)
    display_name: DisplayName
    timezone: str = "Asia/Shanghai"

    _validate_timezone = field_validator("timezone")(validate_timezone_name)


class LoginRequest(APIModel):
    username: Username
    password: SecretStr = Field(min_length=8, max_length=128)


class UserView(APIModel):
    id: UUID
    username: Username
    display_name: DisplayName
    timezone: str

    _validate_timezone = field_validator("timezone")(validate_timezone_name)


class AuthResponse(APIModel):
    user: UserView
    session_expires_at: datetime

    @field_validator("session_expires_at")
    @classmethod
    def validate_aware_expiry(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("session_expires_at must include a timezone")
        return value


class LogoutResponse(APIModel):
    logged_out: Literal[True]
