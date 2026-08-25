from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
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
    MAX_MERGED_TITLE_LENGTH = 4000
    REPEAT_PRIORITY = {"none": 1, "weekly": 2, "daily": 3}

    def __init__(self, database: Database) -> None:
        self.database = database
        self.reminders = ReminderRepository(database)
        self.users = UserRepository(database)

    def create(
        self,
        request: ReminderCreateRequest,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> ReminderView:
        with self._write_transaction(connection) as connection:
            self._require_user(request.user_id, connection=connection)
            time_matches = self.reminders.list_active_at_time(
                user_id=request.user_id,
                next_trigger_at=request.next_trigger_at,
                timezone=request.timezone,
                connection=connection,
            )
            same_repeat = [
                match
                for match in time_matches
                if match["repeat_type"] == request.repeat_type
            ]
            same_title_other_repeat = [
                match
                for match in time_matches
                if match["repeat_type"] != request.repeat_type
                and self._titles_equivalent(match["title"], request.title)
            ]
            stronger = [
                match
                for match in same_title_other_repeat
                if self.REPEAT_PRIORITY[match["repeat_type"]]
                > self.REPEAT_PRIORITY[request.repeat_type]
            ]

            if stronger:
                reminder = self._keep_strongest(
                    matches=same_title_other_repeat,
                    connection=connection,
                )
            elif same_repeat:
                reminder = self._consolidate_matches(
                    canonical=same_repeat[0],
                    matches=same_repeat[1:],
                    requested_title=request.title,
                    connection=connection,
                )
                self._delete_matches(
                    same_title_other_repeat,
                    keep_id=None,
                    connection=connection,
                )
            elif same_title_other_repeat:
                reminder = self._keep_strongest(
                    matches=same_title_other_repeat,
                    connection=connection,
                )
                updated = self.reminders.update(
                    reminder_id=reminder["id"],
                    user_id=reminder["user_id"],
                    updates={"repeat_type": request.repeat_type},
                    connection=connection,
                )
                if updated is None:
                    raise ResourceConflictError("提醒在升级周期期间发生变化")
                reminder = updated
            else:
                reminder = self.reminders.create(
                    user_id=request.user_id,
                    title=request.title,
                    next_trigger_at=request.next_trigger_at,
                    timezone=request.timezone,
                    repeat_type=request.repeat_type,
                    connection=connection,
                )
        return ReminderView.model_validate(reminder)

    def list(
        self,
        query: ReminderListQuery,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> ReminderListResponse:
        self._require_user(query.user_id, connection=connection)
        items, total = self.reminders.list(
            user_id=query.user_id,
            status=query.status,
            limit=query.limit,
            offset=query.offset,
            connection=connection,
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
        connection: sqlite3.Connection | None = None,
    ) -> ReminderView:
        updates = request.model_dump(exclude={"user_id"}, exclude_unset=True)
        with self._write_transaction(connection) as connection:
            self._require_user(request.user_id, connection=connection)
            current = self.reminders.get_for_user(
                str(reminder_id), request.user_id, connection=connection
            )
            if current is None:
                raise ResourceNotFoundError("提醒不存在")
            resulting_status = updates.get("status", current["status"])
            resulting_trigger = updates.get(
                "next_trigger_at", current["next_trigger_at"]
            )
            if resulting_status == "active" and self._as_utc(resulting_trigger) <= (
                now or datetime.now(UTC)
            ).astimezone(UTC):
                raise InvalidRequestError("有效提醒的下一次触发时间必须晚于当前时间")

            if resulting_status == "active":
                resulting_timezone = updates.get("timezone", current["timezone"])
                resulting_repeat = updates.get(
                    "repeat_type", current["repeat_type"]
                )
                resulting_title = updates.get("title", current["title"])
                time_matches = self.reminders.list_active_at_time(
                    user_id=request.user_id,
                    next_trigger_at=resulting_trigger,
                    timezone=resulting_timezone,
                    exclude_id=str(reminder_id),
                    connection=connection,
                )
                same_repeat = [
                    match
                    for match in time_matches
                    if match["repeat_type"] == resulting_repeat
                ]
                same_title_other_repeat = [
                    match
                    for match in time_matches
                    if match["repeat_type"] != resulting_repeat
                    and self._titles_equivalent(match["title"], resulting_title)
                ]
                stronger = [
                    match
                    for match in same_title_other_repeat
                    if self.REPEAT_PRIORITY[match["repeat_type"]]
                    > self.REPEAT_PRIORITY[resulting_repeat]
                ]
                if stronger:
                    survivor = self._keep_strongest(
                        matches=same_title_other_repeat,
                        connection=connection,
                    )
                    self.reminders.soft_delete(
                        reminder_id=str(reminder_id),
                        user_id=request.user_id,
                        connection=connection,
                    )
                    return ReminderView.model_validate(survivor)

                if same_repeat:
                    updates["title"] = self._merge_titles(
                        resulting_title,
                        *(match["title"] for match in same_repeat),
                    )
                    self._delete_matches(
                        same_repeat,
                        keep_id=None,
                        connection=connection,
                    )
                self._delete_matches(
                    same_title_other_repeat,
                    keep_id=None,
                    connection=connection,
                )

            updated = self.reminders.update(
                reminder_id=str(reminder_id),
                user_id=request.user_id,
                updates=updates,
                connection=connection,
            )
            if updated is None:
                raise ResourceNotFoundError("提醒不存在")
        return ReminderView.model_validate(updated)

    def delete(
        self,
        reminder_id: UUID,
        user_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> DeleteResponse:
        self._require_user(user_id, connection=connection)
        if not self.reminders.soft_delete(
            reminder_id=str(reminder_id), user_id=user_id, connection=connection
        ):
            raise ResourceNotFoundError("提醒不存在")
        return DeleteResponse(id=reminder_id, deleted=True)

    def acknowledge(
        self,
        reminder_id: UUID,
        request: ReminderAckRequest,
        *,
        now: datetime | None = None,
    ) -> ReminderAckResponse:
        expected = self._as_utc(request.expected_trigger_at)
        acknowledged_at = (now or datetime.now(UTC)).astimezone(UTC)
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

            repeat_days = {"daily": 1, "weekly": 7}.get(current["repeat_type"])
            if repeat_days is not None:
                next_trigger = self._next_local_occurrence(
                    expected,
                    timezone=current["timezone"],
                    days=repeat_days,
                )
                while next_trigger <= acknowledged_at:
                    next_trigger = self._next_local_occurrence(
                        next_trigger,
                        timezone=current["timezone"],
                        days=repeat_days,
                    )
                status = "active"
            else:
                next_trigger = expected
                status = "completed"

            if status == "active":
                time_matches = self.reminders.list_active_at_time(
                    user_id=request.user_id,
                    next_trigger_at=next_trigger,
                    timezone=current["timezone"],
                    exclude_id=str(reminder_id),
                    connection=connection,
                )
                same_repeat = [
                    match
                    for match in time_matches
                    if match["repeat_type"] == current["repeat_type"]
                ]
                same_title_other_repeat = [
                    match
                    for match in time_matches
                    if match["repeat_type"] != current["repeat_type"]
                    and self._titles_equivalent(match["title"], current["title"])
                ]
                stronger = [
                    match
                    for match in same_title_other_repeat
                    if self.REPEAT_PRIORITY[match["repeat_type"]]
                    > self.REPEAT_PRIORITY[current["repeat_type"]]
                ]
                if stronger:
                    self._keep_strongest(
                        matches=same_title_other_repeat,
                        connection=connection,
                    )
                    completed = self.reminders.set_acknowledged(
                        reminder_id=str(reminder_id),
                        user_id=request.user_id,
                        last_triggered_at=expected,
                        next_trigger_at=expected,
                        status="completed",
                        connection=connection,
                    )
                    if completed is None:
                        raise ResourceConflictError("提醒在确认期间发生变化")
                    return ReminderAckResponse(
                        reminder=ReminderView.model_validate(completed),
                        already_acknowledged=False,
                    )

                if same_repeat:
                    current = self._consolidate_matches(
                        canonical=current,
                        matches=same_repeat,
                        requested_title=current["title"],
                        connection=connection,
                    )
                self._delete_matches(
                    same_title_other_repeat,
                    keep_id=None,
                    connection=connection,
                )

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

    def _require_user(
        self,
        user_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if not self.users.exists(user_id, connection=connection):
            raise ResourceNotFoundError("用户不存在")

    @contextmanager
    def _write_transaction(
        self,
        connection: sqlite3.Connection | None,
    ) -> Iterator[sqlite3.Connection]:
        if connection is not None:
            yield connection
            return
        with self.database.transaction(immediate=True) as active_connection:
            yield active_connection

    def _consolidate_matches(
        self,
        *,
        canonical: dict,
        matches: list[dict],
        requested_title: str,
        connection: sqlite3.Connection,
    ) -> dict:
        merged_title = self._merge_titles(
            canonical["title"],
            *(match["title"] for match in matches),
            requested_title,
        )
        if merged_title != canonical["title"]:
            updated = self.reminders.update(
                reminder_id=canonical["id"],
                user_id=canonical["user_id"],
                updates={"title": merged_title},
                connection=connection,
            )
            if updated is None:
                raise ResourceConflictError("提醒在合并期间发生变化")
            canonical = updated
        for match in matches:
            self.reminders.soft_delete(
                reminder_id=match["id"],
                user_id=canonical["user_id"],
                connection=connection,
            )
        return canonical

    def _keep_strongest(
        self,
        *,
        matches: list[dict],
        connection: sqlite3.Connection,
    ) -> dict:
        strongest = min(
            matches,
            key=lambda match: (
                -self.REPEAT_PRIORITY[match["repeat_type"]],
                match["created_at"],
                match["id"],
            ),
        )
        self._delete_matches(matches, keep_id=strongest["id"], connection=connection)
        return strongest

    def _delete_matches(
        self,
        matches: list[dict],
        *,
        keep_id: str | None,
        connection: sqlite3.Connection,
    ) -> None:
        for match in matches:
            if match["id"] == keep_id:
                continue
            self.reminders.soft_delete(
                reminder_id=match["id"],
                user_id=match["user_id"],
                connection=connection,
            )

    @classmethod
    def _titles_equivalent(cls, left: str, right: str) -> bool:
        return cls._title_keys(left) == cls._title_keys(right)

    @classmethod
    def _title_keys(cls, title: str) -> frozenset[str]:
        return frozenset(
            cls._canonical_title_item(item)
            for item in title.split("；")
            if item.strip()
        )

    @staticmethod
    def _canonical_title_item(item: str) -> str:
        normalized = re.sub(r"[\s，,。.!！?？、:：]+", "", item).casefold()
        normalized = re.sub(r"^(?:请)?(?:提醒我|记得)", "", normalized)
        medication = re.fullmatch(r"(?:吃|服用?|喝)(.+药)", normalized)
        if medication is not None:
            return f"medication:{medication.group(1)}"
        walking = re.fullmatch(r"(?:去|出去)?(?:散步|走路|遛弯)", normalized)
        if walking is not None:
            return "walking"
        return normalized

    @classmethod
    def _merge_titles(cls, *titles: str) -> str:
        items: list[str] = []
        item_keys: set[str] = set()
        for title in titles:
            for item in title.split("；"):
                normalized = item.strip()
                key = cls._canonical_title_item(normalized)
                if normalized and key not in item_keys:
                    items.append(normalized)
                    item_keys.add(key)
        merged = "；".join(items)
        if len(merged) > cls.MAX_MERGED_TITLE_LENGTH:
            raise InvalidRequestError("同一时间的提醒内容合并后过长，请缩短提醒内容")
        return merged

    @staticmethod
    def _as_utc(value: datetime | str) -> datetime:
        return datetime.fromisoformat(normalize_datetime(value))

    @staticmethod
    def _next_local_occurrence(
        trigger_at: datetime,
        *,
        timezone: str,
        days: int,
    ) -> datetime:
        zone = ZoneInfo(timezone)
        local = trigger_at.astimezone(zone)
        next_date: date = local.date() + timedelta(days=days)
        local_time = time(
            local.hour,
            local.minute,
            local.second,
            local.microsecond,
            fold=local.fold,
        )
        return datetime.combine(next_date, local_time, tzinfo=zone)
