"""
Main entry point. Runs the Telegram bot + Mini App web server together.
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

from app.bot.handlers import register_handlers
from app.bot.middlewares.db import DbSessionMiddleware
from app.bot.middlewares.user import CurrentUserMiddleware
from app.core.config import settings
from app.core.logging import setup_logging
from app.scheduler.runner import setup_scheduler
from app.webapp import create_webapp

logger = logging.getLogger(__name__)


async def setup_bot_menu(bot: Bot) -> None:
    commands = [
        BotCommand(command="start",    description="Bosh sahifa"),
        BotCommand(command="today",    description="Bugungi namozlar"),
        BotCommand(command="qazo",     description="Qazo namozlarim"),
        BotCommand(command="stats",    description="Statistika"),
        BotCommand(command="settings", description="Sozlamalar"),
        BotCommand(command="help",     description="Yordam"),
    ]
    await bot.set_my_commands(commands)

    webapp_url = getattr(settings, "webapp_url", None)
    if webapp_url:
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="Ilovani ochish",
                    web_app=WebAppInfo(url=webapp_url),
                )
            )
            logger.info("Mini App button set: %s", webapp_url)
        except Exception as exc:
            logger.warning("Could not set menu button: %s", exc)


async def run_webapp(app: web.Application) -> web.AppRunner:
    runner = web.AppRunner(app)
    await runner.setup()
    host = getattr(settings, "webapp_host", None) or "0.0.0.0"
    port = int(getattr(settings, "webapp_port", None) or 8080)
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("Mini App server started at %s:%s", host, port)
    return runner


async def main() -> None:
    setup_logging()
    settings.validate_required()

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.update.middleware(DbSessionMiddleware())
    dp.update.middleware(CurrentUserMiddleware())
    register_handlers(dp)

    await setup_bot_menu(bot)

    scheduler = setup_scheduler(bot)
    scheduler.start()

    webapp = create_webapp()
    runner = await run_webapp(webapp)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
