from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.prayer import prayer_status_keyboard, snooze_keyboard
from app.db.repositories.daily_prayers import DailyPrayersRepository
from app.db.repositories.missed_prayers import MissedPrayersRepository
from app.services.i18n import prayer_label, t

router = Router(name="prayer")


def success_keyboard(language: str, *, qazo: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if qazo:
        rows.append([InlineKeyboardButton(text=t(language, "menu.qazo"), callback_data="qazo:overview")])
    rows.append([InlineKeyboardButton(text=t(language, "menu.today"), callback_data="today:open")])
    rows.append([InlineKeyboardButton(text=t(language, "common.home"), callback_data="dashboard")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("today:detail:"))
async def today_prayer_detail(callback: CallbackQuery, current_user, session):
    try:
        daily_id = int((callback.data or "").rsplit(":", 1)[1])
    except ValueError:
        await callback.answer(t(current_user.language_code, "error.invalid_action"), show_alert=True)
        return

    daily = await DailyPrayersRepository(session).get_by_id(daily_id)
    if not daily or daily.user_id != current_user.id:
        await callback.answer(t(current_user.language_code, "error.not_yours"), show_alert=True)
        return

    lang = current_user.language_code or "uz"
    time_text = daily.prayer_time.astimezone(ZoneInfo(current_user.timezone or "Asia/Tashkent")).strftime("%H:%M") if daily.prayer_time else "-"
    text = "\n".join([
        t(lang, "today.prayer_detail.title", prayer=prayer_label(lang, daily.prayer_name)),
        "",
        t(lang, "today.prayer_detail.time", time=time_text),
        t(lang, "today.prayer_detail.status", status=t(lang, "status." + daily.status)),
        "",
        t(lang, "today.prayer_detail.question"),
    ])
    try:
        await callback.message.edit_text(text, reply_markup=prayer_status_keyboard(lang, daily.id))
    except Exception:
        await callback.message.answer(text, reply_markup=prayer_status_keyboard(lang, daily.id))
    await callback.answer()


@router.callback_query(F.data.startswith("daily:"))
async def daily_action(callback: CallbackQuery, current_user, session):
    lang = current_user.language_code or "uz"
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer(t(lang, "error.invalid_action"), show_alert=True)
        return

    _, action, raw_id = parts
    try:
        daily_id = int(raw_id)
    except ValueError:
        await callback.answer(t(lang, "error.invalid_action"), show_alert=True)
        return

    daily_repo = DailyPrayersRepository(session)
    daily = await daily_repo.get_by_id(daily_id)
    if not daily or daily.user_id != current_user.id:
        await callback.answer(t(lang, "error.not_yours"), show_alert=True)
        return

    prayer = prayer_label(lang, daily.prayer_name)
    if action == "prayed":
        await daily_repo.set_status(daily_id, "prayed")
        text = t(lang, "today.success.prayed", prayer=prayer)
        keyboard = success_keyboard(lang)
    elif action == "missed":
        await daily_repo.set_status(daily_id, "missed")
        await MissedPrayersRepository(session).create(
            user_id=daily.user_id,
            prayer_name=daily.prayer_name,
            prayer_date=daily.prayer_date,
            source="daily_confirmation",
            daily_prayer_id=daily.id,
        )
        text = t(lang, "today.success.missed", prayer=prayer)
        keyboard = success_keyboard(lang, qazo=True)
    elif action == "snooze":
        text = t(lang, "today.snooze.title") + "\n\n" + t(lang, "today.snooze.question")
        keyboard = snooze_keyboard(lang, daily_id)
    else:
        await callback.answer(t(lang, "error.invalid_action"), show_alert=True)
        return

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("snooze:"))
async def snooze_action(callback: CallbackQuery, current_user, session):
    lang = current_user.language_code or "uz"
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer(t(lang, "error.invalid_action"), show_alert=True)
        return

    _, raw_minutes, raw_id = parts
    try:
        minutes = int(raw_minutes)
        daily_id = int(raw_id)
    except ValueError:
        await callback.answer(t(lang, "error.invalid_action"), show_alert=True)
        return

    daily_repo = DailyPrayersRepository(session)
    daily = await daily_repo.get_by_id(daily_id)
    if not daily or daily.user_id != current_user.id:
        await callback.answer(t(lang, "error.not_yours"), show_alert=True)
        return

    await daily_repo.set_status(
        daily_id,
        "snoozed",
        snooze_until=datetime.now(timezone.utc) + timedelta(minutes=minutes),
    )
    text = t(lang, "today.success.snoozed", minutes=minutes)
    try:
        await callback.message.edit_text(text, reply_markup=success_keyboard(lang))
    except Exception:
        await callback.message.answer(text, reply_markup=success_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def cancel_action(callback: CallbackQuery, current_user, session):
    from app.bot.handlers.dashboard import build_dashboard, dashboard_keyboard
    from app.db.repositories.states import StatesRepository

    await StatesRepository(session).clear(current_user.id)
    lang = current_user.language_code or "uz"
    try:
        await callback.message.edit_text(await build_dashboard(current_user, session), reply_markup=dashboard_keyboard(lang))
    except Exception:
        await callback.message.answer(t(lang, "common.cancelled"))
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()
