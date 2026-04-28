from datetime import date, datetime, timezone
from sqlalchemy import select, update
from app.db.models import QazoCalculation
from app.db.repositories.base import BaseRepository
class QazoCalculationsRepository(BaseRepository):
    async def create_calculated(self, *, user_id: int, start_date: date, end_date: date, selected_prayers: list[str], days_count: int, breakdown: dict[str, int]):
        calc = QazoCalculation(user_id=user_id, start_date=start_date, end_date=end_date, selected_prayers=selected_prayers, days_count=days_count, prayers_count=len(selected_prayers), total_count=sum(breakdown.values()), breakdown=breakdown, created_breakdown={p:0 for p in breakdown}, skipped_breakdown={p:0 for p in breakdown}, status="calculated")
        self.session.add(calc); await self.session.flush(); return calc
    async def mark_applied(self, calculation_id: int, created_breakdown: dict[str, int], skipped_breakdown: dict[str, int]):
        await self.session.execute(update(QazoCalculation).where(QazoCalculation.id == calculation_id).values(status="applied", created_breakdown=created_breakdown, skipped_breakdown=skipped_breakdown, created_missed_count=sum(created_breakdown.values()), skipped_existing_count=sum(skipped_breakdown.values()), applied_at=datetime.now(timezone.utc)))
    async def history(self, user_id: int, limit: int = 10, offset: int = 0):
        return list((await self.session.scalars(select(QazoCalculation).where(QazoCalculation.user_id == user_id).order_by(QazoCalculation.created_at.desc()).limit(limit).offset(offset))).all())
