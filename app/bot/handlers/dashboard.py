from __future__ import annotations

from aiogram import F, Router
from app.bot.filters.text import text_is_one_of
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.keyboards.main import main_menu_keyboard
from app.core.constants import CURRENT_QAZO_SOURCES, PRAYER_NAMES
from app.db.models import User
from app.db.repositories.daily_prayers import DailyPrayersRepository
from app.db.repositories.missed_prayers import MissedPrayersRepository
from app.db.repositories.states import StatesRepository
from app.services.date_periods import current_month_range
from app.services.timezone import tashkent_today, tashkent_now
from app.services.i18n import prayer_label, t
from app.db.repositories.prayer_times import PrayerTimesRepository
from app.services.prayer_times import PrayerTimesService, _extract_times, _parse_hhmm

router = Router(name="dashboard")


def dashboard_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "menu.today"), callback_data="today:open")],
        [InlineKeyboardButton(text=t(language, "menu.qazo"), callback_data="qazo:overview")],
        [InlineKeyboardButton(text=t(language, "menu.calculator"), callback_data="calc:start")],
        [InlineKeyboardButton(text=t(language, "menu.stats"), callback_data="stats:open")],
    ])


def _format_left(minutes: int) -> str:
    h, m = divmod(max(0, minutes), 60)
    return f"{h} soat {m} daqiqa" if h else f"{m} daqiqa"


def _extract_sunrise(raw_payload: dict):
    try:
        data = _extract_times(raw_payload or {})
        lower = {str(k).lower(): v for k, v in data.items()}
        value = data.get("quyosh") or data.get("Quyosh") or lower.get("quyosh") or lower.get("sunrise")
        return _parse_hhmm(value) if value else None
    except Exception:
        return None


async def build_dashboard(user: User, session) -> str:
    lang = user.language_code or "uz"
    today = tashkent_today()
    daily_repo = DailyPrayersRepository(session)
    daily_rows = await daily_repo.list_for_date(user.id, today)
    daily = {row.prayer_name: row.status for row in daily_rows}
    daily_by_name = {row.prayer_name: row for row in daily_rows}
    now_tz = tashkent_now()
    now_text = now_tz.strftime("%H:%M:%S")
    prayer_times = {}
    sunrise_time = None
    next_name = None
    next_time_text = None
    next_left = None
    if user.city:
        try:
            service = PrayerTimesService(PrayerTimesRepository(session))
            dto = await service.get_or_fetch(user.city, today, user.timezone or "Asia/Tashkent")
            prayer_times = dto.as_dict()
            sunrise_time = _extract_sunrise(dto.raw_payload)
            order = [("fajr", prayer_times.get("fajr")), ("sunrise", sunrise_time), ("dhuhr", prayer_times.get("dhuhr")), ("asr", prayer_times.get("asr")), ("maghrib", prayer_times.get("maghrib")), ("isha", prayer_times.get("isha"))]
            labels = {"fajr": prayer_label(lang, "fajr"), "sunrise": "Quyosh", "dhuhr": prayer_label(lang, "dhuhr"), "asr": prayer_label(lang, "asr"), "maghrib": prayer_label(lang, "maghrib"), "isha": prayer_label(lang, "isha")}
            now_min = now_tz.hour * 60 + now_tz.minute
            best = None
            for key, tm in order:
                if not tm:
                    continue
                diff = (tm.hour * 60 + tm.minute) - now_min
                if diff <= 0:
                    diff += 1440
                if best is None or diff < best[0]:
                    best = (diff, key, tm)
            if best:
                next_left, key, tm = best
                next_name = labels.get(key, key)
                next_time_text = tm.strftime("%H:%M")
        except Exception:
            pass
    start, end = current_month_range(today)
    repo = MissedPrayersRepository(session)
    current_summary = await repo.summary(user.id, start, end, CURRENT_QAZO_SOURCES)
    calculator_total = await repo.total_active(user.id, ["calculator"])

    lines = [
        t(lang, "dashboard.title"),
        "",
        t(lang, "dashboard.today", date=today.isoformat()),
        t(lang, "dashboard.city", city=user.city or "-"),
        f"🕒 Hozir: {now_text} (Toshkent, GMT+5)",
    ]
    if next_name and next_time_text and next_left is not None:
        lines.append(f"⏭ Keyingi: {next_name} — {next_time_text} ({_format_left(next_left)} qoldi)")
    lines += [
        "",
        t(lang, "dashboard.today_prayers"),
    ]
    for p in PRAYER_NAMES:
        status = daily.get(p, "pending")
        tm = prayer_times.get(p)
        time_text = f" — {tm.strftime('%H:%M')}" if tm else ""
        lines.append(f"{prayer_label(lang, p)}{time_text}: {t(lang, 'status.' + status)}")
        if p == "fajr" and sunrise_time:
            lines.append(f"Quyosh — {sunrise_time.strftime('%H:%M')}")

    lines += [
        "",
        t(lang, "dashboard.qazo"),
        t(lang, "dashboard.current_month", count=sum(current_summary.values())),
        t(lang, "dashboard.calculator_count", count=calculator_total),
    ]
    return "\n".join(lines)


@router.callback_query(F.data == "dashboard")
async def dashboard_cb(callback: CallbackQuery, current_user: User, session, is_admin: bool):
    await StatesRepository(session).clear(current_user.id)
    text = await build_dashboard(current_user, session)
    try:
        await callback.message.edit_text(text, reply_markup=dashboard_keyboard(current_user.language_code))
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=main_menu_keyboard(current_user.language_code, is_admin),
        )
    await callback.answer()


@router.message(text_is_one_of("/home", "🏠 Menu", "🏠 Asosiy menu", "🏠 Главное меню", "🏠 Main menu", "Asosiy menu", "Menu", "Главное меню", "Main menu"))
async def dashboard_msg(message: Message, current_user: User, session, is_admin: bool):
    await StatesRepository(session).clear(current_user.id)
    await message.answer(
        await build_dashboard(current_user, session),
        reply_markup=main_menu_keyboard(current_user.language_code, is_admin),
    )
