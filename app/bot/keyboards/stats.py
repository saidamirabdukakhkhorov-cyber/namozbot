from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from app.services.i18n import t


def stats_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "period.today"), callback_data="stats:period:today"), InlineKeyboardButton(text=t(language, "period.this_week"), callback_data="stats:period:this_week")],
        [InlineKeyboardButton(text=t(language, "period.this_month"), callback_data="stats:period:this_month"), InlineKeyboardButton(text=t(language, "period.custom"), callback_data="stats:period:custom")],
        [InlineKeyboardButton(text=t(language, "menu.qazo"), callback_data="qazo:overview")],
        [InlineKeyboardButton(text=t(language, "common.home"), callback_data="dashboard")],
    ])
