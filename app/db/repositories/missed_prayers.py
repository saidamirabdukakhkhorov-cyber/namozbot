from datetime import date, datetime, timezone

from sqlalchemy import func, select, update

from app.db.models import MissedPrayer, QazoCompletionAction
from app.db.repositories.base import BaseRepository


class MissedPrayersRepository(BaseRepository):
    async def create(
        self,
        *,
        user_id: int,
        prayer_name: str,
        prayer_date: date,
        source: str = "manual",
        daily_prayer_id: int | None = None,
        qazo_calculation_id: int | None = None,
    ):
        existing = await self.session.scalar(
            select(MissedPrayer).where(
                MissedPrayer.user_id == user_id,
                MissedPrayer.prayer_name == prayer_name,
                MissedPrayer.prayer_date == prayer_date,
                MissedPrayer.status == "active",
            )
        )
        if existing:
            return existing, False
        row = MissedPrayer(
            user_id=user_id,
            prayer_name=prayer_name,
            prayer_date=prayer_date,
            status="active",
            source=source,
            daily_prayer_id=daily_prayer_id,
            qazo_calculation_id=qazo_calculation_id,
        )
        self.session.add(row)
        await self.session.flush()
        return row, True

    async def summary(self, user_id: int, start_date: date | None = None, end_date: date | None = None, sources=None, qazo_calculation_id: int | None = None):
        stmt = select(MissedPrayer.prayer_name, func.count()).where(MissedPrayer.user_id == user_id, MissedPrayer.status == "active")
        if start_date:
            stmt = stmt.where(MissedPrayer.prayer_date >= start_date)
        if end_date:
            stmt = stmt.where(MissedPrayer.prayer_date <= end_date)
        if sources:
            stmt = stmt.where(MissedPrayer.source.in_(list(sources)))
        if qazo_calculation_id:
            stmt = stmt.where(MissedPrayer.qazo_calculation_id == qazo_calculation_id)
        rows = (await self.session.execute(stmt.group_by(MissedPrayer.prayer_name))).all()
        result = {"fajr": 0, "dhuhr": 0, "asr": 0, "maghrib": 0, "isha": 0, "witr": 0}
        for prayer, count in rows:
            result[prayer] = int(count)
        return result

    async def total_active(self, user_id: int, sources=None):
        stmt = select(func.count()).select_from(MissedPrayer).where(MissedPrayer.user_id == user_id, MissedPrayer.status == "active")
        if sources:
            stmt = stmt.where(MissedPrayer.source.in_(list(sources)))
        return int(await self.session.scalar(stmt) or 0)

    async def count_by_prayer(self, user_id: int, prayer_name: str, sources=None):
        stmt = select(func.count()).select_from(MissedPrayer).where(
            MissedPrayer.user_id == user_id,
            MissedPrayer.prayer_name == prayer_name,
            MissedPrayer.status == "active",
        )
        if sources:
            stmt = stmt.where(MissedPrayer.source.in_(list(sources)))
        return int(await self.session.scalar(stmt) or 0)

    async def complete_oldest(self, user_id: int, prayer_name: str, count: int, sources=None):
        if count <= 0:
            raise ValueError("Count must be greater than zero")
        stmt = select(MissedPrayer).where(
            MissedPrayer.user_id == user_id,
            MissedPrayer.prayer_name == prayer_name,
            MissedPrayer.status == "active",
        )
        if sources:
            stmt = stmt.where(MissedPrayer.source.in_(list(sources)))
        rows = list((await self.session.scalars(stmt.order_by(MissedPrayer.prayer_date.asc(), MissedPrayer.created_at.asc()).limit(count))).all())
        if len(rows) < count:
            raise ValueError(f"Only {len(rows)} active qazo rows available")
        ids = [r.id for r in rows]
        now = datetime.now(timezone.utc)
        await self.session.execute(
            update(MissedPrayer)
            .where(MissedPrayer.id.in_(ids))
            .values(status="completed", completed_at=now, updated_at=now)
        )
        action = QazoCompletionAction(
            user_id=user_id,
            prayer_name=prayer_name,
            completed_count=len(ids),
            missed_prayer_ids=ids,
            source_filter=list(sources) if sources else None,
            status="completed",
            created_at=now,
        )
        self.session.add(action)
        await self.session.flush()
        return action

    async def undo_completion_action(self, user_id: int, action_id: int):
        action = await self.session.get(QazoCompletionAction, action_id)
        if not action or action.user_id != user_id or action.status != "completed":
            return None
        now = datetime.now(timezone.utc)
        await self.session.execute(
            update(MissedPrayer)
            .where(MissedPrayer.id.in_(action.missed_prayer_ids), MissedPrayer.user_id == user_id)
            .values(status="active", completed_at=None, updated_at=now)
        )
        action.status = "undone"
        action.undone_at = now
        await self.session.flush()
        return action
