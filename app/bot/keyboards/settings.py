from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.city import CITIES
from app.services.i18n import t


SUPPORTED_LANGUAGE_BUTTONS = [
    ("uz", "🇺🇿 O'zbekcha"),
    ("ru", "🇷🇺 Русский"),
    ("en", "🇬🇧 English"),
]


def settings_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    """Main settings screen actions.

    Callback names are settings-scoped on purpose. The onboarding handlers also
    use language/city callbacks, and sharing those callbacks was the root cause
    of several settings regressions.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "settings.action.language"), callback_data="settings:language")],
        [InlineKeyboardButton(text=t(language, "settings.action.city"), callback_data="settings:city")],
        [InlineKeyboardButton(text=t(language, "settings.action.prayer_reminders"), callback_data="settings:prayer_reminders")],
        [InlineKeyboardButton(text=t(language, "settings.action.qazo_reminders"), callback_data="settings:qazo_reminders")],
        [InlineKeyboardButton(text=t(language, "settings.action.reminder_times"), callback_data="settings:qazo_times")],
        [InlineKeyboardButton(text=t(language, "settings.action.daily_limit"), callback_data="settings:daily_limit")],
        [InlineKeyboardButton(text=t(language, "settings.action.quiet_hours"), callback_data="settings:quiet_hours")],
        [InlineKeyboardButton(text=t(language, "settings.action.privacy"), callback_data="settings:privacy")],
        [InlineKeyboardButton(text=t(language, "common.home"), callback_data="dashboard")],
    ])


def settings_language_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"settings:set_language:{code}")]
        for code, label in SUPPORTED_LANGUAGE_BUTTONS
    ]
    rows.append([InlineKeyboardButton(text=t(language, "common.back"), callback_data="settings:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_city_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(CITIES), 2):
        rows.append([
            InlineKeyboardButton(text=city, callback_data=f"settings:set_city:{city}")
            for city in CITIES[i:i + 2]
        ])
    rows.append([InlineKeyboardButton(text=t(language, "city.other"), callback_data="settings:city_custom")])
    rows.append([InlineKeyboardButton(text=t(language, "common.back"), callback_data="settings:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_back_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "common.back"), callback_data="settings:open")],
        [InlineKeyboardButton(text=t(language, "common.cancel"), callback_data="settings:cancel")],
    ])


def settings_daily_limit_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1", callback_data="settings:set_daily_limit:1"),
            InlineKeyboardButton(text="2", callback_data="settings:set_daily_limit:2"),
            InlineKeyboardButton(text="3", callback_data="settings:set_daily_limit:3"),
        ],
        [InlineKeyboardButton(text=t(language, "settings.action.custom_number"), callback_data="settings:daily_limit_custom")],
        [InlineKeyboardButton(text=t(language, "common.back"), callback_data="settings:open")],
    ])
