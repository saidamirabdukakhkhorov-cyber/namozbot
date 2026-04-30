from datetime import date, datetime, timezone

from sqlalchemy import select, update

from app.db.models import DailyPrayer
from app.db.repositories.base import BaseRepository


class DailyPrayersRepository(BaseRepository):
    async def get_by_id(self, daily_prayer_id: int):
        return await self.session.get(DailyPrayer, daily_prayer_id)

    async def get(self, user_id: int, prayer_name: str, prayer_date: date):
        return await self.session.scalar(
            select(DailyPrayer).where(
                DailyPrayer.user_id == user_id,
                DailyPrayer.prayer_name == prayer_name,
                DailyPrayer.prayer_date == prayer_date,
            )
        )

    async def list_for_date(self, user_id: int, prayer_date: date):
        return list(
            (
                await self.session.scalars(
                    select(DailyPrayer)
                    .where(DailyPrayer.user_id == user_id, DailyPrayer.prayer_date == prayer_date)
                    .order_by(DailyPrayer.prayer_time.asc())
                )
            ).all()
        )

    async def upsert_pending(self, *, user_id: int, prayer_name: str, prayer_date: date, prayer_time: datetime):
        row = await self.get(user_id, prayer_name, prayer_date)
        if row:
            # Do not reset a user's answer. Only refresh time if the API/city changed.
            row.prayer_time = prayer_time
            await self.session.flush()
            return row
        row = DailyPrayer(
            user_id=user_id,
            prayer_name=prayer_name,
            prayer_date=prayer_date,
            prayer_time=prayer_time,
            status="pending",
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def set_status(self, daily_prayer_id: int, status: str, *, snooze_until: datetime | None = None):
        await self.session.execute(
            update(DailyPrayer)
            .where(DailyPrayer.id == daily_prayer_id)
            .values(status=status, answered_at=datetime.now(timezone.utc), snooze_until=snooze_until)
        )
