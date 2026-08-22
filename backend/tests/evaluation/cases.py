from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Scope = Literal["global", "task"]
TaskType = Literal["global", "medication", "walking", "appointment", "other"]


@dataclass(frozen=True)
class MemorySeed:
    scope: Scope
    task_type: TaskType
    memory_key: str
    memory_value: str
    display_text: str
    active: bool = True
    user_id: str = "demo-user"


@dataclass(frozen=True)
class MemoryEvaluationCase:
    case_id: str
    description: str
    task_type: TaskType
    seeds: tuple[MemorySeed, ...]
    expected_identities: tuple[str, ...]
    expected_values: tuple[tuple[str, str], ...] = ()
    limit: int = 3


def seed(
    task_type: TaskType,
    key: str,
    value: str,
    *,
    active: bool = True,
    user_id: str = "demo-user",
) -> MemorySeed:
    scope: Scope = "global" if task_type == "global" else "task"
    return MemorySeed(
        scope=scope,
        task_type=task_type,
        memory_key=key,
        memory_value=value,
        display_text=f"{task_type}:{key}={value}",
        active=active,
        user_id=user_id,
    )


FIXED_MEMORY_CASES: tuple[MemoryEvaluationCase, ...] = (
    MemoryEvaluationCase(
        "M01",
        "没有记忆时返回空列表",
        "medication",
        (),
        (),
    ),
    MemoryEvaluationCase(
        "M02",
        "仅有全局语言偏好时可跨任务检索",
        "medication",
        (seed("global", "language", "zh-CN"),),
        ("global:language",),
    ),
    MemoryEvaluationCase(
        "M03",
        "检索同任务的服药时间偏好",
        "medication",
        (seed("medication", "preferred_time", "19:00"),),
        ("medication:preferred_time",),
    ),
    MemoryEvaluationCase(
        "M04",
        "过滤其他任务的偏好",
        "medication",
        (
            seed("medication", "preferred_time", "19:00"),
            seed("walking", "preferred_time", "07:00"),
        ),
        ("medication:preferred_time",),
    ),
    MemoryEvaluationCase(
        "M05",
        "任务记忆优先于全局记忆",
        "medication",
        (
            seed("global", "language", "zh-CN"),
            seed("medication", "preferred_time", "19:00"),
        ),
        ("medication:preferred_time", "global:language"),
    ),
    MemoryEvaluationCase(
        "M06",
        "没有匹配任务记忆时只返回全局记忆",
        "appointment",
        (
            seed("global", "tone", "gentle"),
            seed("walking", "preferred_time", "07:00"),
        ),
        ("global:tone",),
    ),
    MemoryEvaluationCase(
        "M07",
        "停用的任务记忆不参与检索",
        "medication",
        (seed("medication", "preferred_time", "19:00", active=False),),
        (),
    ),
    MemoryEvaluationCase(
        "M08",
        "停用全局记忆和无关有效记忆均被过滤",
        "medication",
        (
            seed("global", "language", "zh-CN", active=False),
            seed("walking", "preferred_time", "07:00"),
        ),
        (),
    ),
    MemoryEvaluationCase(
        "M09",
        "相同任务和键的新值覆盖旧值",
        "medication",
        (
            seed("medication", "preferred_time", "20:00"),
            seed("medication", "preferred_time", "19:00"),
        ),
        ("medication:preferred_time",),
        (("medication:preferred_time", "19:00"),),
    ),
    MemoryEvaluationCase(
        "M10",
        "相同键可在不同任务中隔离",
        "walking",
        (
            seed("medication", "preferred_time", "19:00"),
            seed("walking", "preferred_time", "07:00"),
        ),
        ("walking:preferred_time",),
        (("walking:preferred_time", "07:00"),),
    ),
    MemoryEvaluationCase(
        "M11",
        "同任务超过三条时只返回最近三条",
        "other",
        (
            seed("other", "key_1", "v1"),
            seed("other", "key_2", "v2"),
            seed("other", "key_3", "v3"),
            seed("other", "key_4", "v4"),
        ),
        ("other:key_4", "other:key_3", "other:key_2"),
    ),
    MemoryEvaluationCase(
        "M12",
        "三条上限内先取任务记忆再取最新全局记忆",
        "medication",
        (
            seed("global", "language", "zh-CN"),
            seed("global", "tone", "gentle"),
            seed("medication", "dosage_form", "tablet"),
            seed("medication", "preferred_time", "19:00"),
        ),
        (
            "medication:preferred_time",
            "medication:dosage_form",
            "global:tone",
        ),
    ),
    MemoryEvaluationCase(
        "M13",
        "其他用户的记忆不能被检索",
        "appointment",
        (seed("appointment", "lead_time", "30m", user_id="other-user"),),
        (),
    ),
    MemoryEvaluationCase(
        "M14",
        "相同键的跨用户数据只返回当前用户值",
        "walking",
        (
            seed("walking", "preferred_time", "08:00", user_id="other-user"),
            seed("walking", "preferred_time", "07:00"),
        ),
        ("walking:preferred_time",),
        (("walking:preferred_time", "07:00"),),
    ),
    MemoryEvaluationCase(
        "M15",
        "新的明确偏好可重新启用原停用键并覆盖值",
        "appointment",
        (
            seed("appointment", "lead_time", "15m", active=False),
            seed("appointment", "lead_time", "30m"),
        ),
        ("appointment:lead_time",),
        (("appointment:lead_time", "30m"),),
    ),
)


assert len(FIXED_MEMORY_CASES) == 15
