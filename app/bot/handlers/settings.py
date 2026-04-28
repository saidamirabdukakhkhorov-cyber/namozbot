from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.bot.filters.text import text_is_one_of
from app.bot.keyboards.city import city_keyboard
from app.bot.keyboards.language import language_keyboard
from app.bot.keyboards.settings import settings_back_keyboard, settings_keyboard
from app.db.models import ReminderSetting, User
from app.db.repositories.states import StatesRepository
from app.services.i18n import t

router = Router(name="settings")


def _lang(user: User) -> str:
    return user.language_code or "uz"


async def get_or_create_reminder_setting(user: User, session) -> ReminderSetting:
    reminder = await session.scalar(select(ReminderSetting).where(ReminderSetting.user_id == user.id))
    if reminder:
        return reminder
    reminder = ReminderSetting(user_id=user.id)
    session.add(reminder)
    await session.flush()
    return reminder


async def render_settings(user: User, session) -> str:
    lang = _lang(user)
    reminder = await get_or_create_reminder_setting(user, session)
    qazo_times = ", ".join(reminder.qazo_reminder_times or ["08:00", "21:00"])
    quiet_start = reminder.quiet_hours_start.strftime("%H:%M") if reminder.quiet_hours_start else "23:00"
    quiet_end = reminder.quiet_hours_end.strftime("%H:%M") if reminder.quiet_hours_end else "06:00"
    return "\n".join([
        t(lang, "settings.title"),
        "",
        t(lang, "settings.language", language=t(lang, f"language.{lang}")),
        t(lang, "settings.city", city=user.city or "-"),
        t(lang, "settings.timezone", timezone=user.timezone),
        "",
        t(lang, "settings.prayer_reminders", status=t(lang, "status.on" if reminder.prayer_reminders_enabled else "status.off")),
        t(lang, "settings.qazo_reminders", status=t(lang, "status.on" if reminder.qazo_reminders_enabled else "status.off")),
        t(lang, "settings.qazo_times", times=qazo_times),
        t(lang, "settings.qazo_daily_limit", count=reminder.daily_qazo_limit),
        t(lang, "settings.quiet_hours", start=quiet_start, end=quiet_end),
    ])


async def open_settings_message(message: Message, current_user: User, session) -> None:
    await StatesRepository(session).clear(current_user.id)
    await message.answer(
        await render_settings(current_user, session),
        reply_markup=settings_keyboard(_lang(current_user)),
    )


async def edit_or_send_settings(callback: CallbackQuery, current_user: User, session, notice: str | None = None) -> None:
    lang = _lang(current_user)
    text = await render_settings(current_user, session)
    if notice:
        text = f"{notice}\n\n{text}"
    try:
        await callback.message.edit_text(text, reply_markup=settings_keyboard(lang))
    except Exception:
        await callback.message.answer(text, reply_markup=settings_keyboard(lang))


@router.message(Command("settings"))
@router.message(text_is_one_of(
    "⚙️ Sozlamalar", "⚙️ Настройки", "⚙️ Settings",
    "⚙ Sozlamalar", "⚙ Настройки", "⚙ Settings",
    "Sozlamalar", "Настройки", "Settings",
))
async def settings_handler(message: Message, current_user: User, session):
    await open_settings_message(message, current_user, session)


@router.callback_query(F.data == "settings:open")
async def settings_open(callback: CallbackQuery, current_user: User, session):
    await StatesRepository(session).clear(current_user.id)
    await edit_or_send_settings(callback, current_user, session)
    await callback.answer()


@router.callback_query(F.data == "settings:language")
async def settings_language(callback: CallbackQuery, current_user: User, session):
    await StatesRepository(session).set(current_user.id, "settings_language", {})
    lang = _lang(current_user)
    try:
        await callback.message.edit_text(t(lang, "settings.language.choose"), reply_markup=language_keyboard())
    except Exception:
        await callback.message.answer(t(lang, "settings.language.choose"), reply_markup=language_keyboard())
    await callback.answer()


@router.callback_query(F.data == "settings:city")
async def settings_city(callback: CallbackQuery, current_user: User, session):
    await StatesRepository(session).set(current_user.id, "settings_city", {})
    lang = _lang(current_user)
    text = t(lang, "settings.city.choose", city=current_user.city or "-")
    try:
        await callback.message.edit_text(text, reply_markup=city_keyboard(lang, back_callback="settings:open"))
    except Exception:
        await callback.message.answer(text, reply_markup=city_keyboard(lang, back_callback="settings:open"))
    await callback.answer()


@router.callback_query(F.data == "settings:prayer_reminders")
async def toggle_prayer_reminders(callback: CallbackQuery, current_user: User, session):
    reminder = await get_or_create_reminder_setting(current_user, session)
    reminder.prayer_reminders_enabled = not reminder.prayer_reminders_enabled
    lang = _lang(current_user)
    notice = t(lang, "settings.prayer_reminders.updated", status=t(lang, "status.on" if reminder.prayer_reminders_enabled else "status.off"))
    await edit_or_send_settings(callback, current_user, session, notice=notice)
    await callback.answer()


@router.callback_query(F.data == "settings:qazo_reminders")
async def toggle_qazo_reminders(callback: CallbackQuery, current_user: User, session):
    reminder = await get_or_create_reminder_setting(current_user, session)
    reminder.qazo_reminders_enabled = not reminder.qazo_reminders_enabled
    lang = _lang(current_user)
    notice = t(lang, "settings.qazo_reminders.updated", status=t(lang, "status.on" if reminder.qazo_reminders_enabled else "status.off"))
    await edit_or_send_settings(callback, current_user, session, notice=notice)
    await callback.answer()


@router.callback_query(F.data == "settings:qazo_times")
async def settings_qazo_times(callback: CallbackQuery, current_user: User, session):
    await StatesRepository(session).set(current_user.id, "settings_waiting_qazo_times", {})
    lang = _lang(current_user)
    try:
        await callback.message.edit_text(t(lang, "settings.qazo_times.prompt"), reply_markup=settings_back_keyboard(lang))
    except Exception:
        await callback.message.answer(t(lang, "settings.qazo_times.prompt"), reply_markup=settings_back_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "settings:quiet_hours")
async def settings_quiet_hours(callback: CallbackQuery, current_user: User, session):
    await StatesRepository(session).set(current_user.id, "settings_waiting_quiet_hours", {})
    lang = _lang(current_user)
    try:
        await callback.message.edit_text(t(lang, "settings.quiet_hours.prompt"), reply_markup=settings_back_keyboard(lang))
    except Exception:
        await callback.message.answer(t(lang, "settings.quiet_hours.prompt"), reply_markup=settings_back_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data.startswith("settings:"))
async def settings_unknown(callback: CallbackQuery, current_user: User, session):
    # Unknown settings callbacks should not dead-end the user.
    lang = _lang(current_user)
    await edit_or_send_settings(callback, current_user, session, notice=t(lang, "settings.unknown"))
    await callback.answer()
