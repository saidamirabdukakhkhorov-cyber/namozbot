from __future__ import annotations

from datetime import date

import structlog
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.core.constants import PRAYER_NAMES
from app.db.models import User
from app.db.repositories.daily_prayers import DailyPrayersRepository
from app.db.repositories.prayer_times import PrayerTimesRepository
from app.services.i18n import prayer_label, t
from app.services.prayer_times import PrayerTimesService

router = Router(name="today")
logger = structlog.get_logger(__name__)


@router.message(Command("today"))
@router.message(F.text.in_({"🕌 Bugungi namozlar", "🕌 Намазы на сегодня", "🕌 Today’s prayers"}))
async def today_handler(message: Message, current_user: User, session):
    lang = current_user.language_code or "uz"

    if not current_user.city:
        await message.answer(t(lang, "city.choose_first"))
        return

    service = PrayerTimesService(PrayerTimesRepository(session))

    try:
        dto = await service.get_or_fetch(current_user.city, date.today(), current_user.timezone)
    except Exception as exc:
        logger.exception(
            "failed_to_fetch_today_prayer_times",
            user_id=current_user.id,
            telegram_id=current_user.telegram_id,
            city=current_user.city,
            timezone=current_user.timezone,
            error=str(exc),
        )
        await message.answer(t(lang, "today.no_times"))
        return

    repo = DailyPrayersRepository(session)
    times = dto.as_dict()

    lines = [
        t(lang, "today.title"),
        f"{t(lang, 'city.label')}: {current_user.city}",
        "",
    ]

    for prayer in PRAYER_NAMES:
        prayer_dt = service.combine(dto.prayer_date, times[prayer], current_user.timezone)
        daily = await repo.upsert_pending(
            user_id=current_user.id,
            prayer_name=prayer,
            prayer_date=dto.prayer_date,
            prayer_time=prayer_dt,
        )
        lines.append(
            f"{prayer_label(lang, prayer)}: {times[prayer].strftime('%H:%M')} — {t(lang, 'status.' + daily.status)}"
        )

    await message.answer("\n".join(lines))
