from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from app.bot.keyboards.admin import admin_keyboard
from app.core.config import settings
from app.db.models import AdminAction, MissedPrayer, ReminderLog, User
from app.db.repositories.admin import AdminRepository

router = Router(name="admin")

def allowed(user_id: int | None) -> bool:
    return user_id in settings.admin_ids

@router.message(Command("admin"))
@router.message(F.text == "🛡 Admin panel")
async def admin_panel(message: Message, session):
    if not allowed(message.from_user.id if message.from_user else None):
        await message.answer("Bu bo'lim faqat adminlar uchun.")
        return
    await message.answer("🛡 Admin panel", reply_markup=admin_keyboard())

@router.callback_query(F.data == "admin:dashboard")
async def admin_dashboard(callback: CallbackQuery, session):
    if not allowed(callback.from_user.id):
        await callback.answer("Bu bo'lim faqat adminlar uchun.", show_alert=True); return
    users_total = await session.scalar(select(func.count()).select_from(User)) or 0
    users_active = await session.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))) or 0
    qazo_active = await session.scalar(select(func.count()).select_from(MissedPrayer).where(MissedPrayer.status == "active")) or 0
    reminders_failed = await session.scalar(select(func.count()).select_from(ReminderLog).where(ReminderLog.status == "failed")) or 0
    await AdminRepository(session).log_action(admin_telegram_id=callback.from_user.id, action="admin_dashboard")
    await callback.message.answer(f"Admin dashboard\n\nUsers:\nTotal: {users_total}\nActive: {users_active}\n\nQazo:\nActive qazo total: {qazo_active}\n\nReminders failed: {reminders_failed}", reply_markup=admin_keyboard())
    await callback.answer()

@router.callback_query(F.data == "admin:users")
async def admin_users(callback: CallbackQuery, session):
    if not allowed(callback.from_user.id):
        await callback.answer("Bu bo'lim faqat adminlar uchun.", show_alert=True); return
    rows = (await session.scalars(select(User).order_by(User.created_at.desc()).limit(10))).all()
    text = "Users\n\n" + "\n".join(f"#{u.id} {u.telegram_id} @{u.username or '-'} {u.city or '-'}" for u in rows)
    await callback.message.answer(text or "Users topilmadi")
    await callback.answer()

@router.callback_query(F.data.startswith("admin:"))
async def admin_placeholder(callback: CallbackQuery):
    if not allowed(callback.from_user.id):
        await callback.answer("Bu bo'lim faqat adminlar uchun.", show_alert=True); return
    await callback.message.answer("Bu admin bo'limi scaffold qilingan. README va docs/admin_panel.md dagi workflow bo'yicha kengaytiriladi.")
    await callback.answer()
