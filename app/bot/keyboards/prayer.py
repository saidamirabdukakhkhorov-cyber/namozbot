from __future__ import annotations

from typing import Iterable, Protocol

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.constants import PRAYER_NAMES
from app.services.i18n import prayer_label, t


class DailyPrayerLike(Protocol):
    id: int
    prayer_name: str
    status: str


def prayer_status_keyboard(language: str, daily_prayer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(language, "prayer.prayed"), callback_data=f"daily:prayed:{daily_prayer_id}")],
            [InlineKeyboardButton(text=t(language, "prayer.missed"), callback_data=f"daily:missed:{daily_prayer_id}")],
            [InlineKeyboardButton(text=t(language, "prayer.snooze"), callback_data=f"daily:snooze:{daily_prayer_id}")],
        ]
    )


def prayers_status_keyboard(language: str, daily_prayers: Iterable[DailyPrayerLike]) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    for daily in daily_prayers:
        if daily.status not in {"pending", "snoozed"}:
            continue
        label = prayer_label(language, daily.prayer_name)
        rows.append(
            [
                InlineKeyboardButton(text=f"✅ {label}", callback_data=f"daily:prayed:{daily.id}"),
                InlineKeyboardButton(text=f"📌 {label}", callback_data=f"daily:missed:{daily.id}"),
            ]
        )
        rows.append([InlineKeyboardButton(text=f"⏰ {label}", callback_data=f"daily:snooze:{daily.id}")])
    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)


def snooze_keyboard(language: str, daily_prayer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="15 daqiqa", callback_data=f"snooze:15:{daily_prayer_id}"),
                InlineKeyboardButton(text="30 daqiqa", callback_data=f"snooze:30:{daily_prayer_id}"),
            ],
            [InlineKeyboardButton(text="1 soat", callback_data=f"snooze:60:{daily_prayer_id}")],
            [InlineKeyboardButton(text=t(language, "common.cancel"), callback_data="cancel")],
        ]
    )


def prayer_select_keyboard(language: str, prefix: str) -> InlineKeyboardMarkup:
    rows = []
    for p in PRAYER_NAMES:
        rows.append([InlineKeyboardButton(text=prayer_label(language, p), callback_data=f"{prefix}:{p}")])
    rows.append([InlineKeyboardButton(text=t(language, "common.back"), callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
