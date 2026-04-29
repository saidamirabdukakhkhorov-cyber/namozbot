from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from app.services.i18n import t
from app.services.prayer_times import ISLOMAPI_REGIONS

CITIES = list(ISLOMAPI_REGIONS)


def city_keyboard(language: str = "uz", *, back_callback: str | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(CITIES), 2):
        rows.append([InlineKeyboardButton(text=c, callback_data=f"city:{c}") for c in CITIES[i:i + 2]])
    rows.append([InlineKeyboardButton(text=t(language, "city.other"), callback_data="city:other")])
    if back_callback:
        rows.append([InlineKeyboardButton(text=t(language, "common.back"), callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)
