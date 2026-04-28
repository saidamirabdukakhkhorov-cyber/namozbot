from __future__ import annotations

from aiogram import F, Router
from app.bot.filters.text import text_is_one_of
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.keyboards.main import main_menu_keyboard
from app.core.constants import CURRENT_QAZO_SOURCES, PRAYER_NAMES
from app.db.models import User
from app.db.repositories.daily_prayers import DailyPrayersRepository
from app.db.repositories.missed_prayers import MissedPrayersRepository
from app.db.repositories.states import StatesRepository
from app.services.date_periods import current_month_range
from app.services.timezone import tashkent_today
from app.services.i18n import prayer_label, t

router = Router(name="dashboard")


def dashboard_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "menu.today"), callback_data="today:open")],
        [InlineKeyboardButton(text=t(language, "menu.qazo"), callback_data="qazo:overview")],
        [InlineKeyboardButton(text=t(language, "menu.calculator"), callback_data="calc:start")],
        [InlineKeyboardButton(text=t(language, "menu.stats"), callback_data="stats:open")],
    ])


async def build_dashboard(user: User, session) -> str:
    lang = user.language_code or "uz"
    today = tashkent_today()
    daily = {row.prayer_name: row.status for row in await DailyPrayersRepository(session).list_for_date(user.id, today)}
    start, end = current_month_range(today)
    repo = MissedPrayersRepository(session)
    current_summary = await repo.summary(user.id, start, end, CURRENT_QAZO_SOURCES)
    calculator_total = await repo.total_active(user.id, ["calculator"])

    lines = [
        t(lang, "dashboard.title"),
        "",
        t(lang, "dashboard.today", date=today.isoformat()),
        t(lang, "dashboard.city", city=user.city or "-"),
        "",
        t(lang, "dashboard.today_prayers"),
    ]
    for p in PRAYER_NAMES:
        status = daily.get(p, "pending")
        lines.append(f"{prayer_label(lang, p)}: {t(lang, 'status.' + status)}")

    lines += [
        "",
        t(lang, "dashboard.qazo"),
        t(lang, "dashboard.current_month", count=sum(current_summary.values())),
        t(lang, "dashboard.calculator_count", count=calculator_total),
    ]
    return "\n".join(lines)


@router.callback_query(F.data == "dashboard")
async def dashboard_cb(callback: CallbackQuery, current_user: User, session, is_admin: bool):
    await StatesRepository(session).clear(current_user.id)
    text = await build_dashboard(current_user, session)
    try:
        await callback.message.edit_text(text, reply_markup=dashboard_keyboard(current_user.language_code))
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=main_menu_keyboard(current_user.language_code, is_admin),
        )
    await callback.answer()


@router.message(text_is_one_of("/home", "🏠 Menu", "🏠 Asosiy menu", "🏠 Главное меню", "🏠 Main menu", "Asosiy menu", "Menu", "Главное меню", "Main menu"))
async def dashboard_msg(message: Message, current_user: User, session, is_admin: bool):
    await StatesRepository(session).clear(current_user.id)
    await message.answer(
        await build_dashboard(current_user, session),
        reply_markup=main_menu_keyboard(current_user.language_code, is_admin),
    )
