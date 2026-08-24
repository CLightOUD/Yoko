from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import (
    get_current_user,
    get_feedback_service,
    require_trusted_origin,
)
from backend.app.api.errors import error_responses
from backend.app.schemas import (
    FeedbackRequest,
    FeedbackRequestBody,
    FeedbackResponse,
    UserView,
)
from backend.app.services.feedback_service import FeedbackService


router = APIRouter(prefix="/api", tags=["feedback"])
FeedbackServiceDependency = Annotated[FeedbackService, Depends(get_feedback_service)]
CurrentUserDependency = Annotated[UserView, Depends(get_current_user)]


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    responses=error_responses(401, 403, 404, 422, 500),
    dependencies=[Depends(require_trusted_origin)],
)
def feedback(
    request: FeedbackRequestBody,
    service: FeedbackServiceDependency,
    current_user: CurrentUserDependency,
) -> FeedbackResponse:
    command = FeedbackRequest(
        user_id=str(current_user.id),
        **request.model_dump(),
    )
    return service.process(command)
