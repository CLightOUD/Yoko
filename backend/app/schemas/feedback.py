from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, NonNegativeInt, StringConstraints, model_validator

from backend.app.schemas.common import APIModel, SessionBoundAPIModel, UserId
from backend.app.schemas.memory import MemoryChange


FeedbackText = Annotated[str, StringConstraints(min_length=1, max_length=2000)]
CorrectedReply = Annotated[str, StringConstraints(min_length=1, max_length=4000)]
FeedbackRating = Literal["up", "down"]


class FeedbackRequestBody(SessionBoundAPIModel):
    request_id: UUID
    feedback_text: FeedbackText | None = None
    corrected_reply: CorrectedReply | None = None
    rating: FeedbackRating | None = None

    @model_validator(mode="after")
    def validate_feedback_content(self) -> FeedbackRequest:
        if (
            self.feedback_text is None
            and self.corrected_reply is None
            and self.rating is None
        ):
            raise ValueError("at least one feedback field must be provided")
        return self


class FeedbackRequest(FeedbackRequestBody):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: UserId


class FeedbackMetrics(APIModel):
    model_call_count: NonNegativeInt
    input_tokens: NonNegativeInt | None
    output_tokens: NonNegativeInt | None
    total_ms: NonNegativeInt


class FeedbackResponse(APIModel):
    feedback_id: UUID
    feedback_message_id: UUID
    status: Literal["processed"]
    memory_changes: list[MemoryChange]
    metrics: FeedbackMetrics
