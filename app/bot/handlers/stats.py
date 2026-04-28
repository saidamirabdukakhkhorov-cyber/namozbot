from datetime import date
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from app.db.models import User
from app.db.repositories.missed_prayers import MissedPrayersRepository
from app.services.i18n import prayer_label

router = Router(name="stats")

@router.message(Command("stats"))
@router.message(F.text.in_({"📊 Statistika", "📊 Статистика", "📊 Statistics"}))
async def stats_handler(message: Message, current_user: User, session):
    summary = await MissedPrayersRepository(session).summary(current_user.id)
    lines = ["📊 Statistika", "", f"Bugungi sana: {date.today()}", f"Qolgan active qazo: {sum(summary.values())} ta", ""]
    for p, count in summary.items():
        lines.append(f"{prayer_label(current_user.language_code, p)}: {count} ta")
    await message.answer("\n".join(lines))
