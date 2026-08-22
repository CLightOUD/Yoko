from __future__ import annotations

import re
from dataclasses import dataclass

from backend.app.schemas.memory import MemoryScope, TaskType


LONG_TERM_MARKERS = ("以后", "每次", "总是", "默认", "记住", "习惯", "都在", "都要")
TEMPORARY_MARKERS = ("今天", "这次", "暂时", "现在")
NEGATION_MARKERS = ("不要", "不再", "别再")
CLAUSE_SEPARATOR = re.compile(r"[，,。；;！!？?]|并且|同时|另外|以及|但是|但")
TASK_PREFERENCE_MARKERS = ("提醒", "时间", "都在", "提前", "默认")
COMMON_INPUT_CORRECTIONS = {
    "晚丄": "晚上",
    "早丄": "早上",
    "提酲": "提醒",
    "提腥": "提醒",
    "典半": "点半",
    "典": "点",
}


@dataclass(frozen=True)
class PreferenceCandidate:
    scope: MemoryScope
    task_type: TaskType
    memory_key: str
    memory_value: str
    display_text: str
    reason: str


def classify_task(text: str) -> TaskType:
    text = normalize_user_text(text)
    if "药物" in text or re.search(
        r"(?:吃|服用?|喝).{0,8}药|药.{0,8}(?:提醒|时间)", text
    ):
        return "medication"
    if any(keyword in text for keyword in ("散步", "走路", "遛弯", "锻炼")):
        return "walking"
    if any(keyword in text for keyword in ("预约", "复诊", "看诊", "挂号")):
        return "appointment"
    return "other"


def extract_preferences(text: str) -> list[PreferenceCandidate]:
    normalized = normalize_user_text(text)
    if not normalized:
        return []
    marker_positions = [
        normalized.index(marker)
        for marker in LONG_TERM_MARKERS
        if marker in normalized
    ]
    persistent = bool(marker_positions)
    if not persistent and any(marker in normalized for marker in TEMPORARY_MARKERS):
        return []
    if not persistent:
        return []

    persistent_text = normalized[min(marker_positions) :]
    clauses = [
        clause.strip()
        for clause in CLAUSE_SEPARATOR.split(persistent_text)
        if clause.strip()
    ]
    overall_task = classify_task(normalized)
    candidates: dict[tuple[TaskType, str], PreferenceCandidate] = {}

    for clause in clauses:
        if _is_negated(clause):
            continue
        if any(word in clause for word in ("简短", "简洁", "短点", "少说点")):
            candidate = PreferenceCandidate(
                scope="global",
                task_type="global",
                memory_key="response_style",
                memory_value="concise",
                display_text="回答风格偏好为简短清晰",
                reason="明确表达了后续持续适用的回答风格",
            )
            candidates[(candidate.task_type, candidate.memory_key)] = candidate
        elif any(word in clause for word in ("详细", "具体")):
            candidate = PreferenceCandidate(
                scope="global",
                task_type="global",
                memory_key="response_style",
                memory_value="detailed",
                display_text="回答风格偏好为详细具体",
                reason="明确表达了后续持续适用的回答风格",
            )
            candidates[(candidate.task_type, candidate.memory_key)] = candidate

        if "中文" in clause:
            candidate = PreferenceCandidate(
                scope="global",
                task_type="global",
                memory_key="language",
                memory_value="zh-CN",
                display_text="默认使用中文交流",
                reason="明确表达了后续持续适用的语言偏好",
            )
            candidates[(candidate.task_type, candidate.memory_key)] = candidate

        clause_task = classify_task(clause)
        if clause_task == "other" and not any(
            marker in clause for marker in TASK_PREFERENCE_MARKERS
        ):
            continue
        task_type = clause_task if clause_task != "other" else overall_task
        if task_type == "other":
            continue

        if task_type == "appointment":
            lead_time = _extract_lead_time(clause)
            if lead_time is not None:
                value, display = lead_time
                candidate = PreferenceCandidate(
                    scope="task",
                    task_type=task_type,
                    memory_key="lead_time",
                    memory_value=value,
                    display_text=f"预约提醒偏好为提前{display}",
                    reason="明确表达了后续持续适用的预约提前量",
                )
                candidates[(candidate.task_type, candidate.memory_key)] = candidate

        preferred_time = _extract_time(clause)
        if preferred_time is None:
            continue
        task_name = {
            "medication": "服药",
            "walking": "散步",
            "appointment": "预约",
        }[task_type]
        candidate = PreferenceCandidate(
            scope="task",
            task_type=task_type,
            memory_key="preferred_time",
            memory_value=preferred_time,
            display_text=f"{task_name}提醒时间偏好为{preferred_time}",
            reason=f"明确表达了后续持续适用的{task_name}提醒时间",
        )
        candidates[(candidate.task_type, candidate.memory_key)] = candidate

    return list(candidates.values())


def extract_preference(text: str) -> PreferenceCandidate | None:
    """Return the first candidate for callers that only support one preference."""
    candidates = extract_preferences(text)
    return candidates[0] if candidates else None


def normalize_user_text(text: str) -> str:
    normalized = " ".join(text.strip().split())
    for incorrect, corrected in COMMON_INPUT_CORRECTIONS.items():
        normalized = normalized.replace(incorrect, corrected)
    return normalized


def _is_negated(clause: str) -> bool:
    without_markers = clause
    for marker in LONG_TERM_MARKERS:
        without_markers = without_markers.replace(marker, "")
    stripped = without_markers.strip()
    return any(marker in stripped for marker in NEGATION_MARKERS) or stripped.startswith(
        "别"
    )


def _extract_lead_time(text: str) -> tuple[str, str] | None:
    match = re.search(r"提前\s*(\d{1,3})\s*(分钟|小时|天)", text)
    if match is None:
        return None
    amount = int(match.group(1))
    if amount < 1:
        return None
    unit = match.group(2)
    suffix = {"分钟": "m", "小时": "h", "天": "d"}[unit]
    return f"{amount}{suffix}", f"{amount}{unit}"


def _extract_time(text: str) -> str | None:
    numeric = re.search(
        r"(凌晨|早上|早晨|上午|中午|下午|晚上)?\s*"
        r"(\d{1,2})\s*(?:[:：点时]\s*(\d{1,2})?\s*分?|点半)",
        text,
    )
    if numeric is not None:
        period, hour_text, minute_text = numeric.groups()
        minute = 30 if "点半" in numeric.group(0) else int(minute_text or 0)
        return _format_time(int(hour_text), minute, period)

    chinese = re.search(
        r"(凌晨|早上|早晨|上午|中午|下午|晚上)?\s*"
        r"([零一二两三四五六七八九十]{1,3})点(半)?",
        text,
    )
    if chinese is None:
        return None
    period, hour_text, half = chinese.groups()
    return _format_time(_chinese_number(hour_text), 30 if half else 0, period)


def _format_time(hour: int, minute: int, period: str | None) -> str | None:
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None
    if period in {"下午", "晚上"} and hour < 12:
        hour += 12
    elif period == "中午" and hour < 11:
        hour += 12
    elif period in {"凌晨", "早上", "早晨", "上午"} and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute:02d}"


def _chinese_number(value: str) -> int:
    digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if value == "十":
        return 10
    if "十" in value:
        left, right = value.split("十", 1)
        return (digits.get(left, 1) * 10) + digits.get(right, 0)
    return digits[value]
