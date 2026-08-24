from typing import Annotated

from fastapi import APIRouter, Depends, Query

from backend.app.api.dependencies import get_current_user, get_metrics_service
from backend.app.api.errors import error_responses
from backend.app.schemas import (
    MetricsSummaryParams,
    MetricsSummaryQuery,
    MetricsSummaryResponse,
    UserView,
)
from backend.app.services import MetricsService


router = APIRouter(prefix="/api/metrics", tags=["metrics"])
MetricsServiceDependency = Annotated[MetricsService, Depends(get_metrics_service)]
CurrentUserDependency = Annotated[UserView, Depends(get_current_user)]


@router.get(
    "/summary",
    response_model=MetricsSummaryResponse,
    responses=error_responses(400, 401, 404, 422, 500),
)
def summarize_metrics(
    query: Annotated[MetricsSummaryParams, Query()],
    service: MetricsServiceDependency,
    current_user: CurrentUserDependency,
) -> MetricsSummaryResponse:
    command = MetricsSummaryQuery(
        user_id=str(current_user.id),
        **query.model_dump(by_alias=True),
    )
    return service.summarize(command)
