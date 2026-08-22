from typing import Annotated

from fastapi import APIRouter, Depends, Query

from backend.app.api.dependencies import get_metrics_service
from backend.app.api.errors import error_responses
from backend.app.schemas import MetricsSummaryQuery, MetricsSummaryResponse
from backend.app.services import MetricsService


router = APIRouter(prefix="/api/metrics", tags=["metrics"])
MetricsServiceDependency = Annotated[MetricsService, Depends(get_metrics_service)]


@router.get(
    "/summary",
    response_model=MetricsSummaryResponse,
    responses=error_responses(400, 404, 422, 500),
)
def summarize_metrics(
    query: Annotated[MetricsSummaryQuery, Query()],
    service: MetricsServiceDependency,
) -> MetricsSummaryResponse:
    return service.summarize(query)
