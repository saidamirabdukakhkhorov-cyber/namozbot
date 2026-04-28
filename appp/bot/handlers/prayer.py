from datetime import datetime, timedelta, timezone
from aiogram import F, Router
from aiogram.types import CallbackQuery
from app.bot.keyboards.prayer import snooze_keyboard
from app.db.repositories.daily_prayers import DailyPrayersRepository
from app.db.repositories.missed_prayers import MissedPrayersRepository

router = Router(name="prayer")

@router.callback_query(F.data.startswith("daily:"))
async def daily_action(callback: CallbackQuery, current_user, session):
    _, action, raw_id = callback.data.split(":")
    daily_id = int(raw_id)
    daily_repo = DailyPrayersRepository(session)
    if action == "prayed":
        await daily_repo.set_status(daily_id, "prayed")
        await callback.message.answer("✅ Belgilandi")
    elif action == "missed":
        await daily_repo.set_status(daily_id, "missed")
        daily = await daily_repo.get_by_id(daily_id)
        if daily:
            await MissedPrayersRepository(session).create(user_id=daily.user_id, prayer_name=daily.prayer_name, prayer_date=daily.prayer_date, source="daily_confirmation", daily_prayer_id=daily.id)
        await callback.message.answer("📌 Qazo sifatida belgilandi")
    elif action == "snooze":
        await callback.message.answer("Qachon eslatay?", reply_markup=snooze_keyboard(current_user.language_code, daily_id))
    await callback.answer()

@router.callback_query(F.data.startswith("snooze:"))
async def snooze_action(callback: CallbackQuery, session):
    _, raw_minutes, raw_id = callback.data.split(":")
    await DailyPrayersRepository(session).set_status(int(raw_id), "snoozed", snooze_until=datetime.now(timezone.utc) + timedelta(minutes=int(raw_minutes)))
    await callback.message.answer("⏰ Eslatma keyinroq yuboriladi")
    await callback.answer()
