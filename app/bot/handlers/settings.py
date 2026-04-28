from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.bot.keyboards.city import city_keyboard
from app.bot.keyboards.language import language_keyboard
from app.bot.keyboards.settings import settings_back_keyboard, settings_keyboard
from app.db.models import ReminderSetting, User
from app.db.repositories.states import StatesRepository
from app.services.i18n import t

router = Router(name="settings")


async def render_settings(user: User, session) -> str:
    lang = user.language_code or "uz"
    reminder = await session.scalar(select(ReminderSetting).where(ReminderSetting.user_id == user.id))
    prayer_enabled = reminder.prayer_reminders_enabled if reminder else True
    qazo_enabled = reminder.qazo_reminders_enabled if reminder else True
    qazo_times = ", ".join(reminder.qazo_reminder_times) if reminder else "08:00, 21:00"
    daily_limit = reminder.daily_qazo_limit if reminder else 1
    quiet_start = reminder.quiet_hours_start.strftime("%H:%M") if reminder else "23:00"
    quiet_end = reminder.quiet_hours_end.strftime("%H:%M") if reminder else "06:00"
    return "\n".join([
        t(lang, "settings.title"),
        "",
        t(lang, "settings.language", language=t(lang, f"language.{lang}")),
        t(lang, "settings.city", city=user.city or "-"),
        t(lang, "settings.timezone", timezone=user.timezone),
        "",
        t(lang, "settings.prayer_reminders", status=t(lang, "status.on" if prayer_enabled else "status.off")),
        t(lang, "settings.qazo_reminders", status=t(lang, "status.on" if qazo_enabled else "status.off")),
        t(lang, "settings.qazo_times", times=qazo_times),
        t(lang, "settings.qazo_daily_limit", count=daily_limit),
        t(lang, "settings.quiet_hours", start=quiet_start, end=quiet_end),
    ])


@router.message(Command("settings"))
@router.message(F.text.in_({"⚙️ Sozlamalar", "⚙️ Настройки", "⚙️ Settings"}))
async def settings_handler(message: Message, current_user: User, session):
    await StatesRepository(session).clear(current_user.id)
    await message.answer(await render_settings(current_user, session), reply_markup=settings_keyboard(current_user.language_code))


@router.callback_query(F.data == "settings:open")
async def settings_open(callback: CallbackQuery, current_user: User, session):
    await StatesRepository(session).clear(current_user.id)
    text = await render_settings(current_user, session)
    try:
        await callback.message.edit_text(text, reply_markup=settings_keyboard(current_user.language_code))
    except Exception:
        await callback.message.answer(text, reply_markup=settings_keyboard(current_user.language_code))
    await callback.answer()


@router.callback_query(F.data == "settings:language")
async def settings_language(callback: CallbackQuery, current_user: User, session):
    await StatesRepository(session).set(current_user.id, "settings_language", {})
    try:
        await callback.message.edit_text(t(current_user.language_code, "settings.language.choose"), reply_markup=language_keyboard())
    except Exception:
        await callback.message.answer(t(current_user.language_code, "settings.language.choose"), reply_markup=language_keyboard())
    await callback.answer()


@router.callback_query(F.data == "settings:city")
async def settings_city(callback: CallbackQuery, current_user: User, session):
    await StatesRepository(session).set(current_user.id, "settings_city", {})
    lang = current_user.language_code or "uz"
    text = t(lang, "settings.city.choose", city=current_user.city or "-")
    try:
        await callback.message.edit_text(text, reply_markup=city_keyboard(lang, back_callback="settings:open"))
    except Exception:
        await callback.message.answer(text, reply_markup=city_keyboard(lang, back_callback="settings:open"))
    await callback.answer()


@router.callback_query(F.data.startswith("settings:"))
async def settings_placeholder(callback: CallbackQuery, current_user: User):
    lang = current_user.language_code or "uz"
    await callback.answer()
    try:
        await callback.message.edit_text(t(lang, "settings.placeholder"), reply_markup=settings_back_keyboard(lang))
    except Exception:
        await callback.message.answer(t(lang, "settings.placeholder"), reply_markup=settings_back_keyboard(lang))
