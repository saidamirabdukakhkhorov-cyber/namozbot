from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.core.constants import PRAYER_NAMES
from app.services.i18n import prayer_label, t


def calculator_start_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Sanadan sanagacha", callback_data="calc:range")],
        [InlineKeyboardButton(text="Oy bo'yicha", callback_data="calc:month")],
        [InlineKeyboardButton(text="Yil bo'yicha", callback_data="calc:year")],
        [InlineKeyboardButton(text=t(language, "common.back"), callback_data="dashboard")],
    ])


def calculator_prayers_keyboard(language: str, selected: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for p in PRAYER_NAMES:
        mark = "✅ " if p in selected else ""
        rows.append([InlineKeyboardButton(text=f"{mark}{prayer_label(language, p)}", callback_data=f"calc_toggle:{p}")])
    if len(selected) == len(PRAYER_NAMES):
        rows.append([InlineKeyboardButton(text="Barchasini olib tashlash", callback_data="calc:clear_all")])
    else:
        rows.append([InlineKeyboardButton(text="Barchasini tanlash", callback_data="calc:select_all")])
    rows.append([InlineKeyboardButton(text="Tasdiqlash", callback_data="calc:preview")])
    rows.append([InlineKeyboardButton(text=t(language, "common.back"), callback_data="calc:start")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def calculator_result_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Qazo ro'yxatimga qo'shish", callback_data="calc:apply_confirm")],
        [InlineKeyboardButton(text="Faqat hisoblab qo'yish", callback_data="calc:save_only")],
        [InlineKeyboardButton(text="Boshqa davr tanlash", callback_data="calc:start")],
        [InlineKeyboardButton(text=t(language, "menu.home"), callback_data="dashboard")],
    ])


def calculator_apply_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ha, qo'shish", callback_data="calc:apply")],
        [InlineKeyboardButton(text=t(language, "common.cancel"), callback_data="calc:start")],
    ])
