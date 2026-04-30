from aiogram import Dispatcher
from app.bot.handlers import admin, dashboard, global_menu, prayer, privacy, qazo, qazo_calculator, settings, start, state_text, stats, today


def register_handlers(dp: Dispatcher) -> None:
    for router in [
        start.router,
        global_menu.router,
        dashboard.router,
        today.router,
        prayer.router,
        qazo_calculator.router,
        stats.router,
        settings.router,
        privacy.router,
        admin.router,
        qazo.router,
        state_text.router,
    ]:
        dp.include_router(router)
