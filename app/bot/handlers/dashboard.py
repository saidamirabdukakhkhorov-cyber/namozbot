from datetime import date
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from app.bot.keyboards.main import main_menu_keyboard
from app.db.models import User
from app.db.repositories.daily_prayers import DailyPrayersRepository
from app.db.repositories.missed_prayers import MissedPrayersRepository
from app.services.i18n import prayer_label, t

router = Router(name="dashboard")

async def build_dashboard(user: User, session) -> str:
    lang = user.language_code
    today = date.today()
    daily = {row.prayer_name: row.status for row in await DailyPrayersRepository(session).list_for_date(user.id, today)}
    summary = await MissedPrayersRepository(session).summary(user.id)
    lines = [t(lang, "dashboard.title", date=today.strftime("%d.%m.%Y")), ""]
    for p in ["fajr", "dhuhr", "asr", "maghrib", "isha"]:
        lines.append(f"🕌 {prayer_label(lang, p)}: {t(lang, 'status.' + daily.get(p, 'pending'))}")
    lines += ["", f"📌 Active qazo: {sum(summary.values())} ta"]
    return "\n".join(lines)

@router.callback_query(F.data == "dashboard")
async def dashboard_cb(callback: CallbackQuery, current_user: User, session, is_admin: bool):
    await callback.message.answer(await build_dashboard(current_user, session), reply_markup=main_menu_keyboard(current_user.language_code, is_admin))
    await callback.answer()

@router.message(F.text.in_({"/home", "🏠 Menu"}))
async def dashboard_msg(message: Message, current_user: User, session, is_admin: bool):
    await message.answer(await build_dashboard(current_user, session), reply_markup=main_menu_keyboard(current_user.language_code, is_admin))
