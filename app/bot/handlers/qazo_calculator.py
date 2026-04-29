"""
Qazo kalkulyator — soddalashtirilgan UX.

Eski UX muammolari:
  1. "Davr turi" qadami (sana/oy/yil tanlov) — ortiqcha murakkablik,
     foydalanuvchi nima tanlash kerakligini tushunmaydi.
  2. 5 ta qadam (1/5, 2/5...) — juda uzun, charchatuvchi.
  3. "Faqat hisoblab qo'yish" vs "Ro'yxatga qo'shish" farqi tushunarsiz.
  4. Namoz tanlash — tugmalar ko'p, barchasini bosib chiqish kerak.

Yangi UX:
  1. Davr tanlash: tez tugmalar (Bu yil / O'tgan yil / O'zim kiritaman).
  2. Agar "O'zim kiritaman" → faqat YILLARNI kiriting (sodda, 4 ta raqam).
  3. Namoz tanlash: bir ekranda, "Barchasi" tugmasi bilan.
  4. Natija: aniq ko'rsatiladi, faqat 1 ta tugma — "Ro'yxatga qo'shish".
  5. Jami 3 qadam: Davr → Namozlar → Tasdiqlash.
"""
from __future__ import annotations

from datetime import date

from aiogram import F, Router
from aiogram.filters import BaseFilter
from app.bot.filters.text import text_is_one_of
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.handlers.dashboard import build_dashboard, dashboard_keyboard
from app.core.constants import QAZO_PRAYER_NAMES
from app.db.models import User
from app.db.repositories.missed_prayers import MissedPrayersRepository
from app.db.repositories.qazo_calculations import QazoCalculationsRepository
from app.db.repositories.states import StatesRepository
from app.services.i18n import prayer_label, t
from app.services.qazo_calculator import QazoCalculatorService
from app.services.timezone import tashkent_today

router = Router(name="qazo_calculator")

# ── helpers ──────────────────────────────────────────────────────────────────

def _svc(session) -> QazoCalculatorService:
    return QazoCalculatorService(
        QazoCalculationsRepository(session),
        MissedPrayersRepository(session),
    )


async def _send(event: Message | CallbackQuery, text: str, kb=None):
    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=kb)
        except Exception:
            await event.message.answer(text, reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb)


def _lang(user: User) -> str:
    return user.language_code or "uz"


# ── keyboards ─────────────────────────────────────────────────────────────────

def _period_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Qadam 1: Davr tanlash — tez tugmalar + o'zim kiritaman."""
    today = tashkent_today()
    this_year = today.year
    last_year = this_year - 1
    two_years_ago = this_year - 2

    rows = [
        [InlineKeyboardButton(
            text=f"📅 {this_year} (bu yil)",
            callback_data=f"calc2:year:{this_year}:{this_year}",
        )],
        [InlineKeyboardButton(
            text=f"📅 {last_year}",
            callback_data=f"calc2:year:{last_year}:{last_year}",
        )],
        [InlineKeyboardButton(
            text=f"📅 {two_years_ago}",
            callback_data=f"calc2:year:{two_years_ago}:{two_years_ago}",
        )],
        [InlineKeyboardButton(
            text=f"📅 {last_year} — {this_year} (2 yil)",
            callback_data=f"calc2:year:{last_year}:{this_year}",
        )],
        [InlineKeyboardButton(
            text="✏️ Boshqa davr (yil kiriting)",
            callback_data="calc2:custom_year",
        )],
        [InlineKeyboardButton(text=t(lang, "common.cancel"), callback_data="calc2:cancel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _prayers_keyboard(lang: str, selected: list[str]) -> InlineKeyboardMarkup:
    """Qadam 2: Namoz tanlash."""
    rows = []
    for p in QAZO_PRAYER_NAMES:
        mark = "✅ " if p in selected else "☐ "
        rows.append([InlineKeyboardButton(
            text=f"{mark}{prayer_label(lang, p)}",
            callback_data=f"calc2:toggle:{p}",
        )])

    if len(selected) == len(QAZO_PRAYER_NAMES):
        rows.append([InlineKeyboardButton(
            text="☐ Barchasini olib tashlash",
            callback_data="calc2:clear",
        )])
    else:
        rows.append([InlineKeyboardButton(
            text="✅ Barchasini tanlash",
            callback_data="calc2:all",
        )])

    rows.append([InlineKeyboardButton(
        text=f"➡️ Hisoblash ({len(selected)} ta namoz)",
        callback_data="calc2:preview",
    )])
    rows.append([InlineKeyboardButton(text=t(lang, "common.back"), callback_data="calc2:start")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Ha, ro'yxatga qo'shish", callback_data="calc2:apply")],
        [InlineKeyboardButton(text=t(lang, "common.back"), callback_data="calc2:back_to_prayers")],
        [InlineKeyboardButton(text=t(lang, "common.cancel"), callback_data="calc2:cancel")],
    ])


def _success_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📌 Qazo ro'yxatim", callback_data="qazo:overview")],
        [InlineKeyboardButton(text="✅ Qazolarni bajarish", callback_data="qazo_complete:start")],
        [InlineKeyboardButton(text=t(lang, "common.home"), callback_data="dashboard")],
    ])


# ── screens ───────────────────────────────────────────────────────────────────

def _step1_text(lang: str) -> str:
    return (
        "🧮 Qazo kalkulyator\n\n"
        "📍 1-qadam: Qaysi yillardan qazo qoldirgan bo'lsangiz, shu davrni tanlang.\n\n"
        "Masalan, 2020-yildan 2024-yilgacha namoz o'qimagan bo'lsangiz — "
        "har bir yilni alohida yoki bir vaqtda tanlashingiz mumkin."
    )


def _step2_text(lang: str, start_year: int, end_year: int) -> str:
    today = tashkent_today()
    end_date = date(end_year, 12, 31) if end_year < today.year else today
    start_date = date(start_year, 1, 1)
    days = (end_date - start_date).days + 1
    return (
        f"🧮 Qazo kalkulyator\n\n"
        f"📅 Tanlangan davr: {start_year} — {end_year}\n"
        f"📆 Kunlar soni: {days} kun\n\n"
        f"📍 2-qadam: Qaysi namozlarni qazo qilgansiz?\n\n"
        f"Faqat o'sha vaqtda o'qimagan namozlaringizni tanlang."
    )


def _preview_text(lang: str, start_date: date, end_date: date, selected: list[str], breakdown: dict, total: int) -> str:
    lines = [
        "🧮 Qazo kalkulyator — Natija",
        "",
        f"📅 Davr: {start_date.year} — {end_date.year}",
        f"📆 {(end_date - start_date).days + 1} kun",
        "",
        "📊 Hisoblangan qazo namozlar:",
    ]
    for p in selected:
        lines.append(f"  • {prayer_label(lang, p)}: {breakdown.get(p, 0)} ta")
    lines += [
        "",
        f"🔢 Jami: {total} ta qazo namoz",
        "",
        "⚠️ Ro'yxatga qo'shsangiz, bular qazo ro'yxatingizda paydo bo'ladi.",
        "Keyin birma-bir yoki guruhlab bajarib borasiz.",
    ]
    return "\n".join(lines)


# ── handlers ──────────────────────────────────────────────────────────────────

@router.message(text_is_one_of(
    "🧮 Qazo kalkulyator", "🧮 Калькулятор каза", "🧮 Missed prayer calculator",
    "Qazo kalkulyator", "Калькулятор каза", "Missed prayer calculator",
))
@router.callback_query(F.data.in_({"calc2:start", "calc:start"}))
async def calculator_start(event: Message | CallbackQuery, current_user: User, session):
    await StatesRepository(session).set(current_user.id, "calc2_step1", {})
    lang = _lang(current_user)
    await _send(event, _step1_text(lang), _period_keyboard(lang))


@router.callback_query(F.data.startswith("calc2:year:"))
async def calculator_year_selected(callback: CallbackQuery, current_user: User, session):
    lang = _lang(current_user)
    _, _, start_str, end_str = callback.data.split(":")
    start_year, end_year = int(start_str), int(end_str)
    payload = {"start_year": start_year, "end_year": end_year, "selected": []}
    await StatesRepository(session).set(current_user.id, "calc2_step2", payload)
    await _send(callback, _step2_text(lang, start_year, end_year), _prayers_keyboard(lang, []))


@router.callback_query(F.data == "calc2:custom_year")
async def calculator_custom_year(callback: CallbackQuery, current_user: User, session):
    lang = _lang(current_user)
    await StatesRepository(session).set(current_user.id, "calc2_waiting_years", {})
    text = (
        "✏️ Boshlanish va tugash yilini kiriting.\n\n"
        "Misol: 2018 2023\n"
        "(ikki yilni bo'sh joy bilan yozing)\n\n"
        "Faqat bir yil bo'lsa, bir xil yilni ikki marta yozing:\n"
        "Misol: 2020 2020"
    )
    await _send(callback, text, InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "common.back"), callback_data="calc2:start")],
    ]))


@router.callback_query(F.data.startswith("calc2:toggle:"))
async def calculator_toggle(callback: CallbackQuery, current_user: User, session):
    lang = _lang(current_user)
    prayer = callback.data.split(":", 2)[2]
    state = await StatesRepository(session).get(current_user.id)
    payload = state.payload if state else {}
    selected = list(payload.get("selected", []))
    if prayer in selected:
        selected.remove(prayer)
    else:
        selected.append(prayer)
    payload["selected"] = selected
    await StatesRepository(session).set(current_user.id, "calc2_step2", payload)
    start_year = payload.get("start_year", tashkent_today().year)
    end_year = payload.get("end_year", tashkent_today().year)
    await callback.message.edit_text(_step2_text(lang, start_year, end_year), reply_markup=_prayers_keyboard(lang, selected))
    await callback.answer()


@router.callback_query(F.data.in_({"calc2:all", "calc2:clear"}))
async def calculator_all_clear(callback: CallbackQuery, current_user: User, session):
    lang = _lang(current_user)
    state = await StatesRepository(session).get(current_user.id)
    payload = state.payload if state else {}
    payload["selected"] = list(QAZO_PRAYER_NAMES) if callback.data == "calc2:all" else []
    await StatesRepository(session).set(current_user.id, "calc2_step2", payload)
    start_year = payload.get("start_year", tashkent_today().year)
    end_year = payload.get("end_year", tashkent_today().year)
    await callback.message.edit_text(_step2_text(lang, start_year, end_year), reply_markup=_prayers_keyboard(lang, payload["selected"]))
    await callback.answer()


@router.callback_query(F.data == "calc2:preview")
async def calculator_preview(callback: CallbackQuery, current_user: User, session):
    lang = _lang(current_user)
    state = await StatesRepository(session).get(current_user.id)
    payload = state.payload if state else {}
    selected = payload.get("selected", [])
    if not selected:
        await callback.answer("Kamida bitta namozni tanlang", show_alert=True)
        return

    today = tashkent_today()
    start_year = payload.get("start_year", today.year)
    end_year = payload.get("end_year", today.year)
    start_date = date(start_year, 1, 1)
    end_date = date(end_year, 12, 31) if end_year < today.year else today

    try:
        svc = _svc(session)
        preview = svc.calculate(start_date, end_date, selected)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    payload["start_date"] = start_date.isoformat()
    payload["end_date"] = end_date.isoformat()
    payload["total"] = preview.total_count
    payload["breakdown"] = preview.breakdown
    await StatesRepository(session).set(current_user.id, "calc2_step3", payload)
    text = _preview_text(lang, start_date, end_date, preview.selected_prayers, preview.breakdown, preview.total_count)
    await _send(callback, text, _confirm_keyboard(lang))


@router.callback_query(F.data == "calc2:back_to_prayers")
async def calculator_back_to_prayers(callback: CallbackQuery, current_user: User, session):
    lang = _lang(current_user)
    state = await StatesRepository(session).get(current_user.id)
    payload = state.payload if state else {}
    selected = payload.get("selected", [])
    start_year = payload.get("start_year", tashkent_today().year)
    end_year = payload.get("end_year", tashkent_today().year)
    await StatesRepository(session).set(current_user.id, "calc2_step2", payload)
    await _send(callback, _step2_text(lang, start_year, end_year), _prayers_keyboard(lang, selected))


@router.callback_query(F.data == "calc2:apply")
async def calculator_apply(callback: CallbackQuery, current_user: User, session):
    lang = _lang(current_user)
    state = await StatesRepository(session).get(current_user.id)
    payload = state.payload if state else {}

    start_date = date.fromisoformat(payload["start_date"])
    end_date = date.fromisoformat(payload["end_date"])
    selected = payload.get("selected", [])

    svc = _svc(session)
    try:
        preview = svc.calculate(start_date, end_date, selected)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    calculation = await svc.save_preview(current_user.id, preview)
    created, skipped = await svc.apply(
        user_id=current_user.id,
        calculation_id=calculation.id,
        start_date=start_date,
        end_date=end_date,
        selected_prayers=selected,
    )
    await StatesRepository(session).clear(current_user.id)

    created_total = sum(created.values())
    skipped_total = sum(skipped.values())
    lines = [
        "✅ Qazolar ro'yxatga qo'shildi!",
        "",
        f"🆕 Yangi qo'shildi: {created_total} ta",
    ]
    if skipped_total > 0:
        lines.append(f"⏭ Oldin qo'shilgan (o'tkazildi): {skipped_total} ta")
    lines += [
        "",
        "Endi qazo ro'yxatingizda ko'rishingiz va birma-bir bajarib borishingiz mumkin.",
    ]
    await _send(callback, "\n".join(lines), _success_keyboard(lang))


@router.callback_query(F.data == "calc2:cancel")
async def calculator_cancel(callback: CallbackQuery, current_user: User, session):
    await StatesRepository(session).clear(current_user.id)
    lang = _lang(current_user)
    await _send(callback, await build_dashboard(current_user, session), dashboard_keyboard(lang))


# ── state: freetext year input ────────────────────────────────────────────────

async def handle_calc2_year_input(message: Message, current_user: User, session, text: str) -> bool:
    """Called from state_text_handler when state == calc2_waiting_years. Returns True if handled."""
    lang = _lang(current_user)
    parts = text.strip().split()
    today = tashkent_today()
    try:
        if len(parts) == 1:
            y = int(parts[0])
            start_year = end_year = y
        elif len(parts) == 2:
            start_year, end_year = int(parts[0]), int(parts[1])
        else:
            raise ValueError
        if not (1900 <= start_year <= today.year) or not (1900 <= end_year <= today.year):
            raise ValueError
        if start_year > end_year:
            start_year, end_year = end_year, start_year
    except ValueError:
        await message.answer(
            f"❌ Noto'g'ri format. Yilni to'g'ri kiriting.\n\nMisol: 2018 2023\n\n"
            f"Yillar 1900 va {today.year} orasida bo'lishi kerak."
        )
        return True

    payload = {"start_year": start_year, "end_year": end_year, "selected": []}
    await StatesRepository(session).set(current_user.id, "calc2_step2", payload)
    await message.answer(_step2_text(lang, start_year, end_year), reply_markup=_prayers_keyboard(lang, []))
    return True


# ── backward compat for old calc: callbacks (redirect to new flow) ─────────────
@router.callback_query(F.data.startswith("calc:type:"))
@router.callback_query(F.data.startswith("calc_toggle:"))
@router.callback_query(F.data.in_({"calc:select_all", "calc:clear_all", "calc:preview",
                                    "calc:save_only", "calc:apply_confirm", "calc:apply",
                                    "calc:back_to_end", "calc:back_to_prayers", "calc:cancel"}))
async def old_calc_redirect(callback: CallbackQuery, current_user: User, session):
    """Redirect any lingering old calc: callbacks to the new flow."""
    await StatesRepository(session).clear(current_user.id)
    lang = _lang(current_user)
    await _send(callback, _step1_text(lang), _period_keyboard(lang))
