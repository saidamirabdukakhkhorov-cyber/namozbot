from __future__ import annotations

from aiogram import Router
from aiogram.types import Message

from app.bot.filters.text import GlobalMenuAction, GlobalMenuFilter
from app.bot.keyboards.admin import admin_keyboard
from app.bot.keyboards.main import main_menu_keyboard
from app.bot.keyboards.prayer import prayer_select_keyboard
from app.bot.keyboards.qazo import qazo_add_date_keyboard, qazo_overview_keyboard
from app.bot.keyboards.qazo_calculator import calculator_start_keyboard
from app.bot.keyboards.settings import settings_keyboard
from app.bot.keyboards.stats import stats_keyboard
from app.core.config import settings as app_settings
from app.db.models import User
from app.db.repositories.states import StatesRepository
from app.services.i18n import t

router = Router(name="global_menu")


def _lang(user: User) -> str:
    return user.language_code or "uz"


@router.message(GlobalMenuFilter())
async def global_menu_handler(
    message: Message,
    global_menu_action: GlobalMenuAction,
    current_user: User,
    session,
    is_admin: bool,
):
    """Single reliable entry point for Reply Keyboard global navigation.

    This intentionally sits before feature routers. It prevents Telegram client
    emoji variations (for example ⚙️ vs ⚙) and active wizard states from making
    global menu buttons feel broken. Any global menu tap clears the current flow
    and opens the requested top-level screen.
    """
    lang = _lang(current_user)
    await StatesRepository(session).clear(current_user.id)

    if global_menu_action == "home":
        from app.bot.handlers.dashboard import build_dashboard

        await message.answer(
            await build_dashboard(current_user, session),
            reply_markup=main_menu_keyboard(lang, is_admin),
        )
        return

    if global_menu_action == "today":
        from app.bot.handlers.today import build_today_screen

        text, keyboard = await build_today_screen(current_user, session)
        await message.answer(text, reply_markup=keyboard)
        return

    if global_menu_action == "qazo":
        from app.bot.handlers.qazo import render_qazo_overview

        text, empty = await render_qazo_overview(current_user, session)
        await message.answer(text, reply_markup=qazo_overview_keyboard(lang, empty=empty))
        return

    if global_menu_action == "qazo_add":
        await StatesRepository(session).set(current_user.id, "qazo_add_date", {})
        await message.answer(t(lang, "qazo.add.date_screen"), reply_markup=qazo_add_date_keyboard(lang))
        return

    if global_menu_action == "calculator":
        from app.bot.handlers.qazo_calculator import calc_start_text

        await StatesRepository(session).set(current_user.id, "calc_period_type", {})
        await message.answer(calc_start_text(lang), reply_markup=calculator_start_keyboard(lang))
        return

    if global_menu_action == "stats":
        from app.bot.handlers.stats import render_stats

        await message.answer(await render_stats(current_user, session), reply_markup=stats_keyboard(lang))
        return

    if global_menu_action == "settings":
        from app.bot.handlers.settings import render_settings

        await message.answer(await render_settings(current_user, session), reply_markup=settings_keyboard(lang))
        return

    if global_menu_action == "help":
        from app.bot.handlers.privacy import help_keyboard

        await message.answer(t(lang, "help.text"), reply_markup=help_keyboard(lang))
        return

    if global_menu_action == "admin":
        telegram_id = message.from_user.id if message.from_user else None
        if telegram_id not in app_settings.admin_ids:
            await message.answer("Bu bo'lim faqat adminlar uchun.")
            return
        await message.answer("🛡 Admin panel", reply_markup=admin_keyboard())
        return
