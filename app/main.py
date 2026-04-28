from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher

from app.bot.handlers import register_handlers
from app.bot.middlewares.db import DbSessionMiddleware
from app.bot.middlewares.user import CurrentUserMiddleware
from app.core.config import settings
from app.core.logging import setup_logging
from app.scheduler.runner import setup_scheduler


async def main() -> None:
    setup_logging()
    settings.validate_required()

    # aiogram >=3.7 no longer accepts parse_mode/disable_web_page_preview/etc.
    # directly in Bot(...). The default parse mode is already None, so keep the
    # constructor minimal and compatible with current aiogram 3.x releases.
    bot = Bot(token=settings.bot_token)

    dp = Dispatcher()
    dp.update.middleware(DbSessionMiddleware())
    dp.update.middleware(CurrentUserMiddleware())

    register_handlers(dp)

    scheduler = setup_scheduler(bot)
    scheduler.start()

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
