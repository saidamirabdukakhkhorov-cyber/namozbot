from datetime import date
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import DailyPrayer, MissedPrayer
class StatsService:
    def __init__(self, session: AsyncSession): self.session = session
    async def period_stats(self, user_id: int, start_date: date, end_date: date):
        prayed = int(await self.session.scalar(select(func.count()).select_from(DailyPrayer).where(DailyPrayer.user_id == user_id, DailyPrayer.status == "prayed", DailyPrayer.prayer_date.between(start_date, end_date))) or 0)
        missed = int(await self.session.scalar(select(func.count()).select_from(DailyPrayer).where(DailyPrayer.user_id == user_id, DailyPrayer.status == "missed", DailyPrayer.prayer_date.between(start_date, end_date))) or 0)
        completed = int(await self.session.scalar(select(func.count()).select_from(MissedPrayer).where(MissedPrayer.user_id == user_id, MissedPrayer.status == "completed", MissedPrayer.prayer_date.between(start_date, end_date))) or 0)
        active = int(await self.session.scalar(select(func.count()).select_from(MissedPrayer).where(MissedPrayer.user_id == user_id, MissedPrayer.status == "active")) or 0)
        return {"prayed": prayed, "missed": missed, "completed": completed, "active": active}
