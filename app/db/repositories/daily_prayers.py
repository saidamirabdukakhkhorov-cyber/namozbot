from datetime import date, datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from app.db.models import DailyPrayer
from app.db.repositories.base import BaseRepository
class DailyPrayersRepository(BaseRepository):
    async def get_by_id(self, daily_prayer_id: int):
        return await self.session.get(DailyPrayer, daily_prayer_id)
    async def get(self, user_id: int, prayer_name: str, prayer_date: date):
        return await self.session.scalar(select(DailyPrayer).where(DailyPrayer.user_id == user_id, DailyPrayer.prayer_name == prayer_name, DailyPrayer.prayer_date == prayer_date))
    async def list_for_date(self, user_id: int, prayer_date: date):
        return list((await self.session.scalars(select(DailyPrayer).where(DailyPrayer.user_id == user_id, DailyPrayer.prayer_date == prayer_date).order_by(DailyPrayer.prayer_time.asc()))).all())
    async def upsert_pending(self, *, user_id: int, prayer_name: str, prayer_date: date, prayer_time: datetime):
        stmt = insert(DailyPrayer).values(user_id=user_id, prayer_name=prayer_name, prayer_date=prayer_date, prayer_time=prayer_time, status="pending").on_conflict_do_nothing(constraint="uq_daily_prayer_user_name_date").returning(DailyPrayer)
        return (await self.session.scalars(stmt)).first() or await self.get(user_id, prayer_name, prayer_date)
    async def set_status(self, daily_prayer_id: int, status: str, *, snooze_until: datetime | None = None):
        await self.session.execute(update(DailyPrayer).where(DailyPrayer.id == daily_prayer_id).values(status=status, answered_at=datetime.now(timezone.utc), snooze_until=snooze_until))
