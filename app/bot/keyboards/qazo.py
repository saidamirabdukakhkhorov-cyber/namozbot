from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.core.constants import PRAYER_NAMES
from app.services.i18n import prayer_label, t


def qazo_overview_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Qazo ado qilish", callback_data="qazo_complete:start")],
        [InlineKeyboardButton(text="➕ Qazo qo'shish", callback_data="qazo_add:start")],
        [InlineKeyboardButton(text="🧮 Kalkulyator qazolari", callback_data="qazo:calculator_section")],
        [InlineKeyboardButton(text="📅 Davrni o'zgartirish", callback_data="qazo:period")],
        [InlineKeyboardButton(text="📋 Barcha qazolar", callback_data="qazo:all")],
    ])


def qazo_add_date_keyboard(language: str, prayer_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "period.today"), callback_data=f"qazo_add_date:{prayer_name}:today")],
        [InlineKeyboardButton(text=t(language, "period.yesterday"), callback_data=f"qazo_add_date:{prayer_name}:yesterday")],
        [InlineKeyboardButton(text=t(language, "period.custom"), callback_data=f"qazo_add_date:{prayer_name}:custom")],
        [InlineKeyboardButton(text=t(language, "common.back"), callback_data="qazo_add:start")],
    ])


def qazo_complete_source_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Joriy qazolardan", callback_data="qazo_complete_source:current")],
        [InlineKeyboardButton(text="Kalkulyator qazolaridan", callback_data="qazo_complete_source:calculator")],
        [InlineKeyboardButton(text="Barcha qazolardan", callback_data="qazo_complete_source:all")],
        [InlineKeyboardButton(text=t(language, "common.back"), callback_data="qazo:overview")],
    ])


def qazo_complete_prayers_keyboard(language: str, counts: dict[str, int], source_key: str) -> InlineKeyboardMarkup:
    rows = []
    for p in PRAYER_NAMES:
        count = counts.get(p, 0)
        if count > 0:
            rows.append([InlineKeyboardButton(text=f"{prayer_label(language, p)} — {count} ta", callback_data=f"qazo_complete_prayer:{source_key}:{p}")])
    rows.append([InlineKeyboardButton(text=t(language, "common.back"), callback_data="qazo_complete:start")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def qazo_complete_count_keyboard(language: str, source_key: str, prayer_name: str, max_count: int) -> InlineKeyboardMarkup:
    options = [1, 2, 3, 5, 10]
    rows = [[InlineKeyboardButton(text=f"{n} ta", callback_data=f"qazo_complete_count:{source_key}:{prayer_name}:{n}")] for n in options if n <= max_count]
    rows.append([InlineKeyboardButton(text="Boshqa son", callback_data=f"qazo_complete_custom:{source_key}:{prayer_name}")])
    rows.append([InlineKeyboardButton(text=t(language, "common.back"), callback_data=f"qazo_complete_source:{source_key}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def undo_keyboard(action_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Bekor qilish", callback_data=f"undo_completion:{action_id}")]])
