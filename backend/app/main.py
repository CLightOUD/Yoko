from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.app.agent import AgentRuntime, LangChainAgent
from backend.app.api.chat import router as chat_router
from backend.app.api.errors import install_error_handlers
from backend.app.api.feedback import router as feedback_router
from backend.app.api.health import router as health_router
from backend.app.api.memories import router as memories_router
from backend.app.api.metrics import router as metrics_router
from backend.app.api.reminders import router as reminders_router
from backend.app.database import Database
from backend.app.services import MemoryService, MetricsService, ReminderService
from backend.app.services.chat_service import ChatService
from backend.app.services.feedback_service import FeedbackService

load_dotenv()


def create_app(
    *,
    database: Database | None = None,
    agent: AgentRuntime | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        active_database = database or Database()
        active_database.initialize()
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
        app.state.reminder_service = reminder_service
        app.state.memory_service = memory_service
        app.state.metrics_service = metrics_service
        app.state.feedback_service = feedback_service
        app.state.chat_service = chat_service
        yield

    application = FastAPI(title="Yoko API", version="0.1.0", lifespan=lifespan)
    frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:5173")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def attach_request_id(request: Request, call_next):
        request.state.request_id = uuid4()
        response = await call_next(request)
        response.headers["X-Request-ID"] = str(request.state.request_id)
        return response

    install_error_handlers(application)
    application.include_router(health_router)
    application.include_router(chat_router)
    application.include_router(feedback_router)
    application.include_router(reminders_router)
    application.include_router(memories_router)
    application.include_router(metrics_router)
    return application


app = create_app()
