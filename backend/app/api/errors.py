from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.app.schemas import ErrorDetail, ErrorResponse
from backend.app.schemas.common import ErrorCode
from backend.app.services import (
    DatabaseUnavailableError,
    InvalidRequestError,
    ModelUnavailableError,
    ResourceConflictError,
    ResourceNotFoundError,
    ServiceError,
    ToolExecutionError,
)


logger = logging.getLogger("yoko.errors")


ERROR_DESCRIPTIONS = {
    400: "业务参数无效",
    404: "资源不存在",
    409: "资源状态冲突",
    422: "请求字段校验失败",
    500: "服务器内部错误",
    502: "模型或工具不可用",
    503: "服务暂不可用",
}


def error_responses(*status_codes: int) -> dict[int, dict[str, Any]]:
    return {
        status_code: {
            "model": ErrorResponse,
            "description": ERROR_DESCRIPTIONS[status_code],
        }
        for status_code in status_codes
    }


def request_id_for(request: Request) -> UUID:
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, UUID):
        return request_id
    request_id = uuid4()
    request.state.request_id = request_id
    return request_id


def error_response(
    request: Request,
    *,
    status_code: int,
    code: ErrorCode,
    message: str,
    details: Any = None,
) -> JSONResponse:
    payload = ErrorResponse(
        error=ErrorDetail(code=code, message=message, details=details),
        request_id=request_id_for(request),
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        details = [
            {
                key: value
                for key, value in error.items()
                if key not in {"ctx", "input", "url"}
            }
            for error in exc.errors()
        ]
        return error_response(
            request,
            status_code=422,
            code="INVALID_REQUEST",
            message="请求参数校验失败",
            details=details,
        )

    @app.exception_handler(ServiceError)
    def handle_service_error(request: Request, exc: ServiceError) -> JSONResponse:
        mapping: dict[type[ServiceError], tuple[int, str]] = {
            InvalidRequestError: (400, "INVALID_REQUEST"),
            ResourceNotFoundError: (404, "RESOURCE_NOT_FOUND"),
            ResourceConflictError: (409, "RESOURCE_CONFLICT"),
            ModelUnavailableError: (502, "MODEL_UNAVAILABLE"),
            ToolExecutionError: (502, "TOOL_EXECUTION_FAILED"),
            DatabaseUnavailableError: (503, "DATABASE_UNAVAILABLE"),
        }
        status_code, code = mapping.get(type(exc), (500, "INTERNAL_ERROR"))
        logger.warning(
            "service_error",
            extra={
                "request_id": str(request_id_for(request)),
                "path": request.url.path,
                "status_code": status_code,
                "error_type": type(exc).__name__,
            },
        )
        safe_messages = {
            ModelUnavailableError: "模型服务暂不可用，请稍后重试",
            ToolExecutionError: "外部工具暂不可用，请稍后重试",
            DatabaseUnavailableError: "数据库暂不可用",
        }
        return error_response(
            request,
            status_code=status_code,
            code=code,
            message=safe_messages.get(type(exc), str(exc) or "请求处理失败"),
        )

    @app.exception_handler(HTTPException)
    def handle_http_error(request: Request, exc: HTTPException) -> JSONResponse:
        code = "RESOURCE_NOT_FOUND" if exc.status_code == 404 else "INVALID_REQUEST"
        message = exc.detail if isinstance(exc.detail, str) else "HTTP 请求失败"
        return error_response(
            request,
            status_code=exc.status_code,
            code=code,
            message=message,
            details=None if isinstance(exc.detail, str) else exc.detail,
        )

    @app.exception_handler(Exception)
    def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unexpected_error",
            extra={
                "request_id": str(request_id_for(request)),
                "path": request.url.path,
                "status_code": 500,
                "error_type": type(exc).__name__,
            },
        )
        return error_response(
            request,
            status_code=500,
            code="INTERNAL_ERROR",
            message="服务器内部错误",
        )
