from __future__ import annotations

import calendar
from datetime import date

from aiogram import Router
from aiogram.types import Message

from app.bot.filters.text import detect_global_menu_action
from app.bot.handlers.global_navigation import send_global_menu_screen
from app.bot.handlers.qazo import render_qazo_overview, source_label, source_values
from app.bot.handlers.qazo_calculator import handle_calc2_year_input
from app.bot.handlers.settings import get_or_create_reminder_setting, render_settings
from app.bot.keyboards.language import onboarding_reminder_keyboard
from app.bot.keyboards.main import main_menu_keyboard
from app.bot.keyboards.prayer import prayer_select_keyboard
from app.bot.keyboards.qazo import qazo_complete_success_keyboard, qazo_overview_keyboard
from app.bot.keyboards.settings import settings_keyboard
from app.db.repositories.missed_prayers import MissedPrayersRepository
from app.db.repositories.states import StatesRepository
from app.db.repositories.users import UsersRepository
# FIX: import shared parsing utils instead of duplicating parse_hhmm
from app.services.parsing import parse_hhmm, parse_time_list, parse_quiet_hours
from app.services.timezone import tashkent_today
from app.services.i18n import prayer_label, t

router = Router(name="state_text")


def parse_yyyy_mm(value: str) -> tuple[int, int]:
    parts = value.split("-")
    if len(parts) != 2:
        raise ValueError
    year, month = int(parts[0]), int(parts[1])
    if year < 1900 or month < 1 or month > 12:
        raise ValueError
    return year, month


def parse_year(value: str) -> int:
    if not value.isdigit() or len(value) != 4:
        raise ValueError
    year = int(value)
    if year < 1900:
        raise ValueError
    return year


@router.message()
async def state_text_handler(message: Message, current_user, session, is_admin: bool):
    if current_user is None:
        return

    action = detect_global_menu_action(message.text)
    if action:
        await send_global_menu_screen(
            message=message,
            action=action,
            current_user=current_user,
            session=session,
            is_admin=is_admin,
        )
        return

    state = await StatesRepository(session).get(current_user.id)
    if not state:
        return
    lang = current_user.language_code or "uz"
    text = (message.text or "").strip()

    if state.state == "settings_waiting_qazo_times":
        try:
            times = parse_time_list(text)
        except ValueError:
            await message.answer(t(lang, "settings.qazo_times.invalid"))
            return
        reminder = await get_or_create_reminder_setting(current_user, session)
        reminder.qazo_reminder_times = times
        await StatesRepository(session).clear(current_user.id)
        await message.answer(
            t(lang, "settings.qazo_times.updated", times=", ".join(times))
            + "\n\n"
            + await render_settings(current_user, session),
            reply_markup=settings_keyboard(lang),
        )
        return

    if state.state == "settings_waiting_quiet_hours":
        try:
            start, end = parse_quiet_hours(text)
        except ValueError:
            await message.answer(t(lang, "settings.quiet_hours.invalid"))
            return
        reminder = await get_or_create_reminder_setting(current_user, session)
        reminder.quiet_hours_enabled = True
        reminder.quiet_hours_start = start
        reminder.quiet_hours_end = end
        await StatesRepository(session).clear(current_user.id)
        await message.answer(
            t(lang, "settings.quiet_hours.updated", start=start.strftime("%H:%M"), end=end.strftime("%H:%M"))
            + "\n\n"
            + await render_settings(current_user, session),
            reply_markup=settings_keyboard(lang),
        )
        return

    if state.state == "waiting_custom_city":
        city = text[:120].strip()
        if not city:
            await message.answer(t(lang, "city.custom_prompt"))
            return

        source = (state.payload or {}).get("source", "onboarding")
        await UsersRepository(session).set_city(current_user.id, city)

        if source == "settings":
            await StatesRepository(session).clear(current_user.id)
            await message.answer(
                t(lang, "settings.city.updated", city=city),
                reply_markup=main_menu_keyboard(lang, is_admin),
            )
        else:
            await StatesRepository(session).set(current_user.id, "onboarding_reminders", {"city": city})
            await message.answer(t(lang, "onboarding.reminders"), reply_markup=onboarding_reminder_keyboard(lang))
        return

    if state.state == "waiting_qazo_period_start":
        try:
            start = date.fromisoformat(text)
        except ValueError:
            await message.answer(t(lang, "error.wrong_date"))
            return
        await StatesRepository(session).set(current_user.id, "waiting_qazo_period_end", {"start": start.isoformat()})
        await message.answer(t(lang, "qazo.period.custom_end"))
        return

    if state.state == "waiting_qazo_period_end":
        payload = state.payload or {}
        # FIX: was payload["start"] — KeyError if state was lost; use .get() with graceful fallback
        start_str = payload.get("start")
        if not start_str:
            await StatesRepository(session).set(current_user.id, "waiting_qazo_period_start", {})
            await message.answer(t(lang, "qazo.period.custom_start"))
            return
        start = date.fromisoformat(start_str)
        try:
            end = date.fromisoformat(text)
        except ValueError:
            await message.answer(t(lang, "error.wrong_date"))
            return
        if end < start:
            await message.answer(t(lang, "error.end_before_start"))
            return
        await StatesRepository(session).clear(current_user.id)
        qazo_text, empty = await render_qazo_overview(current_user, session, start=start, end=end, label=f"{start} — {end}")
        await message.answer(qazo_text, reply_markup=qazo_overview_keyboard(lang, empty=empty))
        return

    if state.state == "waiting_qazo_add_date":
        try:
            day = date.fromisoformat(text)
        except ValueError:
            await message.answer(t(lang, "error.wrong_date"))
            return
        if day > tashkent_today():
            await message.answer(t(lang, "error.future_date"))
            return
        await StatesRepository(session).set(current_user.id, "qazo_add_prayer", {"date": day.isoformat()})
        await message.answer(t(lang, "qazo.add.prayer_screen", date=day.isoformat()), reply_markup=prayer_select_keyboard(lang, "qazo_add_prayer"))
        return

    if state.state == "waiting_qazo_complete_count":
        try:
            count = int(text)
            if count <= 0:
                raise ValueError
        except ValueError:
            await message.answer(t(lang, "error.number_required"))
            return
        # FIX: safe .get() on payload keys
        source_key = (state.payload or {}).get("source_key")
        prayer = (state.payload or {}).get("prayer")
        if not source_key or not prayer:
            await StatesRepository(session).clear(current_user.id)
            await message.answer(t(lang, "error.invalid_action"))
            return
        max_count = await MissedPrayersRepository(session).count_by_prayer(
            current_user.id,
            prayer,
            source_values(source_key),
        )
        if count > max_count:
            await message.answer(t(lang, "error.count_too_large", prayer=prayer_label(lang, prayer), max=max_count))
            return
        action = await MissedPrayersRepository(session).complete_oldest(
            current_user.id,
            prayer,
            count,
            source_values(source_key),
        )
        await StatesRepository(session).clear(current_user.id)
        remaining = await MissedPrayersRepository(session).count_by_prayer(current_user.id, prayer, source_values(source_key))
        total = await MissedPrayersRepository(session).total_active(current_user.id)
        await message.answer(
            t(
                lang,
                "qazo.completion.success",
                count=count,
                prayer=prayer_label(lang, prayer),
                source=source_label(lang, source_key),
                remaining=remaining,
                total=total,
            ),
            reply_markup=qazo_complete_success_keyboard(lang, action.id),
        )
        return

    if state.state == "calc2_waiting_years":
        handled = await handle_calc2_year_input(message, current_user, session, text)
        if handled:
            return

