from __future__ import annotations

from datetime import date

from aiogram import F, Router
from app.bot.filters.text import text_is_one_of
from aiogram.types import CallbackQuery, Message

from app.bot.handlers.dashboard import build_dashboard, dashboard_keyboard
from app.bot.keyboards.qazo_calculator import (
    calculator_apply_keyboard,
    calculator_input_keyboard,
    calculator_prayers_keyboard,
    calculator_result_keyboard,
    calculator_start_keyboard,
    calculator_success_keyboard,
)
from app.core.constants import PRAYER_NAMES
from app.db.models import User
from app.db.repositories.missed_prayers import MissedPrayersRepository
from app.db.repositories.qazo_calculations import QazoCalculationsRepository
from app.db.repositories.states import StatesRepository
from app.services.i18n import prayer_label, t
from app.services.qazo_calculator import QazoCalculatorService

router = Router(name="qazo_calculator")


def payload_dates(payload):
    return date.fromisoformat(payload["start_date"]), date.fromisoformat(payload["end_date"])


async def send_or_edit(event: Message | CallbackQuery, text: str, reply_markup=None):
    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=reply_markup)
        except Exception:
            await event.message.answer(text, reply_markup=reply_markup)
        await event.answer()
    else:
        await event.answer(text, reply_markup=reply_markup)


def calc_start_text(language: str) -> str:
    return "\n".join([
        t(language, "qazo.calculator.title"),
        "",
        t(language, "qazo.calculator.step.period_type"),
        "",
        t(language, "qazo.calculator.period_question"),
    ])


def calc_input_text(language: str, step_key: str, example: str) -> str:
    return "\n".join([
        t(language, "qazo.calculator.title"),
        "",
        t(language, step_key),
        "",
        t(language, "qazo.calculator.input_hint"),
        "",
        t(language, "common.example", example=example),
    ])


def calc_prayers_text(language: str, payload: dict) -> str:
    selected = payload.get("selected_prayers", [])
    selected_lines = [f"✅ {prayer_label(language, p)}" for p in PRAYER_NAMES if p in selected]
    selected_text = "\n".join(selected_lines) if selected_lines else t(language, "qazo.calculator.none_selected")
    return "\n".join([
        t(language, "qazo.calculator.title"),
        "",
        t(language, "qazo.calculator.step.prayers"),
        "",
        t(language, "qazo.calculator.period_preview", start=payload.get("start_date"), end=payload.get("end_date")),
        "",
        t(language, "qazo.calculator.prayers_question"),
        "",
        t(language, "qazo.calculator.selected", selected=selected_text),
    ])


@router.message(text_is_one_of("🧮 Qazo kalkulyator", "🧮 Калькулятор каза", "🧮 Missed prayer calculator", "Qazo kalkulyator", "Калькулятор каза", "Missed prayer calculator"))
@router.callback_query(F.data == "calc:start")
async def calculator_start(event: Message | CallbackQuery, current_user: User, session):
    await StatesRepository(session).set(current_user.id, "calc_period_type", {})
    lang = current_user.language_code or "uz"
    await send_or_edit(event, calc_start_text(lang), calculator_start_keyboard(lang))


@router.callback_query(F.data.startswith("calc:type:"))
async def calculator_period_type(callback: CallbackQuery, current_user: User, session):
    lang = current_user.language_code or "uz"
    kind = callback.data.split(":", 2)[2]
    if kind == "date":
        await StatesRepository(session).set(current_user.id, "calc_waiting_start_date", {"period_type": "date"})
        text = calc_input_text(lang, "qazo.calculator.step.start_date", "2020-01-01")
    elif kind == "month":
        await StatesRepository(session).set(current_user.id, "calc_waiting_start_month", {"period_type": "month"})
        text = calc_input_text(lang, "qazo.calculator.step.start_month", "2020-01")
    else:
        await StatesRepository(session).set(current_user.id, "calc_waiting_start_year", {"period_type": "year"})
        text = calc_input_text(lang, "qazo.calculator.step.start_year", "2020")
    await send_or_edit(callback, text, calculator_input_keyboard(lang, back_callback="calc:start"))


@router.callback_query(F.data.startswith("calc_toggle:"))
async def calculator_toggle(callback: CallbackQuery, current_user: User, session):
    lang = current_user.language_code or "uz"
    state = await StatesRepository(session).get(current_user.id)
    payload = state.payload if state else {}
    selected = list(payload.get("selected_prayers", []))
    prayer = callback.data.split(":", 1)[1]
    if prayer in selected:
        selected.remove(prayer)
    else:
        selected.append(prayer)
    payload["selected_prayers"] = selected
    await StatesRepository(session).set(current_user.id, "calc_select_prayers", payload)
    text = calc_prayers_text(lang, payload)
    await callback.message.edit_text(text, reply_markup=calculator_prayers_keyboard(lang, selected))
    await callback.answer()


@router.callback_query(F.data.in_({"calc:select_all", "calc:clear_all"}))
async def calculator_all(callback: CallbackQuery, current_user: User, session):
    lang = current_user.language_code or "uz"
    state = await StatesRepository(session).get(current_user.id)
    payload = state.payload if state else {}
    selected = list(PRAYER_NAMES) if callback.data == "calc:select_all" else []
    payload["selected_prayers"] = selected
    await StatesRepository(session).set(current_user.id, "calc_select_prayers", payload)
    await callback.message.edit_text(calc_prayers_text(lang, payload), reply_markup=calculator_prayers_keyboard(lang, selected))
    await callback.answer()


@router.callback_query(F.data == "calc:back_to_end")
async def calculator_back_to_end(callback: CallbackQuery, current_user: User, session):
    lang = current_user.language_code or "uz"
    state = await StatesRepository(session).get(current_user.id)
    payload = state.payload if state else {}
    kind = payload.get("period_type", "date")
    if kind == "month":
        await StatesRepository(session).set(current_user.id, "calc_waiting_end_month", payload)
        text = calc_input_text(lang, "qazo.calculator.step.end_month", "2023-03")
    elif kind == "year":
        await StatesRepository(session).set(current_user.id, "calc_waiting_end_year", payload)
        text = calc_input_text(lang, "qazo.calculator.step.end_year", "2023")
    else:
        await StatesRepository(session).set(current_user.id, "calc_waiting_end_date", payload)
        text = calc_input_text(lang, "qazo.calculator.step.end_date", "2023-03-31")
    await send_or_edit(callback, text, calculator_input_keyboard(lang, back_callback="calc:start"))


@router.callback_query(F.data == "calc:back_to_prayers")
async def calculator_back_to_prayers(callback: CallbackQuery, current_user: User, session):
    lang = current_user.language_code or "uz"
    state = await StatesRepository(session).get(current_user.id)
    payload = state.payload if state else {}
    selected = payload.get("selected_prayers", [])
    await StatesRepository(session).set(current_user.id, "calc_select_prayers", payload)
    await send_or_edit(callback, calc_prayers_text(lang, payload), calculator_prayers_keyboard(lang, selected))


@router.callback_query(F.data == "calc:preview")
async def calculator_preview(callback: CallbackQuery, current_user: User, session):
    lang = current_user.language_code or "uz"
    state = await StatesRepository(session).get(current_user.id)
    payload = state.payload if state else {}
    selected = payload.get("selected_prayers", [])
    if not selected:
        await callback.answer(t(lang, "qazo.calculator.error.no_prayers"), show_alert=True)
        return
    try:
        start, end = payload_dates(payload)
        service = QazoCalculatorService(QazoCalculationsRepository(session), MissedPrayersRepository(session))
        preview = service.calculate(start, end, selected)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    breakdown_lines = "\n".join(f"{prayer_label(lang, p)}: {preview.breakdown[p]} ta" for p in preview.selected_prayers)
    text = t(
        lang,
        "qazo.calculator.preview.text",
        start=start.isoformat(),
        end=end.isoformat(),
        days=preview.days_count,
        breakdown=breakdown_lines,
        total=preview.total_count,
    )
    payload["preview"] = {"days_count": preview.days_count, "total_count": preview.total_count, "breakdown": preview.breakdown}
    await StatesRepository(session).set(current_user.id, "calc_preview", payload)
    await send_or_edit(callback, text, calculator_result_keyboard(lang))


@router.callback_query(F.data == "calc:save_only")
async def calculator_save_only(callback: CallbackQuery, current_user: User, session):
    lang = current_user.language_code or "uz"
    state = await StatesRepository(session).get(current_user.id)
    payload = state.payload if state else {}
    start, end = payload_dates(payload)
    selected = payload.get("selected_prayers", [])
    service = QazoCalculatorService(QazoCalculationsRepository(session), MissedPrayersRepository(session))
    preview = service.calculate(start, end, selected)
    await service.save_preview(current_user.id, preview)
    await StatesRepository(session).clear(current_user.id)
    await send_or_edit(callback, t(lang, "qazo.calculator.save_only_success"), calculator_success_keyboard(lang))


@router.callback_query(F.data == "calc:apply_confirm")
async def calculator_apply_confirm(callback: CallbackQuery, current_user: User, session):
    lang = current_user.language_code or "uz"
    state = await StatesRepository(session).get(current_user.id)
    payload = state.payload if state else {}
    total = payload.get("preview", {}).get("total_count", 0)
    text = t(lang, "qazo.calculator.confirm.text", count=total)
    await send_or_edit(callback, text, calculator_apply_keyboard(lang))


@router.callback_query(F.data == "calc:apply")
async def calculator_apply(callback: CallbackQuery, current_user: User, session):
    lang = current_user.language_code or "uz"
    state = await StatesRepository(session).get(current_user.id)
    payload = state.payload if state else {}
    start, end = payload_dates(payload)
    selected = payload.get("selected_prayers", [])
    service = QazoCalculatorService(QazoCalculationsRepository(session), MissedPrayersRepository(session))
    preview = service.calculate(start, end, selected)
    calculation = await service.save_preview(current_user.id, preview)
    created, skipped = await service.apply(user_id=current_user.id, calculation_id=calculation.id, start_date=start, end_date=end, selected_prayers=selected)
    await StatesRepository(session).clear(current_user.id)
    created_lines = "\n".join(f"{prayer_label(lang, p)}: {created[p]} ta" for p in selected)
    skipped_lines = "\n".join(f"{prayer_label(lang, p)}: {skipped[p]} ta" for p in selected if skipped[p] > 0) or "—"
    text = t(
        lang,
        "qazo.calculator.success.text",
        calculated="\n".join(f"{prayer_label(lang, p)}: {preview.breakdown[p]} ta" for p in selected),
        created=created_lines,
        skipped=skipped_lines,
        created_total=sum(created.values()),
        skipped_total=sum(skipped.values()),
    )
    await send_or_edit(callback, text, calculator_success_keyboard(lang))


@router.callback_query(F.data == "calc:cancel")
async def calculator_cancel(callback: CallbackQuery, current_user: User, session):
    await StatesRepository(session).clear(current_user.id)
    lang = current_user.language_code or "uz"
    await send_or_edit(callback, await build_dashboard(current_user, session), dashboard_keyboard(lang))
