from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints

from backend.app.schemas.common import APIModel, SessionBoundAPIModel


PushEndpoint = Annotated[
    str,
    StringConstraints(min_length=16, max_length=2048, pattern=r"^https://"),
]
PushKey = Annotated[
    str,
    StringConstraints(min_length=16, max_length=256, pattern=r"^[A-Za-z0-9_-]+$"),
]


class PushConfigResponse(APIModel):
    enabled: bool
    application_server_key: str | None = Field(default=None, max_length=256)


class PushSubscriptionKeys(APIModel):
    p256dh: PushKey
    auth: PushKey


class PushSubscriptionBody(SessionBoundAPIModel):
    endpoint: PushEndpoint
    keys: PushSubscriptionKeys


class PushSubscriptionDeleteBody(SessionBoundAPIModel):
    endpoint: PushEndpoint


class PushSubscriptionResponse(APIModel):
    id: UUID
    active: Literal[True]


class PushSubscriptionDeleteResponse(APIModel):
    deleted: Literal[True]
