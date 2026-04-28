from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.keyboards.prayer import snooze_keyboard
from app.db.repositories.daily_prayers import DailyPrayersRepository
from app.db.repositories.missed_prayers import MissedPrayersRepository

router = Router(name="prayer")


def _parse_callback_id(callback: CallbackQuery) -> int | None:
    try:
        return int((callback.data or "").rsplit(":", 1)[1])
    except (IndexError, TypeError, ValueError):
        return None


@router.callback_query(F.data.startswith("daily:"))
async def daily_action(callback: CallbackQuery, current_user, session):
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer("Noto'g'ri amal", show_alert=True)
        return

    _, action, raw_id = parts
    try:
        daily_id = int(raw_id)
    except ValueError:
        await callback.answer("Noto'g'ri amal", show_alert=True)
        return

    daily_repo = DailyPrayersRepository(session)
    daily = await daily_repo.get_by_id(daily_id)
    if not daily or daily.user_id != current_user.id:
        await callback.answer("Bu amal sizga tegishli emas", show_alert=True)
        return

    if action == "prayed":
        await daily_repo.set_status(daily_id, "prayed")
        await callback.message.answer("✅ Belgilandi")
    elif action == "missed":
        await daily_repo.set_status(daily_id, "missed")
        await MissedPrayersRepository(session).create(
            user_id=daily.user_id,
            prayer_name=daily.prayer_name,
            prayer_date=daily.prayer_date,
            source="daily_confirmation",
            daily_prayer_id=daily.id,
        )
        await callback.message.answer("📌 Qazo sifatida belgilandi")
    elif action == "snooze":
        await callback.message.answer(
            "Qachon eslatay?",
            reply_markup=snooze_keyboard(current_user.language_code, daily_id),
        )
    else:
        await callback.answer("Noto'g'ri amal", show_alert=True)
        return

    await callback.answer()


@router.callback_query(F.data.startswith("snooze:"))
async def snooze_action(callback: CallbackQuery, current_user, session):
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer("Noto'g'ri amal", show_alert=True)
        return

    _, raw_minutes, raw_id = parts
    try:
        minutes = int(raw_minutes)
        daily_id = int(raw_id)
    except ValueError:
        await callback.answer("Noto'g'ri amal", show_alert=True)
        return

    daily_repo = DailyPrayersRepository(session)
    daily = await daily_repo.get_by_id(daily_id)
    if not daily or daily.user_id != current_user.id:
        await callback.answer("Bu amal sizga tegishli emas", show_alert=True)
        return

    await daily_repo.set_status(
        daily_id,
        "snoozed",
        snooze_until=datetime.now(timezone.utc) + timedelta(minutes=minutes),
    )
    await callback.message.answer("⏰ Eslatma keyinroq yuboriladi")
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def cancel_action(callback: CallbackQuery):
    await callback.message.answer("Bekor qilindi.")
    await callback.answer()
