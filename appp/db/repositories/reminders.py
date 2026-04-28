from datetime import datetime, timezone
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from app.db.models import ReminderLog
from app.db.repositories.base import BaseRepository

class RemindersRepository(BaseRepository):
    async def create_pending(self, *, user_id: int, reminder_type: str, related_entity_type: str, related_entity_id: int, scheduled_for: datetime):
        stmt = insert(ReminderLog).values(user_id=user_id, reminder_type=reminder_type, related_entity_type=related_entity_type, related_entity_id=related_entity_id, scheduled_for=scheduled_for, status="pending").on_conflict_do_nothing(constraint="uq_reminders_idempotency").returning(ReminderLog)
        row = (await self.session.scalars(stmt)).first()
        return row, row is not None
    async def log_pending_once(self, **kwargs) -> bool:
        _, created = await self.create_pending(**kwargs)
        return created
    async def mark_sent(self, reminder_id: int):
        await self.session.execute(update(ReminderLog).where(ReminderLog.id == reminder_id).values(status="sent", sent_at=datetime.now(timezone.utc)))
    async def mark_failed(self, reminder_id: int, error: str):
        await self.session.execute(update(ReminderLog).where(ReminderLog.id == reminder_id).values(status="failed", error_message=error))
