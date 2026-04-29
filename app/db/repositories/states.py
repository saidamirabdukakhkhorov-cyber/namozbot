from datetime import datetime
from typing import Any
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from app.db.models import UserState
from app.db.repositories.base import BaseRepository
class StatesRepository(BaseRepository):
    async def get(self, user_id: int): return await self.session.scalar(select(UserState).where(UserState.user_id == user_id))
    async def set(self, user_id: int, state: str, payload: dict[str, Any] | None = None, expires_at: datetime | None = None):
        stmt = insert(UserState).values(user_id=user_id, state=state, payload=payload or {}, expires_at=expires_at).on_conflict_do_update(index_elements=[UserState.user_id], set_={"state": state, "payload": payload or {}, "expires_at": expires_at})
        await self.session.execute(stmt)
    async def clear(self, user_id: int): await self.session.execute(delete(UserState).where(UserState.user_id == user_id))
