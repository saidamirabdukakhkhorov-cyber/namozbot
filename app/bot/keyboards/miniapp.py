from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.core.config import settings
from app.services.i18n import t


def mini_app_keyboard(language: str) -> InlineKeyboardMarkup:
    url = getattr(settings, "webapp_url", "") or ""
    text = t(language, "miniapp.open")
    if url:
        button = InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))
    else:
        button = InlineKeyboardButton(text=text, callback_data="miniapp:not_configured")
    return InlineKeyboardMarkup(inline_keyboard=[[button]])
