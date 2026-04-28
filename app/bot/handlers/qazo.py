from __future__ import annotations

from datetime import date, timedelta

from aiogram import F, Router
from app.bot.filters.text import text_is_one_of
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.prayer import prayer_select_keyboard
from app.bot.keyboards.qazo import (
    qazo_add_confirm_keyboard,
    qazo_add_date_keyboard,
    qazo_calculator_section_keyboard,
    qazo_complete_count_keyboard,
    qazo_complete_prayers_keyboard,
    qazo_complete_source_keyboard,
    qazo_complete_success_keyboard,
    qazo_overview_keyboard,
    qazo_period_keyboard,
)
from app.core.constants import ALL_QAZO_SOURCES, CURRENT_QAZO_SOURCES, PRAYER_NAMES
from app.db.models import User
from app.db.repositories.missed_prayers import MissedPrayersRepository
from app.db.repositories.qazo_calculations import QazoCalculationsRepository
from app.db.repositories.states import StatesRepository
from app.services.date_periods import current_month_range, period_by_key
from app.services.i18n import prayer_label, t

router = Router(name="qazo")


def source_values(source_key: str):
    if source_key == "current":
        return list(CURRENT_QAZO_SOURCES)
    if source_key == "calculator":
        return ["calculator"]
    return list(ALL_QAZO_SOURCES)


def source_label(language: str, source_key: str) -> str:
    return t(language, f"qazo.completion.source_label.{source_key}")


async def send_or_edit(event: Message | CallbackQuery, text: str, reply_markup=None):
    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=reply_markup)
        except Exception:
            await event.message.answer(text, reply_markup=reply_markup)
        await event.answer()
    else:
        await event.answer(text, reply_markup=reply_markup)


def period_title(language: str, key: str) -> str:
    return t(language, f"period.{key}")


async def render_qazo_overview(user: User, session, *, start: date | None = None, end: date | None = None, label: str | None = None) -> tuple[str, bool]:
    lang = user.language_code or "uz"
    if start is None or end is None:
        start, end = current_month_range()
        label = t(lang, "period.this_month")
    repo = MissedPrayersRepository(session)
    current = await repo.summary(user.id, start, end, CURRENT_QAZO_SOURCES)
    calculator = await repo.total_active(user.id, ["calculator"])
    current_total = sum(current.values())

    if current_total == 0:
        lines = [
            t(lang, "qazo.list.title"),
            "",
            t(lang, "qazo.list.period", period=label or f"{start} — {end}"),
            "",
            t(lang, "qazo.list.empty"),
            "",
            t(lang, "qazo.list.calculator_short", count=calculator),
        ]
        return "\n".join(lines), True

    lines = [
        t(lang, "qazo.list.title"),
        "",
        t(lang, "qazo.list.period", period=label or f"{start} — {end}"),
        f"{start} — {end}",
        "",
        t(lang, "qazo.list.active_count", count=current_total),
        "",
    ]
    for p in PRAYER_NAMES:
        lines.append(f"{prayer_label(lang, p)}: {current.get(p, 0)} ta")
    lines += ["", t(lang, "qazo.list.calculator_active", count=calculator)]
    return "\n".join(lines), False


@router.message(Command("qazo"))
@router.message(text_is_one_of("📌 Qazo namozlarim", "📌 Мои каза-намазы", "📌 My missed prayers", "Qazo namozlarim", "Мои каза-намазы", "My missed prayers"))
async def qazo_menu(message: Message, current_user: User, session):
    await StatesRepository(session).clear(current_user.id)
    text, empty = await render_qazo_overview(current_user, session)
    await message.answer(text, reply_markup=qazo_overview_keyboard(current_user.language_code, empty=empty))


@router.callback_query(F.data == "qazo:overview")
async def qazo_menu_cb(callback: CallbackQuery, current_user: User, session):
    await StatesRepository(session).clear(current_user.id)
    text, empty = await render_qazo_overview(current_user, session)
    await send_or_edit(callback, text, qazo_overview_keyboard(current_user.language_code, empty=empty))


@router.callback_query(F.data == "qazo:period")
async def qazo_period(callback: CallbackQuery, current_user: User):
    lang = current_user.language_code or "uz"
    await send_or_edit(callback, t(lang, "qazo.period.title") + "\n\n" + t(lang, "qazo.period.question"), qazo_period_keyboard(lang))


@router.callback_query(F.data.startswith("qazo_period:"))
async def qazo_period_select(callback: CallbackQuery, current_user: User, session):
    lang = current_user.language_code or "uz"
    key = callback.data.split(":", 1)[1]
    if key == "custom":
        await StatesRepository(session).set(current_user.id, "waiting_qazo_period_start", {})
        text = t(lang, "qazo.period.custom_start")
        await send_or_edit(callback, text)
        return
    p = period_by_key(key)
    text, empty = await render_qazo_overview(current_user, session, start=p.start, end=p.end, label=period_title(lang, p.key))
    await send_or_edit(callback, text, qazo_overview_keyboard(lang, empty=empty))


@router.callback_query(F.data == "qazo:calculator_section")
async def qazo_calculator_section(callback: CallbackQuery, current_user: User, session):
    lang = current_user.language_code or "uz"
    counts = await MissedPrayersRepository(session).summary(current_user.id, sources=["calculator"])
    total = sum(counts.values())
    if total == 0:
        text = t(lang, "qazo.calculator.empty")
        await send_or_edit(callback, text, qazo_calculator_section_keyboard(lang, empty=True))
        return
    lines = [t(lang, "qazo.calculator.title"), "", t(lang, "qazo.calculator.active_intro"), ""]
    for p in PRAYER_NAMES:
        lines.append(f"{prayer_label(lang, p)}: {counts.get(p, 0)} ta")
    lines += ["", t(lang, "qazo.calculator.total", count=total)]
    await send_or_edit(callback, "\n".join(lines), qazo_calculator_section_keyboard(lang))


@router.callback_query(F.data == "qazo:calc_history")
async def qazo_calc_history(callback: CallbackQuery, current_user: User, session):
    lang = current_user.language_code or "uz"
    rows = await QazoCalculationsRepository(session).history(current_user.id, limit=5)
    if not rows:
        await send_or_edit(callback, t(lang, "qazo.calculator.history_empty"), qazo_calculator_section_keyboard(lang, empty=True))
        return
    lines = [t(lang, "qazo.calculator.history_title"), ""]
    for item in rows:
        lines.append(f"• {item.start_date} — {item.end_date}: {item.total_count} ta ({item.status})")
    await send_or_edit(callback, "\n".join(lines), qazo_calculator_section_keyboard(lang))


@router.callback_query(F.data == "qazo:all")
async def qazo_all(callback: CallbackQuery, current_user: User, session):
    lang = current_user.language_code or "uz"
    counts = await MissedPrayersRepository(session).summary(current_user.id)
    lines = [t(lang, "qazo.all.title"), ""]
    for p in PRAYER_NAMES:
        lines.append(f"{prayer_label(lang, p)}: {counts.get(p, 0)} ta")
    lines += ["", t(lang, "qazo.calculator.total", count=sum(counts.values()))]
    await send_or_edit(callback, "\n".join(lines), qazo_overview_keyboard(lang))


@router.callback_query(F.data == "back")
async def qazo_back(callback: CallbackQuery, current_user: User, session):
    text, empty = await render_qazo_overview(current_user, session)
    await send_or_edit(callback, text, qazo_overview_keyboard(current_user.language_code, empty=empty))


@router.message(text_is_one_of("➕ Qazo qo'shish", "➕ Qazo qo‘shish", "➕ Добавить каза", "➕ Add missed prayer", "Qazo qo'shish", "Qazo qo‘shish", "Добавить каза", "Add missed prayer"))
@router.callback_query(F.data == "qazo_add:start")
async def qazo_add_start(event: Message | CallbackQuery, current_user: User, session):
    await StatesRepository(session).set(current_user.id, "qazo_add_date", {})
    lang = current_user.language_code or "uz"
    await send_or_edit(event, t(lang, "qazo.add.date_screen"), qazo_add_date_keyboard(lang))


@router.callback_query(F.data.startswith("qazo_add_date:"))
async def qazo_add_date(callback: CallbackQuery, current_user: User, session):
    lang = current_user.language_code or "uz"
    raw_day = callback.data.split(":", 1)[1]
    if raw_day == "custom":
        await StatesRepository(session).set(current_user.id, "waiting_qazo_add_date", {})
        await send_or_edit(callback, t(lang, "qazo.add.custom_date"))
        return
    day = date.today() if raw_day == "today" else date.today() - timedelta(days=1)
    await StatesRepository(session).set(current_user.id, "qazo_add_prayer", {"date": day.isoformat()})
    text = t(lang, "qazo.add.prayer_screen", date=day.isoformat())
    await send_or_edit(callback, text, prayer_select_keyboard(lang, "qazo_add_prayer"))


@router.callback_query(F.data == "qazo_add:choose_prayer")
async def qazo_add_choose_prayer(callback: CallbackQuery, current_user: User, session):
    lang = current_user.language_code or "uz"
    state = await StatesRepository(session).get(current_user.id)
    payload = state.payload if state else {}
    day = payload.get("date", date.today().isoformat())
    await StatesRepository(session).set(current_user.id, "qazo_add_prayer", {"date": day})
    await send_or_edit(callback, t(lang, "qazo.add.prayer_screen", date=day), prayer_select_keyboard(lang, "qazo_add_prayer"))


@router.callback_query(F.data.startswith("qazo_add_prayer:"))
async def qazo_add_prayer(callback: CallbackQuery, current_user: User, session):
    lang = current_user.language_code or "uz"
    prayer = callback.data.split(":", 1)[1]
    state = await StatesRepository(session).get(current_user.id)
    payload = state.payload if state else {}
    day = payload.get("date")
    if not day:
        await StatesRepository(session).set(current_user.id, "qazo_add_date", {})
        await send_or_edit(callback, t(lang, "qazo.add.date_screen"), qazo_add_date_keyboard(lang))
        return
    await StatesRepository(session).set(current_user.id, "qazo_add_confirm", {"date": day, "prayer": prayer})
    text = t(lang, "qazo.add.confirm", date=day, prayer=prayer_label(lang, prayer))
    await send_or_edit(callback, text, qazo_add_confirm_keyboard(lang, prayer))


@router.callback_query(F.data.startswith("qazo_add_confirm:"))
async def qazo_add_confirm(callback: CallbackQuery, current_user: User, session):
    lang = current_user.language_code or "uz"
    prayer = callback.data.split(":", 1)[1]
    state = await StatesRepository(session).get(current_user.id)
    payload = state.payload if state else {}
    day = date.fromisoformat(payload.get("date"))
    _, created = await MissedPrayersRepository(session).create(user_id=current_user.id, prayer_name=prayer, prayer_date=day, source="manual")
    await StatesRepository(session).clear(current_user.id)
    key = "qazo.add.success" if created else "qazo.add.duplicate"
    text = t(lang, key, prayer=prayer_label(lang, prayer), date=day.isoformat())
    await send_or_edit(callback, text, qazo_overview_keyboard(lang))


@router.callback_query(F.data == "qazo_complete:start")
async def qazo_complete_start(callback: CallbackQuery, current_user: User, session):
    lang = current_user.language_code or "uz"
    repo = MissedPrayersRepository(session)
    current = await repo.total_active(current_user.id, CURRENT_QAZO_SOURCES)
    calc = await repo.total_active(current_user.id, ["calculator"])
    total = await repo.total_active(current_user.id)
    text = t(lang, "qazo.completion.source_screen", current=current, calculator=calc, total=total)
    await send_or_edit(callback, text, qazo_complete_source_keyboard(lang))


@router.callback_query(F.data.startswith("qazo_complete_source:"))
async def qazo_complete_source(callback: CallbackQuery, current_user: User, session):
    lang = current_user.language_code or "uz"
    source_key = callback.data.split(":", 1)[1]
    counts = await MissedPrayersRepository(session).summary(current_user.id, sources=source_values(source_key))
    if sum(counts.values()) == 0:
        await send_or_edit(callback, t(lang, "qazo.empty.active"), qazo_overview_keyboard(lang, empty=True))
    else:
        text = t(lang, "qazo.completion.prayer_screen", source=source_label(lang, source_key))
        await send_or_edit(callback, text, qazo_complete_prayers_keyboard(lang, counts, source_key))


@router.callback_query(F.data.startswith("qazo_complete_prayer:"))
async def qazo_complete_prayer(callback: CallbackQuery, current_user: User, session):
    lang = current_user.language_code or "uz"
    _, source_key, prayer = callback.data.split(":")
    count = await MissedPrayersRepository(session).count_by_prayer(current_user.id, prayer, source_values(source_key))
    text = t(
        lang,
        "qazo.completion.count_screen",
        prayer=prayer_label(lang, prayer),
        source=source_label(lang, source_key),
        count=count,
    )
    await send_or_edit(callback, text, qazo_complete_count_keyboard(lang, source_key, prayer, count))


@router.callback_query(F.data.startswith("qazo_complete_count:"))
async def qazo_complete_count(callback: CallbackQuery, current_user: User, session):
    lang = current_user.language_code or "uz"
    _, source_key, prayer, raw_count = callback.data.split(":")
    try:
        count = int(raw_count)
        action = await MissedPrayersRepository(session).complete_oldest(current_user.id, prayer, count, source_values(source_key))
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    remaining = await MissedPrayersRepository(session).count_by_prayer(current_user.id, prayer, source_values(source_key))
    total = await MissedPrayersRepository(session).total_active(current_user.id)
    text = t(
        lang,
        "qazo.completion.success",
        count=count,
        prayer=prayer_label(lang, prayer),
        source=source_label(lang, source_key),
        remaining=remaining,
        total=total,
    )
    await send_or_edit(callback, text, qazo_complete_success_keyboard(lang, action.id))


@router.callback_query(F.data.startswith("qazo_complete_custom:"))
async def qazo_complete_custom(callback: CallbackQuery, current_user: User, session):
    lang = current_user.language_code or "uz"
    _, source_key, prayer = callback.data.split(":")
    await StatesRepository(session).set(current_user.id, "waiting_qazo_complete_count", {"source_key": source_key, "prayer": prayer})
    await send_or_edit(callback, t(lang, "qazo.completion.manual_prompt", prayer=prayer_label(lang, prayer)))


@router.callback_query(F.data.startswith("undo_completion:"))
async def undo_completion(callback: CallbackQuery, current_user: User, session):
    lang = current_user.language_code or "uz"
    action_id = int(callback.data.split(":", 1)[1])
    action = await MissedPrayersRepository(session).undo_completion_action(current_user.id, action_id)
    if not action:
        await callback.answer(t(lang, "qazo.completion.undo_failed"), show_alert=True)
        return
    text = t(lang, "qazo.completion.undo_success", count=action.completed_count, prayer=prayer_label(lang, action.prayer_name))
    await send_or_edit(callback, text, qazo_overview_keyboard(lang))
