from datetime import datetime, timezone
from sqlalchemy import func, select, update
from app.db.models import ReminderSetting, User, UserPreference
from app.db.repositories.base import BaseRepository
class UsersRepository(BaseRepository):
    async def get_by_telegram_id(self, telegram_id: int): return await self.session.scalar(select(User).where(User.telegram_id == telegram_id))
    async def get_or_create_from_telegram(self, *, telegram_id: int, username: str | None, full_name: str | None):
        user = await self.get_by_telegram_id(telegram_id); now = datetime.now(timezone.utc)
        if user:
            user.username = username; user.full_name = full_name; user.last_activity_at = now; return user
        user = User(telegram_id=telegram_id, username=username, full_name=full_name, language_code="uz", timezone="Asia/Tashkent", is_active=True, last_activity_at=now)
        self.session.add(user); await self.session.flush()
        self.session.add(UserPreference(user_id=user.id, language=user.language_code))
        from datetime import time as _time
        self.session.add(ReminderSetting(
            user_id=user.id,
            prayer_reminders_enabled=True,
            qazo_reminders_enabled=True,
            qazo_reminder_times=["08:00", "21:00"],
            daily_qazo_limit=1,
            quiet_hours_enabled=True,
            quiet_hours_start=_time(23, 0),
            quiet_hours_end=_time(6, 0),
        ))
        await self.session.flush(); return user
    async def set_language(self, user_id: int, language: str):
        await self.session.execute(update(User).where(User.id == user_id).values(language_code=language, updated_at=func.now()))
        await self.session.execute(update(UserPreference).where(UserPreference.user_id == user_id).values(language=language, updated_at=func.now()))
    async def set_city(self, user_id: int, city: str, timezone_name: str = "Asia/Tashkent"):
        await self.session.execute(update(User).where(User.id == user_id).values(city=city, timezone=timezone_name, updated_at=func.now()))
    async def complete_onboarding(self, user_id: int):
        await self.session.execute(update(User).where(User.id == user_id).values(onboarding_completed=True, updated_at=func.now()))
    async def list_users(self, *, limit: int = 10, offset: int = 0):
        return list((await self.session.scalars(select(User).order_by(User.created_at.desc()).limit(limit).offset(offset))).all())
