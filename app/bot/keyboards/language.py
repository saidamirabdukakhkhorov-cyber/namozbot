from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from app.services.i18n import t


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang:uz")],
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en")],
    ])


def onboarding_continue_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "common.continue"), callback_data="onboarding:privacy")],
    ])


def onboarding_privacy_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "common.continue"), callback_data="onboarding:city")],
    ])


def onboarding_reminder_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "onboarding.reminders.enable"), callback_data="onboarding:reminders:on")],
        [InlineKeyboardButton(text=t(language, "onboarding.reminders.skip"), callback_data="onboarding:reminders:off")],
        [InlineKeyboardButton(text=t(language, "common.back"), callback_data="onboarding:city")],
    ])
