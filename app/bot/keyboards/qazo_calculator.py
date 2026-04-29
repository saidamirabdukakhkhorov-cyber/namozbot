from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from app.core.constants import PRAYER_NAMES
from app.services.i18n import prayer_label, t


def calculator_start_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "qazo.calculator.type.date_range"), callback_data="calc:type:date")],
        [InlineKeyboardButton(text=t(language, "qazo.calculator.type.month"), callback_data="calc:type:month")],
        [InlineKeyboardButton(text=t(language, "qazo.calculator.type.year"), callback_data="calc:type:year")],
        [InlineKeyboardButton(text=t(language, "common.cancel"), callback_data="calc:cancel")],
    ])


def calculator_input_keyboard(language: str, *, back_callback: str = "calc:start") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "common.back"), callback_data=back_callback)],
        [InlineKeyboardButton(text=t(language, "common.cancel"), callback_data="calc:cancel")],
    ])


def calculator_prayers_keyboard(language: str, selected: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for p in PRAYER_NAMES:
        mark = "✅ " if p in selected else ""
        rows.append([InlineKeyboardButton(text=f"{mark}{prayer_label(language, p)}", callback_data=f"calc_toggle:{p}")])
    if len(selected) == len(PRAYER_NAMES):
        rows.append([InlineKeyboardButton(text=t(language, "qazo.calculator.action.clear_all"), callback_data="calc:clear_all")])
    else:
        rows.append([InlineKeyboardButton(text=t(language, "qazo.calculator.action.select_all"), callback_data="calc:select_all")])
    rows.append([InlineKeyboardButton(text=t(language, "common.continue"), callback_data="calc:preview")])
    rows.append([InlineKeyboardButton(text=t(language, "common.back"), callback_data="calc:back_to_end")])
    rows.append([InlineKeyboardButton(text=t(language, "common.cancel"), callback_data="calc:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def calculator_result_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "qazo.calculator.action.save"), callback_data="calc:apply_confirm")],
        [InlineKeyboardButton(text=t(language, "qazo.calculator.action.calculate_only"), callback_data="calc:save_only")],
        [InlineKeyboardButton(text=t(language, "common.back"), callback_data="calc:back_to_prayers")],
        [InlineKeyboardButton(text=t(language, "common.cancel"), callback_data="calc:cancel")],
    ])


def calculator_apply_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "qazo.calculator.confirm.yes"), callback_data="calc:apply")],
        [InlineKeyboardButton(text=t(language, "common.cancel"), callback_data="calc:cancel")],
    ])


def calculator_success_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "menu.qazo"), callback_data="qazo:overview")],
        [InlineKeyboardButton(text=t(language, "qazo.action.complete"), callback_data="qazo_complete:start")],
        [InlineKeyboardButton(text=t(language, "common.home"), callback_data="dashboard")],
    ])
