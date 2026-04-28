from __future__ import annotations

import re
from typing import Literal

from aiogram import F
from aiogram.filters import BaseFilter
from aiogram.types import Message

_VARIATION_SELECTORS = {"\ufe0f", "\ufe0e"}
_ZERO_WIDTH = {"\u200d", "\u200c", "\u200b"}
_APOSTROPHES = {
    "‘": "'",
    "’": "'",
    "ʼ": "'",
    "ʻ": "'",
    "`": "'",
    "´": "'",
}

GlobalMenuAction = Literal[
    "home",
    "today",
    "qazo",
    "qazo_add",
    "calculator",
    "stats",
    "settings",
    "help",
    "admin",
]


def normalize_button_text(value: str | None) -> str:
    """Normalize Telegram button text for reliable Reply Keyboard matching.

    Telegram clients may send emoji buttons with/without variation selectors
    (for example, "⚙️ Sozlamalar" vs "⚙ Sozlamalar"). Some keyboards may
    also include typographic apostrophes. Normalizing text keeps global
    navigation reliable across Telegram clients and platforms.
    """
    text = value or ""
    for marker in _VARIATION_SELECTORS | _ZERO_WIDTH:
        text = text.replace(marker, "")
    for src, dst in _APOSTROPHES.items():
        text = text.replace(src, dst)
    return " ".join(text.strip().split()).casefold()


def _without_leading_icon(value: str) -> str:
    """Remove leading emoji/symbols from a normalized menu label."""
    return re.sub(r"^[^\w/а-яА-ЯёЁўқғҳЎҚҒҲ]+", "", value).strip()


def text_is_one_of(*values: str):
    expected = {normalize_button_text(value) for value in values}
    expected |= {_without_leading_icon(value) for value in expected}
    return F.text.func(lambda text: normalize_button_text(text) in expected or _without_leading_icon(normalize_button_text(text)) in expected)


_GLOBAL_MENU_ALIASES: dict[GlobalMenuAction, set[str]] = {
    "home": {
        "/home",
        "menu",
        "asosiy menu",
        "главное меню",
        "main menu",
    },
    "today": {
        "/today",
        "bugungi namozlar",
        "намазы на сегодня",
        "today's prayers",
        "today’s prayers",
        "today prayers",
    },
    "qazo": {
        "/qazo",
        "qazo namozlarim",
        "мои каза-намазы",
        "мои каза намазы",
        "my missed prayers",
    },
    "qazo_add": {
        "qazo qo'shish",
        "добавить каза",
        "add missed prayer",
    },
    "calculator": {
        "qazo kalkulyator",
        "калькулятор каза",
        "missed prayer calculator",
    },
    "stats": {
        "/stats",
        "statistika",
        "статистика",
        "statistics",
    },
    "settings": {
        "/settings",
        "sozlamalar",
        "настройки",
        "settings",
    },
    "help": {
        "/help",
        "yordam",
        "помощь",
        "help",
    },
    "admin": {
        "/admin",
        "admin panel",
        "админ панель",
    },
}


def detect_global_menu_action(value: str | None) -> GlobalMenuAction | None:
    normalized = normalize_button_text(value)
    plain = _without_leading_icon(normalized)
    candidates = {normalized, plain}
    for action, aliases in _GLOBAL_MENU_ALIASES.items():
        if candidates & aliases:
            return action
    return None


class GlobalMenuFilter(BaseFilter):
    """Aiogram filter that matches only global Reply Keyboard menu labels."""

    async def __call__(self, message: Message) -> dict[str, GlobalMenuAction] | bool:
        action = detect_global_menu_action(message.text)
        if not action:
            return False
        return {"global_menu_action": action}
