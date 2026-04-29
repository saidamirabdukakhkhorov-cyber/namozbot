from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.scheduler.jobs import ensure_daily_prayers_job, send_due_prayer_reminders_job, send_qazo_reminders_job


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    scheduler.add_job(ensure_daily_prayers_job, "cron", hour=3, minute=30, id="ensure_daily_prayers", replace_existing=True)
    scheduler.add_job(send_due_prayer_reminders_job, "interval", minutes=1, args=[bot], id="send_due_prayer_reminders", replace_existing=True, max_instances=1)
    scheduler.add_job(send_qazo_reminders_job, "cron", hour=8, minute=0, args=[bot], id="send_qazo_reminders_morning", replace_existing=True)
    scheduler.add_job(send_qazo_reminders_job, "cron", hour=21, minute=0, args=[bot], id="send_qazo_reminders_evening", replace_existing=True)
    return scheduler
