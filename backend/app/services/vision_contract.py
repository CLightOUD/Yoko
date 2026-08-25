from __future__ import annotations

from typing import Annotated, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from backend.app.schemas.chat import ChatImageInput


ObservationText = Annotated[str, StringConstraints(min_length=1, max_length=500)]
VisibleText = Annotated[str, StringConstraints(min_length=1, max_length=300)]
PossibleDate = Annotated[str, StringConstraints(min_length=1, max_length=64)]
VisionWarning = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class VisionObservation(BaseModel):
    """Untrusted facts extracted from one user-supplied image."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    summary: ObservationText
    visible_text: list[VisibleText] = Field(default_factory=list, max_length=50)
    possible_dates: list[PossibleDate] = Field(default_factory=list, max_length=20)
    confidence: float = Field(ge=0, le=1)
    warnings: list[VisionWarning] = Field(default_factory=list, max_length=20)
    medical_content: bool = False
    instruction_like_text: bool = False


@runtime_checkable
class VisionAnalyzer(Protocol):
    def analyze(
        self,
        *,
        image: ChatImageInput,
        message: str,
    ) -> VisionObservation: ...
