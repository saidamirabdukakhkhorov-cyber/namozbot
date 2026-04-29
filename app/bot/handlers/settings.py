from __future__ import annotations

from collections.abc import Awaitable, Callable
import asyncio
from datetime import time
from typing import Any, TypeVar

from aiogram import F, Router
from aiogram.filters import BaseFilter, Command
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
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

SUPPORTED_LANGUAGES = {"uz", "ru", "en"}
DEFAULT_QAZO_TIMES = ["08:00", "21:00"]
DEFAULT_QUIET_HOURS = (time(23, 0), time(6, 0))
MIN_DAILY_LIMIT = 1
MAX_DAILY_LIMIT = 10

SETTINGS_INPUT_CITY = "settings_input_city"
SETTINGS_INPUT_QAZO_TIMES = "settings_input_qazo_times"
SETTINGS_INPUT_DAILY_LIMIT = "settings_input_daily_limit"
SETTINGS_INPUT_QUIET_HOURS = "settings_input_quiet_hours"
SETTINGS_INPUT_STATES = {
    SETTINGS_INPUT_CITY,
    SETTINGS_INPUT_QAZO_TIMES,
    SETTINGS_INPUT_DAILY_LIMIT,
    SETTINGS_INPUT_QUIET_HOURS,
}

T = TypeVar("T")


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

    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise ValueError("time must contain numbers") from exc

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("time is out of range")
    return time(hour=hour, minute=minute)


def parse_time_list(value: str) -> list[str]:
    items = value.replace(";", ",").replace("\n", ",").split(",")
    times = [parse_hhmm(item).strftime("%H:%M") for item in items if item.strip()]
    if not times:
        raise ValueError("empty time list")
    return list(dict.fromkeys(times))


def parse_quiet_hours(value: str) -> tuple[time, time]:
    normalized = value.strip().replace("—", "-").replace("–", "-")
    if "-" not in normalized:
        raise ValueError("quiet hours separator is missing")
    start_raw, end_raw = [part.strip() for part in normalized.split("-", 1)]
    return parse_hhmm(start_raw), parse_hhmm(end_raw)


def parse_daily_limit(value: str) -> int:
    try:
        count = int(value.strip())
    except ValueError as exc:
        raise ValueError("daily limit must be a number") from exc
    if not (MIN_DAILY_LIMIT <= count <= MAX_DAILY_LIMIT):
        raise ValueError("daily limit is out of range")
    return count


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
        qazo_reminder_times=DEFAULT_QAZO_TIMES.copy(),
        daily_qazo_limit=MIN_DAILY_LIMIT,
        quiet_hours_enabled=True,
        quiet_hours_start=DEFAULT_QUIET_HOURS[0],
        quiet_hours_end=DEFAULT_QUIET_HOURS[1],
    )
    session.add(reminder)
    await session.flush()
    await session.refresh(reminder)
    return reminder


async def render_settings(user: User, session, *, notice: str | None = None) -> str:
    lang = _lang(user)
    reminder = await get_or_create_reminder_setting(user, session)
    qazo_times = ", ".join(reminder.qazo_reminder_times or DEFAULT_QAZO_TIMES)
    quiet_start = _fmt_time(reminder.quiet_hours_start, "23:00")
    quiet_end = _fmt_time(reminder.quiet_hours_end, "06:00")

    body = "\n".join([
        t(lang, "settings.title"),
        "",
        t(lang, "settings.language", language=t(lang, f"language.{lang}")),
        t(lang, "settings.city", city=user.city or "-"),
        t(lang, "settings.timezone", timezone=user.timezone or "Asia/Tashkent"),
        "",
        t(lang, "settings.prayer_reminders", status=_status(lang, reminder.prayer_reminders_enabled)),
        t(lang, "settings.qazo_reminders", status=_status(lang, reminder.qazo_reminders_enabled)),
        t(lang, "settings.qazo_times", times=qazo_times),
        t(lang, "settings.qazo_daily_limit", count=reminder.daily_qazo_limit or MIN_DAILY_LIMIT),
        t(lang, "settings.quiet_hours", start=quiet_start, end=quiet_end),
    ])
    return f"{notice}\n\n{body}" if notice else body


async def _edit_or_answer(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    if not callback.message:
        return

    # Settings can be opened from a normal text message or from a media/caption
    # message. edit_text fails for media messages, so use edit_caption there.
    try:
        if getattr(callback.message, "text", None) is not None:
            await callback.message.edit_text(text, reply_markup=reply_markup)
        elif getattr(callback.message, "caption", None) is not None:
            await callback.message.edit_caption(caption=text, reply_markup=reply_markup)
        else:
            await callback.message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        await callback.message.answer(text, reply_markup=reply_markup)


async def refresh_reply_main_menu(message: Message | None, language: str, is_admin: bool) -> None:
    """Force Telegram to replace the cached Reply Keyboard after language change."""
    if not message:
        return
    await message.answer(t(language, "settings.language.updated"), reply_markup=ReplyKeyboardRemove())
    await asyncio.sleep(0.15)
    await message.answer(t(language, "menu.home"), reply_markup=main_menu_keyboard(language, is_admin))


async def _open_settings_message(message: Message, current_user: User, session, *, notice: str | None = None) -> None:
    await StatesRepository(session).clear(current_user.id)
    lang = _lang(current_user)
    await message.answer(
        await render_settings(current_user, session, notice=notice),
        reply_markup=settings_keyboard(lang),
    )


async def _open_settings_callback(callback: CallbackQuery, current_user: User, session, *, notice: str | None = None) -> None:
    await StatesRepository(session).clear(current_user.id)
    lang = _lang(current_user)
    await _edit_or_answer(
        callback,
        await render_settings(current_user, session, notice=notice),
        settings_keyboard(lang),
    )


async def _show_callback_screen(
    callback: CallbackQuery,
    current_user: User,
    session,
    text: str,
    reply_markup=None,
    *,
    clear_state: bool = True,
) -> None:
    if clear_state:
        await StatesRepository(session).clear(current_user.id)
    await _edit_or_answer(callback, text, reply_markup)


async def _ask_for_text_input(callback: CallbackQuery, current_user: User, session, state: str, prompt_key: str) -> None:
    await StatesRepository(session).set(current_user.id, state, {})
    lang = _lang(current_user)
    await _edit_or_answer(callback, t(lang, prompt_key), settings_back_keyboard(lang))


async def _update_reminder_and_open(
    callback: CallbackQuery,
    current_user: User,
    session,
    update: Callable[[ReminderSetting], None],
    notice_factory: Callable[[str, ReminderSetting], str],
) -> None:
    reminder = await get_or_create_reminder_setting(current_user, session)
    update(reminder)
    lang = _lang(current_user)
    await _open_settings_callback(callback, current_user, session, notice=notice_factory(lang, reminder))


async def _save_text_input(
    message: Message,
    current_user: User,
    session,
    notice: str,
) -> None:
    await StatesRepository(session).clear(current_user.id)
    await _open_settings_message(message, current_user, session, notice=notice)


@router.message(Command("settings"))
async def settings_menu_message(message: Message, current_user: User, session):
    await _open_settings_message(message, current_user, session)


@router.callback_query(F.data == "settings:open")
@router.callback_query(F.data == "settings:cancel")
async def settings_open(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    await _open_settings_callback(callback, current_user, session)


@router.callback_query(F.data == "settings:language")
async def settings_language(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    lang = _lang(current_user)
    await _show_callback_screen(
        callback,
        current_user,
        session,
        t(lang, "settings.language.choose"),
        settings_language_keyboard(lang),
    )


@router.callback_query(F.data.startswith("settings:set_language:"))
async def settings_set_language(callback: CallbackQuery, current_user: User, session, is_admin: bool):
    await callback.answer()
    language = (callback.data or "").rsplit(":", 1)[-1]
    if language not in SUPPORTED_LANGUAGES:
        language = "uz"

    await UsersRepository(session).set_language(current_user.id, language)
    current_user.language_code = language

    # Telegram clients cache persistent Reply Keyboards. The settings message
    # can be edited in the new language, but the bottom menu remains in the
    # previous language unless it is explicitly removed and sent again.
    await _open_settings_callback(
        callback,
        current_user,
        session,
        notice=t(language, "settings.language.updated"),
    )
    await refresh_reply_main_menu(callback.message, language, is_admin)


@router.callback_query(F.data == "settings:city")
async def settings_city(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    lang = _lang(current_user)
    await _show_callback_screen(
        callback,
        current_user,
        session,
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
    await _open_settings_callback(
        callback,
        current_user,
        session,
        notice=t(lang, "settings.city.updated", city=city),
    )


@router.callback_query(F.data == "settings:city_custom")
async def settings_city_custom(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    await _ask_for_text_input(callback, current_user, session, SETTINGS_INPUT_CITY, "settings.city.custom_prompt")


@router.callback_query(F.data == "settings:prayer_reminders")
async def settings_toggle_prayer_reminders(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    await _update_reminder_and_open(
        callback,
        current_user,
        session,
        lambda reminder: setattr(reminder, "prayer_reminders_enabled", not reminder.prayer_reminders_enabled),
        lambda lang, reminder: t(
            lang,
            "settings.prayer_reminders.updated",
            status=_status(lang, reminder.prayer_reminders_enabled),
        ),
    )


@router.callback_query(F.data == "settings:qazo_reminders")
async def settings_toggle_qazo_reminders(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    await _update_reminder_and_open(
        callback,
        current_user,
        session,
        lambda reminder: setattr(reminder, "qazo_reminders_enabled", not reminder.qazo_reminders_enabled),
        lambda lang, reminder: t(
            lang,
            "settings.qazo_reminders.updated",
            status=_status(lang, reminder.qazo_reminders_enabled),
        ),
    )


@router.callback_query(F.data == "settings:qazo_times")
async def settings_qazo_times(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    await _ask_for_text_input(callback, current_user, session, SETTINGS_INPUT_QAZO_TIMES, "settings.qazo_times.prompt")


@router.callback_query(F.data == "settings:daily_limit")
async def settings_daily_limit(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    lang = _lang(current_user)
    await _show_callback_screen(
        callback,
        current_user,
        session,
        t(lang, "settings.daily_limit.choose"),
        settings_daily_limit_keyboard(lang),
    )


@router.callback_query(F.data.startswith("settings:set_daily_limit:"))
async def settings_set_daily_limit(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    lang = _lang(current_user)
    try:
        count = parse_daily_limit((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        await _edit_or_answer(callback, t(lang, "settings.daily_limit.invalid"), settings_back_keyboard(lang))
        return

    await _update_reminder_and_open(
        callback,
        current_user,
        session,
        lambda reminder: setattr(reminder, "daily_qazo_limit", count),
        lambda lang, _reminder: t(lang, "settings.daily_limit.updated", count=count),
    )


@router.callback_query(F.data == "settings:daily_limit_custom")
async def settings_daily_limit_custom(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    await _ask_for_text_input(callback, current_user, session, SETTINGS_INPUT_DAILY_LIMIT, "settings.daily_limit.prompt")


@router.callback_query(F.data == "settings:quiet_hours")
async def settings_quiet_hours(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    await _ask_for_text_input(callback, current_user, session, SETTINGS_INPUT_QUIET_HOURS, "settings.quiet_hours.prompt")


@router.callback_query(F.data == "settings:privacy")
async def settings_privacy(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    lang = _lang(current_user)
    await _show_callback_screen(callback, current_user, session, t(lang, "privacy.text"), settings_back_keyboard(lang))


@router.message(SettingsInputStateFilter(*SETTINGS_INPUT_STATES))
async def settings_text_input(message: Message, current_user: User, session, settings_state, is_admin: bool):
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

    if settings_state.state == SETTINGS_INPUT_CITY:
        city = text[:120].strip()
        if not city:
            await message.answer(t(lang, "settings.city.invalid"), reply_markup=settings_back_keyboard(lang))
            return
        await UsersRepository(session).set_city(current_user.id, city)
        current_user.city = city
        await _save_text_input(message, current_user, session, t(lang, "settings.city.updated", city=city))
        return

    if settings_state.state == SETTINGS_INPUT_QAZO_TIMES:
        try:
            times = parse_time_list(text)
        except ValueError:
            await message.answer(t(lang, "settings.qazo_times.invalid"), reply_markup=settings_back_keyboard(lang))
            return
        reminder = await get_or_create_reminder_setting(current_user, session)
        reminder.qazo_reminder_times = times
        await _save_text_input(
            message,
            current_user,
            session,
            t(lang, "settings.qazo_times.updated", times=", ".join(times)),
        )
        return

    if settings_state.state == SETTINGS_INPUT_DAILY_LIMIT:
        try:
            count = parse_daily_limit(text)
        except ValueError:
            await message.answer(t(lang, "settings.daily_limit.invalid"), reply_markup=settings_back_keyboard(lang))
            return
        reminder = await get_or_create_reminder_setting(current_user, session)
        reminder.daily_qazo_limit = count
        await _save_text_input(message, current_user, session, t(lang, "settings.daily_limit.updated", count=count))
        return

    if settings_state.state == SETTINGS_INPUT_QUIET_HOURS:
        try:
            start, end = parse_quiet_hours(text)
        except ValueError:
            await message.answer(t(lang, "settings.quiet_hours.invalid"), reply_markup=settings_back_keyboard(lang))
            return
        reminder = await get_or_create_reminder_setting(current_user, session)
        reminder.quiet_hours_enabled = True
        reminder.quiet_hours_start = start
        reminder.quiet_hours_end = end
        await _save_text_input(
            message,
            current_user,
            session,
            t(lang, "settings.quiet_hours.updated", start=start.strftime("%H:%M"), end=end.strftime("%H:%M")),
        )
        return


@router.callback_query(F.data.startswith("settings:"))
async def settings_unknown(callback: CallbackQuery, current_user: User, session):
    await callback.answer()
    lang = _lang(current_user)
    await _open_settings_callback(callback, current_user, session, notice=t(lang, "settings.unknown"))
