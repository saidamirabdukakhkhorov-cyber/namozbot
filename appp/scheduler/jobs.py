from datetime import date, datetime, timedelta, timezone
from aiogram import Bot
from sqlalchemy import select
from app.core.constants import PRAYER_NAMES
from app.db.models import DailyPrayer, ReminderSetting, User
from app.db.repositories.daily_prayers import DailyPrayersRepository
from app.db.repositories.prayer_times import PrayerTimesRepository
from app.db.repositories.reminders import RemindersRepository
from app.db.session import AsyncSessionLocal
from app.scheduler.locks import advisory_lock
from app.services.i18n import prayer_label, t
from app.services.prayer_times import PrayerTimesService

async def ensure_daily_prayers_job() -> None:
    async with AsyncSessionLocal() as session:
        async with advisory_lock(session, 42826002) as acquired:
            if not acquired:
                return
            users = (await session.scalars(select(User).where(User.is_active.is_(True), User.city.is_not(None)))).all()
            service = PrayerTimesService(PrayerTimesRepository(session))
            repo = DailyPrayersRepository(session)
            for user in users:
                try:
                    dto = await service.get_or_fetch(user.city, date.today(), user.timezone)
                except Exception:
                    continue
                for prayer in PRAYER_NAMES:
                    await repo.upsert_pending(user_id=user.id, prayer_name=prayer, prayer_date=dto.prayer_date, prayer_time=service.combine(dto.prayer_date, dto.as_dict()[prayer], user.timezone))
            await session.commit()

async def send_due_prayer_reminders_job(bot: Bot) -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        async with advisory_lock(session, 42826003) as acquired:
            if not acquired:
                return
            rows = (await session.scalars(select(DailyPrayer).where(DailyPrayer.status.in_(["pending", "snoozed"]), DailyPrayer.prayer_time <= now + timedelta(minutes=1)).limit(200))).all()
            reminders = RemindersRepository(session)
            for daily in rows:
                user = await session.get(User, daily.user_id)
                if not user or not user.is_active:
                    continue
                log, created = await reminders.create_pending(user_id=user.id, reminder_type="prayer_time", related_entity_type="daily_prayer", related_entity_id=daily.id, scheduled_for=daily.prayer_time)
                if not created:
                    continue
                try:
                    await bot.send_message(user.telegram_id, f"🕌 {prayer_label(user.language_code, daily.prayer_name)} vaqti kirdi\n\nNamozni o'qidingizmi?")
                    await reminders.mark_sent(log.id)
                except Exception as exc:
                    await reminders.mark_failed(log.id, str(exc)[:500])
            await session.commit()

async def send_qazo_reminders_job(bot: Bot) -> None:
    # MVP-safe placeholder: counts are DB-first; production can add quiet-hours aware batching here.
    return None
