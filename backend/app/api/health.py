import logging
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import get_database
from backend.app.api.errors import error_responses
from backend.app.database import Database
from backend.app.schemas import HealthResponse, ReadinessResponse
from backend.app.services import DatabaseUnavailableError

router = APIRouter(prefix="/api", tags=["system"])
logger = logging.getLogger("yoko.readiness")


@router.get(
    "/health",
    response_model=HealthResponse,
    responses=error_responses(500),
)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses=error_responses(500, 503),
)
def readiness(
    database: Annotated[Database, Depends(get_database)],
) -> ReadinessResponse:
    try:
        version = database.check_readiness()
    except (OSError, RuntimeError, sqlite3.Error) as exc:
        logger.error(
            "readiness_check_failed",
            extra={"error_type": type(exc).__name__},
        )
        raise DatabaseUnavailableError("数据库暂不可用") from exc
    return ReadinessResponse(
        status="ok",
        database="ok",
        schema_version=version,
    )
