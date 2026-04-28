from __future__ import annotations

from aiogram import Router
from aiogram.types import Message

from app.bot.filters.text import GlobalMenuAction, GlobalMenuFilter
from app.bot.handlers.global_navigation import send_global_menu_screen
from app.db.models import User

router = Router(name="global_menu")


@router.message(GlobalMenuFilter())
async def global_menu_handler(
    message: Message,
    global_menu_action: GlobalMenuAction,
    current_user: User,
    session,
    is_admin: bool,
):
    await send_global_menu_screen(
        message=message,
        action=global_menu_action,
        current_user=current_user,
        session=session,
        is_admin=is_admin,
    )
