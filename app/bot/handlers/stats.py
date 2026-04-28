from __future__ import annotations

from datetime import date

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.stats import stats_keyboard
from app.core.constants import PRAYER_NAMES
from app.db.models import User
from app.db.repositories.missed_prayers import MissedPrayersRepository
from app.db.repositories.states import StatesRepository
from app.services.date_periods import period_by_key
from app.services.i18n import prayer_label, t
from app.services.stats import StatsService

router = Router(name="stats")


def period_title(language: str, key: str) -> str:
    return t(language, f"period.{key}")


async def render_stats(user: User, session, *, key: str = "this_month") -> str:
    lang = user.language_code or "uz"
    period = period_by_key(key)
    stats = await StatsService(session).period_stats(user.id, period.start, period.end)
    qazo_counts = await MissedPrayersRepository(session).summary(user.id, period.start, period.end)
    if sum(stats.values()) == 0 and sum(qazo_counts.values()) == 0:
        return t(lang, "stats.empty")
    lines = [
        t(lang, "stats.title"),
        "",
        t(lang, "stats.period", period=period_title(lang, period.key)),
        "",
        t(lang, "stats.prayers_read", count=stats["prayed"]),
        t(lang, "stats.prayers_qazo", count=stats["missed"]),
        t(lang, "stats.qazo_completed", count=stats["completed"]),
        t(lang, "stats.qazo_active", count=stats["active"]),
        "",
        t(lang, "stats.qazo_breakdown"),
    ]
    for p in PRAYER_NAMES:
        lines.append(f"{prayer_label(lang, p)}: {qazo_counts.get(p, 0)} ta")
    return "\n".join(lines)


@router.message(Command("stats"))
@router.message(F.text.in_({"📊 Statistika", "📊 Статистика", "📊 Statistics"}))
async def stats_handler(message: Message, current_user: User, session):
    await StatesRepository(session).clear(current_user.id)
    await message.answer(await render_stats(current_user, session), reply_markup=stats_keyboard(current_user.language_code))


@router.callback_query(F.data == "stats:open")
async def stats_open(callback: CallbackQuery, current_user: User, session):
    await StatesRepository(session).clear(current_user.id)
    text = await render_stats(current_user, session)
    try:
        await callback.message.edit_text(text, reply_markup=stats_keyboard(current_user.language_code))
    except Exception:
        await callback.message.answer(text, reply_markup=stats_keyboard(current_user.language_code))
    await callback.answer()


@router.callback_query(F.data.startswith("stats:period:"))
async def stats_period(callback: CallbackQuery, current_user: User, session):
    lang = current_user.language_code or "uz"
    key = callback.data.split(":", 2)[2]
    if key == "custom":
        await callback.answer(t(lang, "stats.custom_soon"), show_alert=True)
        return
    text = await render_stats(current_user, session, key=key)
    try:
        await callback.message.edit_text(text, reply_markup=stats_keyboard(lang))
    except Exception:
        await callback.message.answer(text, reply_markup=stats_keyboard(lang))
    await callback.answer()
