from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

TASHKENT_TIMEZONE = "Asia/Tashkent"
TASHKENT_TZ = ZoneInfo(TASHKENT_TIMEZONE)

def tashkent_now() -> datetime:
    return datetime.now(TASHKENT_TZ)

def tashkent_today() -> date:
    return tashkent_now().date()

def user_timezone_name(user_timezone: str | None = None) -> str:
    return user_timezone or TASHKENT_TIMEZONE
