from __future__ import annotations

from datetime import time
from typing import Any

from aiogram import F, Router
from aiogram.filters import BaseFilter, Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.bot.filters.text import detect_global_menu_action
from app.bot.keyboards.main import main_menu_keyboard
from app.bot.keyboards.settings import (
    settings_back_keyboard,
    settings_city_keyboard,
    settings_daily_limit_keyboard,
    settings_keyboard,
    settings_language_keyboard,
)
from app.db.models import ReminderSetting, User
from app.db.repositories.states import StatesRepository
from app.db.repositories.users import UsersRepository
from app.services.i18n import t

router = Router(name="settings")

SETTINGS_INPUT_STATES = {
    "settings_input_city",
    "settings_input_qazo_times",
    "settings_input_daily_limit",
    "settings_input_quiet_hours",
}

SUPPORTED_LANGUAGES = {"uz", "ru", "en"}


def _lang(user: User | None) -> str:
    if user and user.language_code in SUPPORTED_LANGUAGES:
        return user.language_code
    return "uz"


def _status(lang: str, enabled: bool) -> str:
    return t(lang, "status.on" if enabled else "status.off")


def _fmt_time(value: time | None, fallback: str) -> str:
    return value.strftime("%H:%M") if value else fallback


def parse_hhmm(value: str) -> time:
    raw = value.strip()
    parts = raw.split(":")
    if len(parts) != 2:
        raise ValueError("time must be HH:MM")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("time is out of range")
    return time(hour=hour, minute=minute)


def parse_time_list(value: str) -> list[str]:
    items = value.replace(";", ",").replace("\n", ",").split(",")
    result: list[str] = []
    for item in items:
        item = item.strip()
        if not item:
            continue
        result.append(parse_hhmm(item).strftime("%H:%M"))
    if not result:
        raise ValueError("empty time list")
    return list(dict.fromkeys(result))


def parse_quiet_hours(value: str) -> tuple[time, time]:
    normalized = value.strip().replace("—", "-").replace("–", "-")
    if "-" not in normalized:
        raise ValueError("quiet hours separator is missing")
    start_raw, end_raw = [part.strip() for part in normalized.split("-", 1)]
    return parse_hhmm(start_raw), parse_hhmm(end_raw)


class SettingsInputStateFilter(BaseFilter):
    def __init__(self, *states: str) -> None:
        self.states = set(states)

    async def __call__(self, message: Message, current_user: User | None, session) -> dict[str, Any] | bool:
        if not current_user:
            return False
        state = await StatesRepository(session).get(current_user.id)
        if state and state.state in self.states:
            return {"settings_state": state}
        return False


async def get_or_create_reminder_setting(user: User, session) -> ReminderSetting:
    reminder = await session.scalar(select(ReminderSetting).where(ReminderSetting.user_id == user.id))
    if reminder:
        return reminder
    reminder = ReminderSetting(
        user_id=user.id,
        prayer_reminders_enabled=True,
        qazo_reminders_enabled=True,
        qazo_reminder_times=["08:00", "21:00"],
        daily_qazo_limit=1,
        quiet_hours_enabled=True,
        quiet_hours_start=time(23, 0),
        quiet_hours_end=time(6, 0),
    )
    session.add(reminder)
    await session.flush()
    await session.refresh(reminder)
    return reminder


async def render_settings(user: User, session, *, notice: str | None = None) -> str:
    lang = _lang(user)
    reminder = await get_or_create_reminder_setting(user, session)
    qazo_times = ", ".join(reminder.qazo_reminder_times or ["08:00", "21:00"])
    quiet_start = _fmt_time(reminder.quiet_hours_start, "23:00")
    quiet_end = _fmt_time(reminder.quiet_hours_end, "06:00")

    lines = [
        t(lang, "settings.title"),
        "",
        t(lang, "settings.language", language=t(lang, f"language.{lang}")),
        t(lang, "settings.city", city=user.city or "-"),
        t(lang, "settings.timezone", timezone=user.timezone or "Asia/Tashkent"),
        "",
        t(lang, "settings.prayer_reminders", status=_status(lang, reminder.prayer_reminders_enabled)),
        t(lang, "settings.qazo_reminders", status=_status(lang, reminder.qazo_reminders_enabled)),
        t(lang, "settings.qazo_times", times=qazo_times),
        t(lang, "settings.qazo_daily_limit", count=reminder.daily_qazo_limit or 1),
        t(lang, "settings.quiet_hours", start=quiet_start, end=quiet_end),
    ]
    body = "\n".join(lines)
    return f"{notice}\n\n{body}" if notice else body


async def _open_settings_from_message(message: Message, current_user: User, session) -> None:
    await StatesRepository(session).clear(current_user.id)
    lang = _lang(current_user)
    await message.answer(
        await render_settings(current_user, session),
        reply_markup=settings_keyboard(lang),
    )


async def _edit_or_answer(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    if callback.message:
        try:
            await callback.message.edit_text(text, reply_markup=reply_markup)
            return
        except Exception:
            await callback.message.answer(text, reply_markup=reply_markup)


async def _open_settings_from_callback(callback: CallbackQuery, current_user: User, session, *, notice: str | None = None) -> None:
    await StatesRepository(session).clear(current_user.id)
    lang = _lang(current_user)
    await _edit_or_answer(
        callback,
        await render_settings(current_user, session, notice=notice),
        settings_keyboard(lang),
    )


@router.message(Command("settings"))
async def settings_menu_message(message: Message, current_user: User, session):
    await _open_settings_from_message(message, current_user, session)


@router.callback_query(F.data == "settings:open")
@router.callback_query(F.data == "settings:cancel")
async def settings_open(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    await _open_settings_from_callback(callback, current_user, session)


@router.callback_query(F.data == "settings:language")
async def settings_language(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    await StatesRepository(session).clear(current_user.id)
    lang = _lang(current_user)
    await _edit_or_answer(callback, t(lang, "settings.language.choose"), settings_language_keyboard(lang))


@router.callback_query(F.data.startswith("settings:set_language:"))
async def settings_set_language(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    language = (callback.data or "").rsplit(":", 1)[-1]
    if language not in SUPPORTED_LANGUAGES:
        language = "uz"
    await UsersRepository(session).set_language(current_user.id, language)
    current_user.language_code = language
    await callback.answer()
    await _open_settings_from_callback(
        callback,
        current_user,
        session,
        notice=t(language, "settings.language.updated"),
    )


@router.callback_query(F.data == "settings:city")
async def settings_city(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    await StatesRepository(session).clear(current_user.id)
    lang = _lang(current_user)
    await _edit_or_answer(
        callback,
        t(lang, "settings.city.choose", city=current_user.city or "-"),
        settings_city_keyboard(lang),
    )


@router.callback_query(F.data.startswith("settings:set_city:"))
async def settings_set_city(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    city = (callback.data or "").split(":", 2)[2].strip()
    lang = _lang(current_user)
    if not city:
        await _edit_or_answer(callback, t(lang, "settings.city.invalid"), settings_back_keyboard(lang))
        return
    await UsersRepository(session).set_city(current_user.id, city)
    current_user.city = city
    await _open_settings_from_callback(
        callback,
        current_user,
        session,
        notice=t(lang, "settings.city.updated", city=city),
    )


@router.callback_query(F.data == "settings:city_custom")
async def settings_city_custom(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    await StatesRepository(session).set(current_user.id, "settings_input_city", {})
    lang = _lang(current_user)
    await _edit_or_answer(callback, t(lang, "settings.city.custom_prompt"), settings_back_keyboard(lang))


@router.callback_query(F.data == "settings:prayer_reminders")
async def settings_toggle_prayer_reminders(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    reminder = await get_or_create_reminder_setting(current_user, session)
    reminder.prayer_reminders_enabled = not reminder.prayer_reminders_enabled
    lang = _lang(current_user)
    await _open_settings_from_callback(
        callback,
        current_user,
        session,
        notice=t(lang, "settings.prayer_reminders.updated", status=_status(lang, reminder.prayer_reminders_enabled)),
    )


@router.callback_query(F.data == "settings:qazo_reminders")
async def settings_toggle_qazo_reminders(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    reminder = await get_or_create_reminder_setting(current_user, session)
    reminder.qazo_reminders_enabled = not reminder.qazo_reminders_enabled
    lang = _lang(current_user)
    await _open_settings_from_callback(
        callback,
        current_user,
        session,
        notice=t(lang, "settings.qazo_reminders.updated", status=_status(lang, reminder.qazo_reminders_enabled)),
    )


@router.callback_query(F.data == "settings:qazo_times")
async def settings_qazo_times(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    await StatesRepository(session).set(current_user.id, "settings_input_qazo_times", {})
    lang = _lang(current_user)
    await _edit_or_answer(callback, t(lang, "settings.qazo_times.prompt"), settings_back_keyboard(lang))


@router.callback_query(F.data == "settings:daily_limit")
async def settings_daily_limit(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    await StatesRepository(session).clear(current_user.id)
    lang = _lang(current_user)
    await _edit_or_answer(callback, t(lang, "settings.daily_limit.choose"), settings_daily_limit_keyboard(lang))


@router.callback_query(F.data.startswith("settings:set_daily_limit:"))
async def settings_set_daily_limit(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    lang = _lang(current_user)
    try:
        count = int((callback.data or "").rsplit(":", 1)[-1])
        if count < 1 or count > 10:
            raise ValueError
    except ValueError:
        await _edit_or_answer(callback, t(lang, "settings.daily_limit.invalid"), settings_back_keyboard(lang))
        return
    reminder = await get_or_create_reminder_setting(current_user, session)
    reminder.daily_qazo_limit = count
    await _open_settings_from_callback(
        callback,
        current_user,
        session,
        notice=t(lang, "settings.daily_limit.updated", count=count),
    )


@router.callback_query(F.data == "settings:daily_limit_custom")
async def settings_daily_limit_custom(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    await StatesRepository(session).set(current_user.id, "settings_input_daily_limit", {})
    lang = _lang(current_user)
    await _edit_or_answer(callback, t(lang, "settings.daily_limit.prompt"), settings_back_keyboard(lang))


@router.callback_query(F.data == "settings:quiet_hours")
async def settings_quiet_hours(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    await StatesRepository(session).set(current_user.id, "settings_input_quiet_hours", {})
    lang = _lang(current_user)
    await _edit_or_answer(callback, t(lang, "settings.quiet_hours.prompt"), settings_back_keyboard(lang))


@router.callback_query(F.data == "settings:privacy")
async def settings_privacy(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    await StatesRepository(session).clear(current_user.id)
    lang = _lang(current_user)
    await _edit_or_answer(callback, t(lang, "privacy.text"), settings_back_keyboard(lang))


@router.message(SettingsInputStateFilter(*SETTINGS_INPUT_STATES))
async def settings_text_input(message: Message, current_user: User, session, settings_state, is_admin: bool):
    # If the user taps a global Reply Keyboard button while a settings input is
    # active, do not treat it as raw input. Let global navigation handle it if it
    # was not already handled by the earlier router.
    action = detect_global_menu_action(message.text)
    if action:
        from app.bot.handlers.global_navigation import send_global_menu_screen

        await send_global_menu_screen(
            message=message,
            action=action,
            current_user=current_user,
            session=session,
            is_admin=is_admin,
        )
        return

    lang = _lang(current_user)
    text = (message.text or "").strip()

    if settings_state.state == "settings_input_city":
        city = text[:120].strip()
        if not city:
            await message.answer(t(lang, "settings.city.invalid"), reply_markup=settings_back_keyboard(lang))
            return
        await UsersRepository(session).set_city(current_user.id, city)
        current_user.city = city
        await StatesRepository(session).clear(current_user.id)
        await message.answer(
            await render_settings(current_user, session, notice=t(lang, "settings.city.updated", city=city)),
            reply_markup=settings_keyboard(lang),
        )
        return

    if settings_state.state == "settings_input_qazo_times":
        try:
            times = parse_time_list(text)
        except ValueError:
            await message.answer(t(lang, "settings.qazo_times.invalid"), reply_markup=settings_back_keyboard(lang))
            return
        reminder = await get_or_create_reminder_setting(current_user, session)
        reminder.qazo_reminder_times = times
        await StatesRepository(session).clear(current_user.id)
        await message.answer(
            await render_settings(current_user, session, notice=t(lang, "settings.qazo_times.updated", times=", ".join(times))),
            reply_markup=settings_keyboard(lang),
        )
        return

    if settings_state.state == "settings_input_daily_limit":
        try:
            count = int(text)
            if count < 1 or count > 10:
                raise ValueError
        except ValueError:
            await message.answer(t(lang, "settings.daily_limit.invalid"), reply_markup=settings_back_keyboard(lang))
            return
        reminder = await get_or_create_reminder_setting(current_user, session)
        reminder.daily_qazo_limit = count
        await StatesRepository(session).clear(current_user.id)
        await message.answer(
            await render_settings(current_user, session, notice=t(lang, "settings.daily_limit.updated", count=count)),
            reply_markup=settings_keyboard(lang),
        )
        return

    if settings_state.state == "settings_input_quiet_hours":
        try:
            start, end = parse_quiet_hours(text)
        except ValueError:
            await message.answer(t(lang, "settings.quiet_hours.invalid"), reply_markup=settings_back_keyboard(lang))
            return
        reminder = await get_or_create_reminder_setting(current_user, session)
        reminder.quiet_hours_enabled = True
        reminder.quiet_hours_start = start
        reminder.quiet_hours_end = end
        await StatesRepository(session).clear(current_user.id)
        await message.answer(
            await render_settings(
                current_user,
                session,
                notice=t(lang, "settings.quiet_hours.updated", start=start.strftime("%H:%M"), end=end.strftime("%H:%M")),
            ),
            reply_markup=settings_keyboard(lang),
        )
        return


@router.callback_query(F.data.startswith("settings:"))
async def settings_unknown(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    lang = _lang(current_user)
    await _open_settings_from_callback(callback, current_user, session, notice=t(lang, "settings.unknown"))
