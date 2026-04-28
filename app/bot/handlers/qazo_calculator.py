from datetime import date
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from app.bot.keyboards.qazo_calculator import calculator_apply_keyboard, calculator_prayers_keyboard, calculator_result_keyboard, calculator_start_keyboard
from app.core.constants import PRAYER_NAMES
from app.db.models import User
from app.db.repositories.missed_prayers import MissedPrayersRepository
from app.db.repositories.qazo_calculations import QazoCalculationsRepository
from app.db.repositories.states import StatesRepository
from app.services.i18n import prayer_label
from app.services.qazo_calculator import QazoCalculatorService

router = Router(name="qazo_calculator")

def payload_dates(payload):
    return date.fromisoformat(payload["start_date"]), date.fromisoformat(payload["end_date"])

@router.message(F.text.in_({"🧮 Qazo kalkulyator", "🧮 Калькулятор каза", "🧮 Missed prayer calculator"}))
@router.callback_query(F.data == "calc:start")
async def calculator_start(event, current_user: User):
    target = event.message if isinstance(event, CallbackQuery) else event
    await target.answer("🧮 Qazo kalkulyator\n\nDavrni qanday tanlaysiz?", reply_markup=calculator_start_keyboard(current_user.language_code))
    if isinstance(event, CallbackQuery):
        await event.answer()

@router.callback_query(F.data == "calc:range")
async def calculator_range(callback: CallbackQuery, current_user: User, session):
    await StatesRepository(session).set(current_user.id, "calc_waiting_start_date", {})
    await callback.message.answer("Boshlanish sanasini YYYY-MM-DD formatida yozing. Masalan: 2020-01-01")
    await callback.answer()

@router.callback_query(F.data == "calc:year")
async def calculator_year(callback: CallbackQuery, current_user: User, session):
    await StatesRepository(session).set(current_user.id, "calc_waiting_start_year", {})
    await callback.message.answer("Boshlanish yilini yozing. Masalan: 2020")
    await callback.answer()

@router.callback_query(F.data == "calc:month")
async def calculator_month(callback: CallbackQuery, current_user: User, session):
    await StatesRepository(session).set(current_user.id, "calc_waiting_start_month", {})
    await callback.message.answer("Boshlanish oyini YYYY-MM formatida yozing. Masalan: 2020-01")
    await callback.answer()

@router.callback_query(F.data.startswith("calc_toggle:"))
async def calculator_toggle(callback: CallbackQuery, current_user: User, session):
    state = await StatesRepository(session).get(current_user.id)
    payload = state.payload if state else {}
    selected = payload.get("selected_prayers", [])
    prayer = callback.data.split(":", 1)[1]
    if prayer in selected:
        selected.remove(prayer)
    else:
        selected.append(prayer)
    payload["selected_prayers"] = selected
    await StatesRepository(session).set(current_user.id, "calc_select_prayers", payload)
    await callback.message.edit_reply_markup(reply_markup=calculator_prayers_keyboard(current_user.language_code, selected))
    await callback.answer()

@router.callback_query(F.data.in_({"calc:select_all", "calc:clear_all"}))
async def calculator_all(callback: CallbackQuery, current_user: User, session):
    state = await StatesRepository(session).get(current_user.id)
    payload = state.payload if state else {}
    selected = list(PRAYER_NAMES) if callback.data == "calc:select_all" else []
    payload["selected_prayers"] = selected
    await StatesRepository(session).set(current_user.id, "calc_select_prayers", payload)
    await callback.message.edit_reply_markup(reply_markup=calculator_prayers_keyboard(current_user.language_code, selected))
    await callback.answer()

@router.callback_query(F.data == "calc:preview")
async def calculator_preview(callback: CallbackQuery, current_user: User, session):
    state = await StatesRepository(session).get(current_user.id)
    payload = state.payload if state else {}
    selected = payload.get("selected_prayers", [])
    try:
        start, end = payload_dates(payload)
        service = QazoCalculatorService(QazoCalculationsRepository(session), MissedPrayersRepository(session))
        preview = service.calculate(start, end, selected)
    except Exception as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    breakdown_lines = "\n".join(f"{prayer_label(current_user.language_code, p)}: {preview.breakdown[p]} ta" for p in selected)
    text = f"🧮 Qazo kalkulyator natijasi\n\nDavr:\n{start} — {end}\n\nKunlar soni:\n{preview.days_count} kun\n\nHisoblangan qazolar:\n{breakdown_lines}\n\nJami:\n{preview.total_count} ta qazo namoz"
    payload["preview"] = {"days_count": preview.days_count, "total_count": preview.total_count, "breakdown": preview.breakdown}
    await StatesRepository(session).set(current_user.id, "calc_preview", payload)
    await callback.message.answer(text, reply_markup=calculator_result_keyboard(current_user.language_code))
    await callback.answer()

@router.callback_query(F.data == "calc:save_only")
async def calculator_save_only(callback: CallbackQuery, current_user: User, session):
    state = await StatesRepository(session).get(current_user.id); payload = state.payload if state else {}
    start, end = payload_dates(payload); selected = payload.get("selected_prayers", [])
    service = QazoCalculatorService(QazoCalculationsRepository(session), MissedPrayersRepository(session))
    preview = service.calculate(start, end, selected)
    await service.save_preview(current_user.id, preview)
    await StatesRepository(session).clear(current_user.id)
    await callback.message.answer("Hisob-kitob tarixga saqlandi. Missed prayers ro'yxatiga qo'shilmadi.")
    await callback.answer()

@router.callback_query(F.data == "calc:apply_confirm")
async def calculator_apply_confirm(callback: CallbackQuery, current_user: User, session):
    state = await StatesRepository(session).get(current_user.id); payload = state.payload if state else {}
    total = payload.get("preview", {}).get("total_count", 0)
    warning = "Siz katta davr tanladingiz.\n\n" if total > 10000 else ""
    await callback.message.answer(f"{warning}{total} ta qazo namoz ro'yxatingizga qo'shiladi.\n\nDavom etamizmi?", reply_markup=calculator_apply_keyboard(current_user.language_code))
    await callback.answer()

@router.callback_query(F.data == "calc:apply")
async def calculator_apply(callback: CallbackQuery, current_user: User, session):
    state = await StatesRepository(session).get(current_user.id); payload = state.payload if state else {}
    start, end = payload_dates(payload); selected = payload.get("selected_prayers", [])
    service = QazoCalculatorService(QazoCalculationsRepository(session), MissedPrayersRepository(session))
    preview = service.calculate(start, end, selected)
    calculation = await service.save_preview(current_user.id, preview)
    created, skipped = await service.apply(user_id=current_user.id, calculation_id=calculation.id, start_date=start, end_date=end, selected_prayers=selected)
    await StatesRepository(session).clear(current_user.id)
    lines = ["Qazo ro'yxatiga qo'shildi.", "", "Yangi qo'shildi:"]
    for p in selected:
        lines.append(f"{prayer_label(current_user.language_code, p)}: {created[p]} ta")
    lines += ["", "Oldin mavjud bo'lgani uchun o'tkazib yuborildi:"]
    for p in selected:
        lines.append(f"{prayer_label(current_user.language_code, p)}: {skipped[p]} ta")
    await callback.message.answer("\n".join(lines))
    await callback.answer()

