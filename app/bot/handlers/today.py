from __future__ import annotations

from datetime import date

from aiogram import F, Router
from app.bot.filters.text import text_is_one_of
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.prayer import today_prayers_keyboard
from app.core.constants import PRAYER_NAMES
from app.db.models import User
from app.db.repositories.daily_prayers import DailyPrayersRepository
from app.db.repositories.prayer_times import PrayerTimesRepository
from app.db.repositories.states import StatesRepository
from app.services.i18n import prayer_label, t
from app.services.prayer_times import PrayerTimesService

router = Router(name="today")


async def build_today_screen(user: User, session) -> tuple[str, object | None]:
    lang = user.language_code or "uz"
    if not user.city:
        return t(lang, "city.choose_first"), None

    service = PrayerTimesService(PrayerTimesRepository(session))
    try:
        dto = await service.get_or_fetch(user.city, date.today(), user.timezone)
    except Exception:
        return t(lang, "error.api_prayer_times"), None

    repo = DailyPrayersRepository(session)
    lines = [
        t(lang, "today.title"),
        "",
        t(lang, "today.city", city=user.city),
        t(lang, "today.date", date=dto.prayer_date.isoformat()),
        "",
    ]
    daily_items = []
    times = dto.as_dict()

    for prayer in PRAYER_NAMES:
        prayer_dt = service.combine(dto.prayer_date, times[prayer], user.timezone)
        daily = await repo.upsert_pending(
            user_id=user.id,
            prayer_name=prayer,
            prayer_date=dto.prayer_date,
            prayer_time=prayer_dt,
        )
        daily_items.append(daily)
        lines.append(
            f"{prayer_label(lang, prayer)}: {times[prayer].strftime('%H:%M')} — {t(lang, 'status.' + daily.status)}"
        )

    return "\n".join(lines), today_prayers_keyboard(lang, daily_items)


@router.message(Command("today"))
@router.message(text_is_one_of("🕌 Bugungi namozlar", "🕌 Намазы на сегодня", "🕌 Today’s prayers", "Bugungi namozlar", "Намазы на сегодня", "Today’s prayers"))
async def today_handler(message: Message, current_user: User, session):
    await StatesRepository(session).clear(current_user.id)
    text, keyboard = await build_today_screen(current_user, session)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "today:open")
async def today_open(callback: CallbackQuery, current_user: User, session):
    await StatesRepository(session).clear(current_user.id)
    text, keyboard = await build_today_screen(current_user, session)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()
