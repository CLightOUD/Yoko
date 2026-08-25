from __future__ import annotations

import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def default_timezone() -> str:
    value = os.getenv("APP_TIMEZONE", "Asia/Shanghai").strip()
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError("APP_TIMEZONE must be a valid IANA timezone") from exc
    return value
