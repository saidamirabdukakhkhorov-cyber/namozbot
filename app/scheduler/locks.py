from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

LOCK_KEY = 42826001

@asynccontextmanager
async def advisory_lock(session: AsyncSession, key: int = LOCK_KEY) -> AsyncIterator[bool]:
    acquired = bool(await session.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}))
    try:
        yield acquired
    finally:
        if acquired:
            await session.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
