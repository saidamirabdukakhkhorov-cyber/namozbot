from __future__ import annotations

from typing import Iterable, Protocol

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.constants import PRAYER_NAMES
from app.services.i18n import prayer_label, t


class DailyPrayerLike(Protocol):
    id: int
    prayer_name: str
    status: str


def today_prayers_keyboard(language: str, daily_prayers: Iterable[DailyPrayerLike]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    current_row: list[InlineKeyboardButton] = []
    for daily in daily_prayers:
        current_row.append(InlineKeyboardButton(text=prayer_label(language, daily.prayer_name), callback_data=f"today:detail:{daily.id}"))
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)
    rows.append([InlineKeyboardButton(text=t(language, "common.home"), callback_data="dashboard")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def prayer_status_keyboard(language: str, daily_prayer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "today.action.read"), callback_data=f"daily:prayed:{daily_prayer_id}")],
        [InlineKeyboardButton(text=t(language, "today.action.qazo"), callback_data=f"daily:missed:{daily_prayer_id}")],
        [InlineKeyboardButton(text=t(language, "today.action.snooze"), callback_data=f"daily:snooze:{daily_prayer_id}")],
        [InlineKeyboardButton(text=t(language, "common.back"), callback_data="today:open")],
    ])


def prayers_status_keyboard(language: str, daily_prayers: Iterable[DailyPrayerLike]) -> InlineKeyboardMarkup | None:
    # Backward compatible alias. Premium UX uses today_prayers_keyboard.
    return today_prayers_keyboard(language, daily_prayers)


def snooze_keyboard(language: str, daily_prayer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t(language, "today.snooze.15"), callback_data=f"snooze:15:{daily_prayer_id}"),
            InlineKeyboardButton(text=t(language, "today.snooze.30"), callback_data=f"snooze:30:{daily_prayer_id}"),
        ],
        [InlineKeyboardButton(text=t(language, "today.snooze.60"), callback_data=f"snooze:60:{daily_prayer_id}")],
        [InlineKeyboardButton(text=t(language, "common.back"), callback_data=f"today:detail:{daily_prayer_id}")],
    ])


def prayer_select_keyboard(language: str, prefix: str) -> InlineKeyboardMarkup:
    rows = []
    for p in PRAYER_NAMES:
        rows.append([InlineKeyboardButton(text=prayer_label(language, p), callback_data=f"{prefix}:{p}")])
    rows.append([InlineKeyboardButton(text=t(language, "common.back"), callback_data="qazo_add:start")])
    rows.append([InlineKeyboardButton(text=t(language, "common.cancel"), callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def prayers_batch_status_keyboard(language: str, daily_prayers: Iterable[DailyPrayerLike]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for daily in daily_prayers:
        rows.append([
            InlineKeyboardButton(
                text=prayer_label(language, daily.prayer_name),
                callback_data=f"today:detail:{daily.id}",
            )
        ])
        rows.append([
            InlineKeyboardButton(text=t(language, "today.action.read"), callback_data=f"daily:prayed:{daily.id}"),
            InlineKeyboardButton(text=t(language, "today.action.qazo"), callback_data=f"daily:missed:{daily.id}"),
            InlineKeyboardButton(text=t(language, "today.action.snooze"), callback_data=f"daily:snooze:{daily.id}"),
        ])
    rows.append([InlineKeyboardButton(text=t(language, "menu.today"), callback_data="today:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
