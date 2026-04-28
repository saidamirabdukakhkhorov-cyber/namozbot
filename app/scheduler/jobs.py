from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import Bot
from sqlalchemy import and_, or_, select

from app.bot.keyboards.prayer import prayer_status_keyboard, prayers_batch_status_keyboard
from app.core.constants import PRAYER_NAMES
from app.db.models import DailyPrayer, User
from app.db.repositories.daily_prayers import DailyPrayersRepository
from app.db.repositories.prayer_times import PrayerTimesRepository
from app.db.repositories.reminders import RemindersRepository
from app.db.session import AsyncSessionLocal
from app.scheduler.locks import advisory_lock
from app.services.i18n import prayer_label, t
from app.services.prayer_times import PrayerTimesService
from app.services.timezone import tashkent_today

TASHKENT_TZ = ZoneInfo("Asia/Tashkent")


async def ensure_daily_prayers_job() -> None:
    async with AsyncSessionLocal() as session:
        async with advisory_lock(session, 42826002) as acquired:
            if not acquired:
                return

            users = (
                await session.scalars(
                    select(User).where(User.is_active.is_(True), User.city.is_not(None))
                )
            ).all()
            service = PrayerTimesService(PrayerTimesRepository(session))
            repo = DailyPrayersRepository(session)

            for user in users:
                try:
                    dto = await service.get_or_fetch(user.city, tashkent_today(), user.timezone)
                except Exception:
                    continue

                times = dto.as_dict()
                for prayer in PRAYER_NAMES:
                    await repo.upsert_pending(
                        user_id=user.id,
                        prayer_name=prayer,
                        prayer_date=dto.prayer_date,
                        prayer_time=service.combine(dto.prayer_date, times[prayer], user.timezone),
                    )

            await session.commit()


def _due_prayer_time(daily: DailyPrayer) -> datetime:
    return daily.snooze_until if daily.status == "snoozed" and daily.snooze_until else daily.prayer_time


def _format_single_reminder_text(language: str, daily: DailyPrayer) -> str:
    now_tashkent = datetime.now(TASHKENT_TZ)
    reminder_text = t(
        language,
        "reminder.prayer_time",
        prayer=prayer_label(language, daily.prayer_name),
    )
    return (
        f"📅 {now_tashkent.strftime('%d.%m.%Y')}\n"
        f"🕒 {now_tashkent.strftime('%H:%M')} (Toshkent vaqti, GMT+5)\n\n"
        f"{reminder_text}"
    )


def _format_batch_reminder_text(language: str, daily_prayers: list[DailyPrayer]) -> str:
    now_tashkent = datetime.now(TASHKENT_TZ)
    date_text = now_tashkent.strftime("%d.%m.%Y")
    time_text = now_tashkent.strftime("%H:%M")

    if language == "ru":
        title = "Сегодняшние намазы"
        question = "Отметьте статус каждого намаза:"
        tz_label = "ташкентское время, GMT+5"
    elif language == "en":
        title = "Today's prayers"
        question = "Mark each prayer status:"
        tz_label = "Tashkent time, GMT+5"
    else:
        title = "Bugungi namozlar"
        question = "Har bir namoz holatini belgilang:"
        tz_label = "Toshkent vaqti, GMT+5"

    lines = [
        f"📅 {title} — {date_text}",
        f"🕒 {time_text} ({tz_label})",
        "",
        question,
        "",
    ]
    for daily in daily_prayers:
        prayer_time = _due_prayer_time(daily).astimezone(TASHKENT_TZ).strftime("%H:%M")
        lines.append(f"🕌 {prayer_label(language, daily.prayer_name)} — {prayer_time}")
    return "\n".join(lines)


async def send_due_prayer_reminders_job(bot: Bot) -> None:
    now = datetime.now(timezone.utc)
    pending_window_end = now + timedelta(minutes=1)

    async with AsyncSessionLocal() as session:
        async with advisory_lock(session, 42826003) as acquired:
            if not acquired:
                return

            rows = (
                await session.scalars(
                    select(DailyPrayer)
                    .where(
                        or_(
                            and_(
                                DailyPrayer.status == "pending",
                                DailyPrayer.prayer_time <= pending_window_end,
                            ),
                            and_(
                                DailyPrayer.status == "snoozed",
                                DailyPrayer.snooze_until.is_not(None),
                                DailyPrayer.snooze_until <= now,
                            ),
                        )
                    )
                    .order_by(DailyPrayer.user_id.asc(), DailyPrayer.prayer_time.asc())
                    .limit(200)
                )
            ).all()

            reminders = RemindersRepository(session)
            grouped: dict[int, list[tuple[DailyPrayer, int]]] = defaultdict(list)

            for daily in rows:
                user = await session.get(User, daily.user_id)
                if not user or not user.is_active:
                    continue

                log, created = await reminders.create_pending(
                    user_id=user.id,
                    reminder_type="prayer_time",
                    related_entity_type="daily_prayer",
                    related_entity_id=daily.id,
                    scheduled_for=_due_prayer_time(daily),
                )
                if created and log:
                    grouped[user.id].append((daily, log.id))

            for user_id, items in grouped.items():
                user = await session.get(User, user_id)
                if not user or not user.is_active:
                    continue

                daily_items = [daily for daily, _ in items]
                log_ids = [log_id for _, log_id in items]
                lang = user.language_code or "uz"

                try:
                    if len(daily_items) == 1:
                        daily = daily_items[0]
                        text = _format_single_reminder_text(lang, daily)
                        reply_markup = prayer_status_keyboard(lang, daily.id)
                    else:
                        text = _format_batch_reminder_text(lang, daily_items)
                        reply_markup = prayers_batch_status_keyboard(lang, daily_items)

                    await bot.send_message(user.telegram_id, text, reply_markup=reply_markup)
                    for log_id in log_ids:
                        await reminders.mark_sent(log_id)
                except Exception as exc:
                    for log_id in log_ids:
                        await reminders.mark_failed(log_id, str(exc)[:500])

            await session.commit()


async def send_qazo_reminders_job(bot: Bot) -> None:
    # MVP-safe placeholder: counts are DB-first; production can add quiet-hours aware batching here.
    return None
