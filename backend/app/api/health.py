from fastapi import APIRouter

from backend.app.api.errors import error_responses
from backend.app.schemas import HealthResponse

router = APIRouter(prefix="/api", tags=["system"])


@router.get(
    "/health",
    response_model=HealthResponse,
    responses=error_responses(500),
)
def health() -> HealthResponse:
    return HealthResponse(status="ok")
