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
    bot = Bot(token=settings.bot_token, parse_mode=None)
    dp = Dispatcher()
    dp.update.middleware(DbSessionMiddleware())
    dp.update.middleware(CurrentUserMiddleware())
    register_handlers(dp)
    scheduler = setup_scheduler(bot)
    scheduler.start()
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
