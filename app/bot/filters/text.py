from __future__ import annotations

from aiogram import F

_VARIATION_SELECTORS = {"️", "︎"}


def normalize_button_text(value: str | None) -> str:
    """Normalize Telegram button text for reliable Reply Keyboard matching.

    Some Telegram clients send emoji buttons with/without variation selectors
    (for example, "⚙️ Sozlamalar" vs "⚙ Sozlamalar"). Exact string
    matching makes global navigation feel broken, so handlers should compare
    normalized text.
    """
    text = value or ""
    for marker in _VARIATION_SELECTORS:
        text = text.replace(marker, "")
    return " ".join(text.strip().split()).casefold()


def text_is_one_of(*values: str):
    expected = {normalize_button_text(value) for value in values}
    return F.text.func(lambda text: normalize_button_text(text) in expected)
