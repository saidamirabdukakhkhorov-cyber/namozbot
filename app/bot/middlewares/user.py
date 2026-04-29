from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update, User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.repositories.users import UsersRepository


def _telegram_user_from_event(event: TelegramObject) -> TelegramUser | None:
    """Extract Telegram user from both Update-level and event-level middlewares.

    The middleware is registered on dp.update in app/main.py. In aiogram 3 this
    means the middleware receives an Update object, not a Message/CallbackQuery.
    Without this extraction current_user/is_admin are not injected into handlers.
    """
    if isinstance(event, Message):
        return event.from_user
    if isinstance(event, CallbackQuery):
        return event.from_user
    if isinstance(event, Update):
        if event.message and event.message.from_user:
            return event.message.from_user
        if event.callback_query and event.callback_query.from_user:
            return event.callback_query.from_user
        if event.edited_message and event.edited_message.from_user:
            return event.edited_message.from_user
        if event.my_chat_member and event.my_chat_member.from_user:
            return event.my_chat_member.from_user
        if event.chat_member and event.chat_member.from_user:
            return event.chat_member.from_user
    return None


class CurrentUserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data.setdefault("current_user", None)
        data.setdefault("is_admin", False)

        tg_user = _telegram_user_from_event(event)
        session: AsyncSession | None = data.get("session")

        if tg_user and session:
            repo = UsersRepository(session)
            full_name = " ".join(
                part for part in [tg_user.first_name, tg_user.last_name] if part
            )
            user = await repo.get_or_create_from_telegram(
                telegram_id=tg_user.id,
                username=tg_user.username,
                full_name=full_name,
            )
            data["current_user"] = user
            data["is_admin"] = tg_user.id in settings.admin_ids

        return await handler(event, data)
