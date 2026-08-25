from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.agent import AgentRuntime, LangChainAgent
from backend.app.api.auth import account_router, router as auth_router
from backend.app.api.chat import router as chat_router
from backend.app.api.errors import error_response, install_error_handlers
from backend.app.api.feedback import router as feedback_router
from backend.app.api.health import router as health_router
from backend.app.api.memories import router as memories_router
from backend.app.api.metrics import router as metrics_router
from backend.app.api.reminders import router as reminders_router
from backend.app.database import Database
from backend.app.logging_config import configure_logging
from backend.app.rate_limit import RequestRateLimiter
from backend.app.services import MemoryService, MetricsService, ReminderService
from backend.app.services.auth_service import AuthService
from backend.app.services.chat_service import ChatService
from backend.app.services.feedback_service import FeedbackService

load_dotenv()
logger = logging.getLogger("yoko.http")
DEFAULT_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def create_app(
    *,
    database: Database | None = None,
    agent: AgentRuntime | None = None,
    auth_service: AuthService | None = None,
    frontend_dist: Path | None = DEFAULT_FRONTEND_DIST,
) -> FastAPI:
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        active_database = database or Database()
        active_database.initialize()
        active_auth_service = auth_service or AuthService(active_database)
        reminder_service = ReminderService(active_database)
        memory_service = MemoryService(active_database)
        metrics_service = MetricsService(active_database)
        feedback_service = FeedbackService(active_database, memory_service)
        chat_service = ChatService(
            active_database,
            memory_service=memory_service,
            reminder_service=reminder_service,
            metrics_service=metrics_service,
            agent=agent or LangChainAgent(),
        )
        app.state.database = active_database
        app.state.auth_service = active_auth_service
        app.state.reminder_service = reminder_service
        app.state.memory_service = memory_service
        app.state.metrics_service = metrics_service
        app.state.feedback_service = feedback_service
        app.state.chat_service = chat_service
        yield

    application = FastAPI(title="Yoko API", version="0.5.0", lifespan=lifespan)
    frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:5173")
    rate_limiter = RequestRateLimiter()

    @application.middleware("http")
    async def attach_request_id(request: Request, call_next):
        request.state.request_id = uuid4()
        started = perf_counter()
        status_code = 500
        try:
            session_token = request.cookies.get(
                os.getenv("AUTH_COOKIE_NAME", "yoko_session")
            )
            limited = rate_limiter.check(
                path=request.url.path,
                method=request.method,
                client_host=request.client.host if request.client else "unknown",
                session_token=session_token,
            )
            if limited is None:
                response = await call_next(request)
            else:
                response = error_response(
                    request,
                    status_code=429,
                    code="TOO_MANY_ATTEMPTS",
                    message="请求过于频繁，请稍后重试",
                )
                response.headers["Retry-After"] = str(limited.retry_after)
                response.headers["X-RateLimit-Limit"] = str(limited.limit)
                response.headers["X-RateLimit-Remaining"] = "0"
            status_code = response.status_code
            response.headers["X-Request-ID"] = str(request.state.request_id)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Permissions-Policy"] = (
                "camera=(), microphone=(), geolocation=()"
            )
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                "connect-src 'self'; object-src 'none'; base-uri 'self'; "
                "frame-ancestors 'none'; form-action 'self'"
            )
            if request.url.path.startswith("/api/"):
                response.headers["Cache-Control"] = "no-store"
            if request.url.scheme == "https":
                response.headers["Strict-Transport-Security"] = (
                    "max-age=31536000; includeSubDomains"
                )
            return response
        finally:
            logger.info(
                "http_request",
                extra={
                    "request_id": str(request.state.request_id),
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": max(
                        0, round((perf_counter() - started) * 1000)
                    ),
                },
            )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=[frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    install_error_handlers(application)
    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(account_router)
    application.include_router(chat_router)
    application.include_router(feedback_router)
    application.include_router(reminders_router)
    application.include_router(memories_router)
    application.include_router(metrics_router)

    # Keep this mount last so API, OpenAPI, and documentation routes win first.
    if frontend_dist is not None and (frontend_dist / "index.html").is_file():
        application.mount(
            "/",
            StaticFiles(directory=frontend_dist, html=True),
            name="frontend",
        )
    return application


app = create_app()
