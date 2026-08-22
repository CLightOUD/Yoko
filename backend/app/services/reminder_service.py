from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from backend.app.database import Database
from backend.app.repositories import ReminderRepository, UserRepository
from backend.app.repositories._common import normalize_datetime
from backend.app.schemas import (
    DeleteResponse,
    DueReminderQuery,
    ReminderAckRequest,
    ReminderAckResponse,
    ReminderCreateRequest,
    ReminderListQuery,
    ReminderListResponse,
    ReminderUpdateRequest,
    ReminderView,
)
from backend.app.services.errors import (
    InvalidRequestError,
    ResourceConflictError,
    ResourceNotFoundError,
)


class ReminderService:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.reminders = ReminderRepository(database)
        self.users = UserRepository(database)

    def create(self, request: ReminderCreateRequest) -> ReminderView:
        self._require_user(request.user_id)
        reminder = self.reminders.create(
            user_id=request.user_id,
            title=request.title,
            next_trigger_at=request.next_trigger_at,
            timezone=request.timezone,
            repeat_type=request.repeat_type,
        )
        return ReminderView.model_validate(reminder)

    def list(self, query: ReminderListQuery) -> ReminderListResponse:
        self._require_user(query.user_id)
        items, total = self.reminders.list(
            user_id=query.user_id,
            status=query.status,
            limit=query.limit,
            offset=query.offset,
        )
        return ReminderListResponse(items=items, total=total)

    def list_due(
        self,
        query: DueReminderQuery,
        *,
        now: datetime | None = None,
    ) -> ReminderListResponse:
        self._require_user(query.user_id)
        due_at = now or datetime.now(UTC)
        items, total = self.reminders.list_due(
            user_id=query.user_id,
            due_at=due_at,
            limit=query.limit,
        )
        return ReminderListResponse(items=items, total=total)

    def update(
        self,
        reminder_id: UUID,
        request: ReminderUpdateRequest,
        *,
        now: datetime | None = None,
    ) -> ReminderView:
        self._require_user(request.user_id)
        updates = request.model_dump(exclude={"user_id"}, exclude_unset=True)
        current = self.reminders.get_for_user(str(reminder_id), request.user_id)
        if current is None:
            raise ResourceNotFoundError("提醒不存在")
        resulting_status = updates.get("status", current["status"])
        resulting_trigger = updates.get("next_trigger_at", current["next_trigger_at"])
        if resulting_status == "active" and self._as_utc(resulting_trigger) <= (
            now or datetime.now(UTC)
        ).astimezone(UTC):
            raise InvalidRequestError("有效提醒的下一次触发时间必须晚于当前时间")
        updated = self.reminders.update(
            reminder_id=str(reminder_id),
            user_id=request.user_id,
            updates=updates,
        )
        if updated is None:
            raise ResourceNotFoundError("提醒不存在")
        return ReminderView.model_validate(updated)

    def delete(self, reminder_id: UUID, user_id: str) -> DeleteResponse:
        self._require_user(user_id)
        if not self.reminders.soft_delete(
            reminder_id=str(reminder_id), user_id=user_id
        ):
            raise ResourceNotFoundError("提醒不存在")
        return DeleteResponse(id=reminder_id, deleted=True)

    def acknowledge(
        self,
        reminder_id: UUID,
        request: ReminderAckRequest,
    ) -> ReminderAckResponse:
        expected = self._as_utc(request.expected_trigger_at)
        with self.database.transaction(immediate=True) as connection:
            if not self.users.exists(request.user_id, connection=connection):
                raise ResourceNotFoundError("用户不存在")
            current = self.reminders.get_for_user(
                str(reminder_id), request.user_id, connection=connection
            )
            if current is None:
                raise ResourceNotFoundError("提醒不存在")

            last_triggered = (
                self._as_utc(current["last_triggered_at"])
                if current["last_triggered_at"] is not None
                else None
            )
            if last_triggered == expected:
                return ReminderAckResponse(
                    reminder=ReminderView.model_validate(current),
                    already_acknowledged=True,
                )

            if current["status"] != "active":
                raise ResourceConflictError("提醒当前状态不可确认")
            if self._as_utc(current["next_trigger_at"]) != expected:
                raise ResourceConflictError("提醒触发时间已经变化")

            if current["repeat_type"] == "daily":
                next_trigger = self._next_local_day(
                    expected, timezone=current["timezone"]
                )
                status = "active"
            else:
                next_trigger = expected
                status = "completed"

            updated = self.reminders.set_acknowledged(
                reminder_id=str(reminder_id),
                user_id=request.user_id,
                last_triggered_at=expected,
                next_trigger_at=next_trigger,
                status=status,
                connection=connection,
            )
            if updated is None:
                raise ResourceConflictError("提醒在确认期间发生变化")
            return ReminderAckResponse(
                reminder=ReminderView.model_validate(updated),
                already_acknowledged=False,
            )

    def _require_user(self, user_id: str) -> None:
        if not self.users.exists(user_id):
            raise ResourceNotFoundError("用户不存在")

    @staticmethod
    def _as_utc(value: datetime | str) -> datetime:
        return datetime.fromisoformat(normalize_datetime(value))

    @staticmethod
    def _next_local_day(trigger_at: datetime, *, timezone: str) -> datetime:
        zone = ZoneInfo(timezone)
        local = trigger_at.astimezone(zone)
        next_date: date = local.date() + timedelta(days=1)
        local_time = time(
            local.hour,
            local.minute,
            local.second,
            local.microsecond,
            fold=local.fold,
        )
        return datetime.combine(next_date, local_time, tzinfo=zone)
