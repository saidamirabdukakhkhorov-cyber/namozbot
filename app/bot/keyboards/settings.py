from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from app.services.i18n import t


def settings_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "settings.action.language"), callback_data="settings:language")],
        [InlineKeyboardButton(text=t(language, "settings.action.city"), callback_data="settings:city")],
        [InlineKeyboardButton(text=t(language, "settings.action.prayer_reminders"), callback_data="settings:prayer_reminders")],
        [InlineKeyboardButton(text=t(language, "settings.action.qazo_reminders"), callback_data="settings:qazo_reminders")],
        [InlineKeyboardButton(text=t(language, "settings.action.reminder_times"), callback_data="settings:qazo_times")],
        [InlineKeyboardButton(text=t(language, "settings.action.quiet_hours"), callback_data="settings:quiet_hours")],
        [InlineKeyboardButton(text=t(language, "settings.action.privacy"), callback_data="privacy")],
        [InlineKeyboardButton(text=t(language, "common.home"), callback_data="dashboard")],
    ])


def settings_back_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "common.back"), callback_data="settings:open")],
    ])
