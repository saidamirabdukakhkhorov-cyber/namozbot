from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import Bot
from sqlalchemy import and_, or_, select

from app.bot.keyboards.prayer import prayer_status_keyboard
from app.core.constants import PRAYER_NAMES
from app.db.models import DailyPrayer, ReminderSetting, User
from app.db.repositories.daily_prayers import DailyPrayersRepository
from app.db.repositories.prayer_times import PrayerTimesRepository
from app.db.repositories.reminders import RemindersRepository
from app.db.session import AsyncSessionLocal
from app.scheduler.locks import advisory_lock
from app.services.i18n import prayer_label, t
from app.services.prayer_times import PrayerTimesService
from app.services.timezone import tashkent_today

TASHKENT_TZ = ZoneInfo("Asia/Tashkent")

PRAYER_CHECK_DELAY_MINUTES = 30


def _motivational_line(language: str) -> str:
    # FIX: use i18n system instead of hardcoded strings
    return t(language, "reminder.motivational_line")


def _format_prayer_time_push(language: str, daily: DailyPrayer) -> str:
    due_at = _as_tashkent(_due_prayer_time(daily))
    prayer = prayer_label(language, daily.prayer_name)
    if language == "ru":
        return (
            f"🕌 Время намаза: {prayer}\n\n"
            f"🕒 {due_at.strftime('%H:%M')} (ташкентское время, GMT+5)\n\n"
            f"{_motivational_line(language)}"
        )
    if language == "en":
        return (
            f"🕌 It is time for {prayer}\n\n"
            f"🕒 {due_at.strftime('%H:%M')} (Tashkent time, GMT+5)\n\n"
            f"{_motivational_line(language)}"
        )
    return (
        f"🕌 {prayer} vaqti kirdi\n\n"
        f"🕒 {due_at.strftime('%H:%M')} (Toshkent vaqti, GMT+5)\n\n"
        f"{_motivational_line(language)}"
    )


def _format_prayer_check_push(language: str, daily: DailyPrayer) -> str:
    prayer = prayer_label(language, daily.prayer_name)
    if language == "ru":
        return f"🕌 {prayer}\n\nВы уже совершили этот намаз?"
    if language == "en":
        return f"🕌 {prayer}\n\nDid you complete this prayer?"
    return f"🕌 {prayer}\n\nNamozni o‘qidingizmi?"


def _is_in_window(target: datetime, now_tashkent: datetime) -> bool:
    target = _as_tashkent(target)
    return now_tashkent - timedelta(minutes=2) <= target <= now_tashkent + timedelta(minutes=1)


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


def _as_tashkent(dt: datetime) -> datetime:
    """Normalize DB datetimes to Asia/Tashkent.

    SQLAlchemy/Postgres deployments often store prayer_time as a timezone-less
    timestamp. In that case the value represents local Tashkent prayer time, not
    UTC. Treating it as UTC makes future prayers look overdue and causes a huge
    batch reminder.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=TASHKENT_TZ)
    return dt.astimezone(TASHKENT_TZ)


def _is_due_now(daily: DailyPrayer, now_tashkent: datetime) -> bool:
    """Return True only for the exact prayer reminder window.

    We intentionally do not send backlog reminders here. Missed/backlog summaries
    belong to a separate qazo reminder job. This keeps Telegram push messages
    clean: one prayer at its time, instead of all today prayers in one message.
    """
    due_at = _as_tashkent(_due_prayer_time(daily))
    window_start = now_tashkent - timedelta(minutes=2)
    window_end = now_tashkent + timedelta(minutes=1)
    return window_start <= due_at <= window_end


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
        prayer_time = _as_tashkent(_due_prayer_time(daily)).strftime("%H:%M")
        lines.append(f"🕌 {prayer_label(language, daily.prayer_name)} — {prayer_time}")
    return "\n".join(lines)


async def send_due_prayer_reminders_job(bot: Bot) -> None:
    """Mini-App first prayer reminders.

    Flow:
    1) At prayer time: send a clean motivational reminder without action buttons.
    2) After PRAYER_CHECK_DELAY_MINUTES: ask whether the prayer was completed.
       Only then the user can choose: prayed / qazo / remind later.
    3) Snoozed reminders also ask the same question when due.
    """
    now_tashkent = datetime.now(TASHKENT_TZ)
    today_tashkent = now_tashkent.date()

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
                                DailyPrayer.prayer_date == today_tashkent,
                            ),
                            and_(
                                DailyPrayer.status == "snoozed",
                                DailyPrayer.snooze_until.is_not(None),
                            ),
                        )
                    )
                    .order_by(DailyPrayer.user_id.asc(), DailyPrayer.prayer_time.asc())
                    .limit(1000)
                )
            ).all()

            reminders = RemindersRepository(session)

            for daily in rows:
                user = await session.get(User, daily.user_id)
                if not user or not user.is_active:
                    continue

                setting = (
                    await session.scalars(
                        select(ReminderSetting).where(ReminderSetting.user_id == user.id)
                    )
                ).first()
                if setting and not setting.prayer_reminders_enabled:
                    continue

                lang = user.language_code or "uz"
                due_at = _as_tashkent(_due_prayer_time(daily))

                if daily.status == "snoozed":
                    if not _is_in_window(due_at, now_tashkent):
                        continue
                    log, created = await reminders.create_pending(
                        user_id=user.id,
                        reminder_type="prayer_snooze_check",
                        related_entity_type="daily_prayer",
                        related_entity_id=daily.id,
                        scheduled_for=due_at,
                    )
                    if not created or not log:
                        continue
                    try:
                        await bot.send_message(
                            user.telegram_id,
                            _format_prayer_check_push(lang, daily),
                            reply_markup=prayer_status_keyboard(lang, daily.id),
                        )
                        await reminders.mark_sent(log.id)
                    except Exception as exc:
                        await reminders.mark_failed(log.id, str(exc)[:500])
                    continue

                # Step 1: prayer-time motivational push, no buttons.
                if _is_in_window(due_at, now_tashkent):
                    log, created = await reminders.create_pending(
                        user_id=user.id,
                        reminder_type="prayer_time",
                        related_entity_type="daily_prayer",
                        related_entity_id=daily.id,
                        scheduled_for=daily.prayer_time,
                    )
                    if created and log:
                        try:
                            await bot.send_message(user.telegram_id, _format_prayer_time_push(lang, daily))
                            await reminders.mark_sent(log.id)
                        except Exception as exc:
                            await reminders.mark_failed(log.id, str(exc)[:500])

                # Step 2: after a short delay, ask for status with actions.
                check_at = due_at + timedelta(minutes=PRAYER_CHECK_DELAY_MINUTES)
                if _is_in_window(check_at, now_tashkent):
                    log, created = await reminders.create_pending(
                        user_id=user.id,
                        reminder_type="prayer_check",
                        related_entity_type="daily_prayer",
                        related_entity_id=daily.id,
                        scheduled_for=check_at,
                    )
                    if not created or not log:
                        continue
                    try:
                        await bot.send_message(
                            user.telegram_id,
                            _format_prayer_check_push(lang, daily),
                            reply_markup=prayer_status_keyboard(lang, daily.id),
                        )
                        await reminders.mark_sent(log.id)
                    except Exception as exc:
                        await reminders.mark_failed(log.id, str(exc)[:500])

            await session.commit()


async def send_qazo_reminders_job(bot: Bot) -> None:
    # MVP-safe placeholder: counts are DB-first; production can add quiet-hours aware batching here.
    return None
