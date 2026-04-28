from sqlalchemy import func, select
from app.db.models import AdminAction, DailyPrayer, MissedPrayer, ReminderLog, User
from app.db.repositories.base import BaseRepository
class AdminRepository(BaseRepository):
    async def log_action(self, *, admin_telegram_id: int, action: str, target_user_id: int | None = None, payload: dict | None = None):
        self.session.add(AdminAction(admin_telegram_id=admin_telegram_id, action=action, target_user_id=target_user_id, payload=payload or {}))
    async def dashboard(self):
        return {
          "total_users": int(await self.session.scalar(select(func.count()).select_from(User)) or 0),
          "active_users": int(await self.session.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))) or 0),
          "daily_statuses": int(await self.session.scalar(select(func.count()).select_from(DailyPrayer)) or 0),
          "active_qazo": int(await self.session.scalar(select(func.count()).select_from(MissedPrayer).where(MissedPrayer.status == "active")) or 0),
          "completed_qazo": int(await self.session.scalar(select(func.count()).select_from(MissedPrayer).where(MissedPrayer.status == "completed")) or 0),
          "sent_reminders": int(await self.session.scalar(select(func.count()).select_from(ReminderLog).where(ReminderLog.status == "sent")) or 0),
          "failed_reminders": int(await self.session.scalar(select(func.count()).select_from(ReminderLog).where(ReminderLog.status == "failed")) or 0),
        }
