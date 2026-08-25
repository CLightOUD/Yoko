from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    Field,
    SecretStr,
    StringConstraints,
    field_validator,
    model_validator,
)

from backend.app.config import default_timezone
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
    timezone: str = Field(default_factory=default_timezone)

    _validate_timezone = field_validator("timezone")(validate_timezone_name)


class LoginRequest(APIModel):
    username: Username
    password: SecretStr = Field(min_length=8, max_length=128)


class ChangePasswordRequest(APIModel):
    current_password: SecretStr = Field(min_length=8, max_length=128)
    new_password: SecretStr = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_password_changed(self) -> "ChangePasswordRequest":
        if (
            self.current_password.get_secret_value()
            == self.new_password.get_secret_value()
        ):
            raise ValueError("new_password must differ from current_password")
        return self


class AccountDeleteRequest(APIModel):
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


class AccountDeleteResponse(APIModel):
    deleted: Literal[True]


class AccountExportResponse(APIModel):
    exported_at: datetime
    account: dict[str, Any]
    messages: list[dict[str, Any]]
    reminders: list[dict[str, Any]]
    memories: list[dict[str, Any]]
    memory_events: list[dict[str, Any]]
    request_metrics: list[dict[str, Any]]
    feedbacks: list[dict[str, Any]]
