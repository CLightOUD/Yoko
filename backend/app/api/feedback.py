from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import get_feedback_service
from backend.app.api.errors import error_responses
from backend.app.schemas import FeedbackRequest, FeedbackResponse
from backend.app.services.feedback_service import FeedbackService


router = APIRouter(prefix="/api", tags=["feedback"])
FeedbackServiceDependency = Annotated[FeedbackService, Depends(get_feedback_service)]


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    responses=error_responses(404, 422, 500),
)
def feedback(
    request: FeedbackRequest,
    service: FeedbackServiceDependency,
) -> FeedbackResponse:
    return service.process(request)
