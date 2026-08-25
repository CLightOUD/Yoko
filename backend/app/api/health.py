import logging
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import get_chat_service, get_database
from backend.app.api.errors import error_responses
from backend.app.database import Database
from backend.app.schemas import HealthResponse, ReadinessResponse
from backend.app.services import DatabaseUnavailableError, ModelNotReadyError
from backend.app.services.chat_service import ChatService

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
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
) -> ReadinessResponse:
    try:
        version = database.check_readiness()
    except (OSError, RuntimeError, sqlite3.Error) as exc:
        logger.error(
            "readiness_check_failed",
            extra={"error_type": type(exc).__name__},
        )
        raise DatabaseUnavailableError("数据库暂不可用") from exc
    try:
        chat_service.check_model_readiness()
    except Exception as exc:
        logger.error(
            "model_readiness_check_failed",
            extra={"error_type": type(exc).__name__},
        )
        raise ModelNotReadyError("模型服务尚未就绪") from exc
    return ReadinessResponse(
        status="ok",
        database="ok",
        model="ok",
        schema_version=version,
    )
