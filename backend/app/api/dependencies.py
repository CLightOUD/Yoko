from fastapi import Request

from backend.app.database import Database
from backend.app.services import MemoryService, MetricsService, ReminderService
from backend.app.services.chat_service import ChatService
from backend.app.services.feedback_service import FeedbackService


def get_database(request: Request) -> Database:
    return request.app.state.database


def get_reminder_service(request: Request) -> ReminderService:
    return request.app.state.reminder_service


def get_memory_service(request: Request) -> MemoryService:
    return request.app.state.memory_service


def get_metrics_service(request: Request) -> MetricsService:
    return request.app.state.metrics_service


def get_feedback_service(request: Request) -> FeedbackService:
    return request.app.state.feedback_service


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service
