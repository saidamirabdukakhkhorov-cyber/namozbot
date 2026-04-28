from collections.abc import Awaitable, Callable
from typing import Any
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.repositories.users import UsersRepository
from app.core.config import settings


class CurrentUserMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user = None
        if isinstance(event, Message):
            tg_user = event.from_user
        elif isinstance(event, CallbackQuery):
            tg_user = event.from_user
        session: AsyncSession | None = data.get("session")
        if tg_user and session:
            repo = UsersRepository(session)
            full_name = " ".join(x for x in [tg_user.first_name, tg_user.last_name] if x)
            user = await repo.get_or_create_from_telegram(telegram_id=tg_user.id, username=tg_user.username, full_name=full_name)
            data["current_user"] = user
            data["is_admin"] = tg_user.id in settings.admin_ids
        return await handler(event, data)
