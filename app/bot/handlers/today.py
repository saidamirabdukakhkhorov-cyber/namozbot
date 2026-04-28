from __future__ import annotations

from datetime import date

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.keyboards.prayer import prayers_status_keyboard
from app.core.constants import PRAYER_NAMES
from app.db.models import User
from app.db.repositories.daily_prayers import DailyPrayersRepository
from app.db.repositories.prayer_times import PrayerTimesRepository
from app.services.i18n import prayer_label, t
from app.services.prayer_times import PrayerTimesService

router = Router(name="today")


@router.message(Command("today"))
@router.message(F.text.in_({"🕌 Bugungi namozlar", "🕌 Намазы на сегодня", "🕌 Today’s prayers"}))
async def today_handler(message: Message, current_user: User, session):
    lang = current_user.language_code
    if not current_user.city:
        await message.answer(t(lang, "city.choose_first"))
        return

    service = PrayerTimesService(PrayerTimesRepository(session))
    try:
        dto = await service.get_or_fetch(current_user.city, date.today(), current_user.timezone)
    except Exception:
        await message.answer(t(lang, "today.no_times"))
        return

    repo = DailyPrayersRepository(session)
    lines = [t(lang, "today.title"), f"{t(lang, 'city.label')}: {current_user.city}", ""]
    daily_items = []
    times = dto.as_dict()

    for prayer in PRAYER_NAMES:
        prayer_dt = service.combine(dto.prayer_date, times[prayer], current_user.timezone)
        daily = await repo.upsert_pending(
            user_id=current_user.id,
            prayer_name=prayer,
            prayer_date=dto.prayer_date,
            prayer_time=prayer_dt,
        )
        daily_items.append(daily)
        lines.append(
            f"{prayer_label(lang, prayer)}: {times[prayer].strftime('%H:%M')} — {t(lang, 'status.' + daily.status)}"
        )

    await message.answer(
        "\n".join(lines),
        reply_markup=prayers_status_keyboard(lang, daily_items),
    )
