from collections.abc import Awaitable, Callable
from typing import Any
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from app.core.config import settings


class AdminOnlyMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: dict[str, Any]) -> Any:
        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        if isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id
        if user_id not in settings.admin_ids:
            if isinstance(event, Message):
                await event.answer("Bu bo'lim faqat adminlar uchun.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Bu bo'lim faqat adminlar uchun.", show_alert=True)
            return None
        return await handler(event, data)
