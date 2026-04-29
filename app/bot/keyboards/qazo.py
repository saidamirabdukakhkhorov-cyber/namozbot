from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from app.core.constants import PRAYER_NAMES
from app.services.i18n import prayer_label, t


def qazo_overview_keyboard(language: str, *, empty: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if not empty:
        rows.append([InlineKeyboardButton(text=t(language, "qazo.action.complete"), callback_data="qazo_complete:start")])
        rows.append([InlineKeyboardButton(text=t(language, "qazo.action.add"), callback_data="qazo_add:start")])
        rows.append([InlineKeyboardButton(text=t(language, "qazo.action.calculator_items"), callback_data="qazo:calculator_section")])
        rows.append([InlineKeyboardButton(text=t(language, "qazo.action.period"), callback_data="qazo:period")])
        rows.append([InlineKeyboardButton(text=t(language, "qazo.action.all"), callback_data="qazo:all")])
    else:
        rows.append([InlineKeyboardButton(text=t(language, "qazo.action.calculator_items"), callback_data="qazo:calculator_section")])
        rows.append([InlineKeyboardButton(text=t(language, "qazo.action.add"), callback_data="qazo_add:start")])
        rows.append([InlineKeyboardButton(text=t(language, "qazo.action.period"), callback_data="qazo:period")])
    rows.append([InlineKeyboardButton(text=t(language, "common.home"), callback_data="dashboard")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def qazo_period_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "period.today"), callback_data="qazo_period:today"), InlineKeyboardButton(text=t(language, "period.yesterday"), callback_data="qazo_period:yesterday")],
        [InlineKeyboardButton(text=t(language, "period.this_week"), callback_data="qazo_period:this_week"), InlineKeyboardButton(text=t(language, "period.last_week"), callback_data="qazo_period:last_week")],
        [InlineKeyboardButton(text=t(language, "period.this_month"), callback_data="qazo_period:this_month"), InlineKeyboardButton(text=t(language, "period.last_month"), callback_data="qazo_period:last_month")],
        [InlineKeyboardButton(text=t(language, "period.this_year"), callback_data="qazo_period:this_year"), InlineKeyboardButton(text=t(language, "period.last_year"), callback_data="qazo_period:last_year")],
        [InlineKeyboardButton(text=t(language, "period.custom"), callback_data="qazo_period:custom")],
        [InlineKeyboardButton(text=t(language, "common.back"), callback_data="qazo:overview")],
    ])


def qazo_custom_period_keyboard(language: str, *, back_callback: str = "qazo:period") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "period.write_date"), callback_data="noop")],
        [InlineKeyboardButton(text=t(language, "common.back"), callback_data=back_callback)],
        [InlineKeyboardButton(text=t(language, "common.cancel"), callback_data="cancel")],
    ])


def qazo_add_date_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "period.today"), callback_data="qazo_add_date:today")],
        [InlineKeyboardButton(text=t(language, "period.yesterday"), callback_data="qazo_add_date:yesterday")],
        [InlineKeyboardButton(text=t(language, "period.write_date"), callback_data="qazo_add_date:custom")],
        [InlineKeyboardButton(text=t(language, "common.back"), callback_data="qazo:overview")],
        [InlineKeyboardButton(text=t(language, "common.cancel"), callback_data="cancel")],
    ])


def qazo_add_confirm_keyboard(language: str, prayer_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "qazo.add.confirm_yes"), callback_data=f"qazo_add_confirm:{prayer_name}")],
        [InlineKeyboardButton(text=t(language, "common.back"), callback_data="qazo_add:choose_prayer")],
        [InlineKeyboardButton(text=t(language, "common.cancel"), callback_data="cancel")],
    ])


def qazo_calculator_section_keyboard(language: str, *, empty: bool = False) -> InlineKeyboardMarkup:
    if empty:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(language, "menu.calculator"), callback_data="calc:start")],
            [InlineKeyboardButton(text=t(language, "common.back"), callback_data="qazo:overview")],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "qazo.action.complete"), callback_data="qazo_complete_source:calculator")],
        [InlineKeyboardButton(text=t(language, "qazo.calculator.history"), callback_data="qazo:calc_history")],
        [InlineKeyboardButton(text=t(language, "qazo.action.all"), callback_data="qazo:all")],
        [InlineKeyboardButton(text=t(language, "common.back"), callback_data="qazo:overview")],
    ])


def qazo_complete_source_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "qazo.completion.source.current"), callback_data="qazo_complete_source:current")],
        [InlineKeyboardButton(text=t(language, "qazo.completion.source.calculator"), callback_data="qazo_complete_source:calculator")],
        [InlineKeyboardButton(text=t(language, "qazo.completion.source.all"), callback_data="qazo_complete_source:all")],
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
    rows.append([InlineKeyboardButton(text=t(language, "qazo.completion.other_count"), callback_data=f"qazo_complete_custom:{source_key}:{prayer_name}")])
    rows.append([InlineKeyboardButton(text=t(language, "common.back"), callback_data=f"qazo_complete_source:{source_key}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def qazo_complete_success_keyboard(language: str, action_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "qazo.completion.undo"), callback_data=f"undo_completion:{action_id}")],
        [InlineKeyboardButton(text=t(language, "qazo.completion.again"), callback_data="qazo_complete:start")],
        [InlineKeyboardButton(text=t(language, "menu.qazo"), callback_data="qazo:overview")],
        [InlineKeyboardButton(text=t(language, "common.home"), callback_data="dashboard")],
    ])


def undo_keyboard(action_id: int, language: str = "uz") -> InlineKeyboardMarkup:
    return qazo_complete_success_keyboard(language, action_id)
