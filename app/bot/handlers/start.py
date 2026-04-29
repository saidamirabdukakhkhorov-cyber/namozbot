from __future__ import annotations

import asyncio

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove, MenuButtonCommands, MenuButtonWebApp, WebAppInfo
from sqlalchemy import update

from app.bot.keyboards.language import language_keyboard, onboarding_continue_keyboard, onboarding_privacy_keyboard
from app.bot.keyboards.miniapp import mini_app_keyboard
from app.core.config import settings
from app.db.models import ReminderSetting, User
from app.db.repositories.states import StatesRepository
from app.db.repositories.users import UsersRepository
from app.services.i18n import t

router = Router(name="start")


async def _set_registration_menu_button(bot, chat_id: int, *, language: str | None = None, enabled: bool = False) -> None:
    """Hide Mini App chat button until onboarding is completed; enable it after consent."""
    try:
        url = getattr(settings, "webapp_url", "") or ""
        if enabled and url:
            await bot.set_chat_menu_button(
                chat_id=chat_id,
                menu_button=MenuButtonWebApp(
                    text=t(language or "uz", "miniapp.open"),
                    web_app=WebAppInfo(url=url),
                ),
            )
        else:
            await bot.set_chat_menu_button(chat_id=chat_id, menu_button=MenuButtonCommands())
    except Exception:
        # Menu button is UX-only. API gate in webapp.py remains the source of truth.
        pass


@router.message(CommandStart())
async def start(message: Message, current_user: User, session, is_admin: bool):
    await StatesRepository(session).clear(current_user.id)
    if not current_user.language_code or not current_user.onboarding_completed:
        await _set_registration_menu_button(message.bot, message.chat.id, enabled=False)
        await message.answer(t("uz", "onboarding.choose_language"), reply_markup=language_keyboard())
        return
    lang = current_user.language_code or "uz"
    await _set_registration_menu_button(message.bot, message.chat.id, language=lang, enabled=True)
    await message.answer(
        t(lang, "miniapp.ready"),
        reply_markup=mini_app_keyboard(lang),
    )


@router.callback_query(F.data.startswith("lang:"))
async def choose_language(callback: CallbackQuery, current_user: User, session, is_admin: bool):
    language = (callback.data or "uz").split(":", 1)[1]
    state = await StatesRepository(session).get(current_user.id)

    await UsersRepository(session).set_language(current_user.id, language)

    if state and state.state == "settings_language":
        await StatesRepository(session).clear(current_user.id)
        try:
            await callback.message.edit_text(t(language, "settings.language.updated"))
        except Exception:
            await callback.message.answer(t(language, "settings.language.updated"))
        await callback.message.answer(t(language, "settings.language.updated"), reply_markup=ReplyKeyboardRemove())
        await asyncio.sleep(0.15)
        if current_user.onboarding_completed:
            await _set_registration_menu_button(callback.bot, callback.message.chat.id, language=language, enabled=True)
            await callback.message.answer(t(language, "miniapp.ready"), reply_markup=mini_app_keyboard(language))
        await callback.answer()
        return

    await StatesRepository(session).set(current_user.id, "onboarding_intro", {"language": language})
    await callback.message.edit_text(t(language, "onboarding.intro"), reply_markup=onboarding_continue_keyboard(language))
    await callback.answer()


@router.callback_query(F.data == "onboarding:privacy")
async def onboarding_privacy(callback: CallbackQuery, current_user: User, session):
    language = current_user.language_code or "uz"
    await StatesRepository(session).set(current_user.id, "onboarding_privacy", {})
    await callback.message.edit_text(t(language, "onboarding.privacy"), reply_markup=onboarding_privacy_keyboard(language))
    await callback.answer()


@router.callback_query(F.data == "onboarding:city")
async def onboarding_complete(callback: CallbackQuery, current_user: User, session):
    language = current_user.language_code or "uz"
    # Mini-App first flow: after privacy agreement we complete onboarding immediately.
    # Default city/timezone is Tashkent; user can change it inside the Mini App settings.
    await UsersRepository(session).set_city(current_user.id, current_user.city or "Toshkent")
    await session.execute(
        update(ReminderSetting)
        .where(ReminderSetting.user_id == current_user.id)
        .values(prayer_reminders_enabled=True, qazo_reminders_enabled=False)
    )
    await UsersRepository(session).complete_onboarding(current_user.id)
    await StatesRepository(session).clear(current_user.id)
    await _set_registration_menu_button(callback.bot, callback.message.chat.id, language=language, enabled=True)
    await callback.message.edit_text(t(language, "onboarding.done_miniapp"))
    await callback.message.answer(
        t(language, "miniapp.ready"),
        reply_markup=mini_app_keyboard(language),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("city:"))
async def choose_city(callback: CallbackQuery, current_user: User, session, is_admin: bool):
    city = (callback.data or "city:other").split(":", 1)[1]
    language = current_user.language_code or "uz"
    state = await StatesRepository(session).get(current_user.id)
    is_settings_flow = bool(state and state.state == "settings_city")

    if city == "other":
        await StatesRepository(session).set(
            current_user.id,
            "waiting_custom_city",
            {"source": "settings" if is_settings_flow else "onboarding"},
        )
        await callback.message.edit_text(t(language, "city.custom_prompt"))
        await callback.answer()
        return

    await UsersRepository(session).set_city(current_user.id, city)

    if is_settings_flow:
        await StatesRepository(session).clear(current_user.id)
        try:
            await callback.message.edit_text(t(language, "settings.city.updated", city=city))
        except Exception:
            await callback.message.answer(t(language, "settings.city.updated", city=city), reply_markup=mini_app_keyboard(language))
    else:
        await session.execute(
            update(ReminderSetting)
            .where(ReminderSetting.user_id == current_user.id)
            .values(prayer_reminders_enabled=True, qazo_reminders_enabled=False)
        )
        await UsersRepository(session).complete_onboarding(current_user.id)
        await StatesRepository(session).clear(current_user.id)
        await _set_registration_menu_button(callback.bot, callback.message.chat.id, language=language, enabled=True)
        await callback.message.edit_text(t(language, "onboarding.done_miniapp"))
        await callback.message.answer(t(language, "miniapp.ready"), reply_markup=mini_app_keyboard(language))

    await callback.answer()


@router.callback_query(F.data.startswith("onboarding:reminders:"))
async def onboarding_reminders(callback: CallbackQuery, current_user: User, session, is_admin: bool):
    language = current_user.language_code or "uz"
    enabled = callback.data.endswith(":on")
    await session.execute(
        update(ReminderSetting)
        .where(ReminderSetting.user_id == current_user.id)
        .values(prayer_reminders_enabled=enabled, qazo_reminders_enabled=enabled)
    )
    await UsersRepository(session).complete_onboarding(current_user.id)
    await StatesRepository(session).clear(current_user.id)
    await _set_registration_menu_button(callback.bot, callback.message.chat.id, language=language, enabled=True)
    await callback.message.edit_text(t(language, "onboarding.done", city=current_user.city or "-"))
    await callback.message.answer(
        t(language, "miniapp.ready"),
        reply_markup=mini_app_keyboard(language),
    )
    await callback.answer()


@router.callback_query(F.data == "miniapp:not_configured")
async def miniapp_not_configured(callback: CallbackQuery, current_user: User):
    await callback.answer(t(current_user.language_code or "uz", "miniapp.not_configured"), show_alert=True)
