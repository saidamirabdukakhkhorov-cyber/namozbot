from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.city import city_keyboard
from app.bot.keyboards.language import language_keyboard
from app.bot.keyboards.settings import settings_keyboard
from app.db.models import User
from app.db.repositories.states import StatesRepository

router = Router(name="settings")


@router.message(Command("settings"))
@router.message(F.text.in_({"⚙️ Sozlamalar", "⚙️ Настройки", "⚙️ Settings"}))
async def settings_handler(message: Message, current_user: User):
    await message.answer(
        f"⚙️ Sozlamalar\n\nTil: {current_user.language_code}\nShahar: {current_user.city or '-'}\nTimezone: {current_user.timezone}",
        reply_markup=settings_keyboard(),
    )


@router.callback_query(F.data == "settings:language")
async def settings_language(callback: CallbackQuery, current_user: User, session):
    await StatesRepository(session).set(current_user.id, "settings_language", {})
    await callback.message.answer("Tilni tanlang", reply_markup=language_keyboard())
    await callback.answer()


@router.callback_query(F.data == "settings:city")
async def settings_city(callback: CallbackQuery, current_user: User, session):
    await StatesRepository(session).set(current_user.id, "settings_city", {})
    await callback.message.answer("Shahringizni tanlang", reply_markup=city_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("settings:"))
async def settings_placeholder(callback: CallbackQuery):
    await callback.message.answer("Bu sozlama bo'limi keyingi versiyada kengaytiriladi.")
    await callback.answer()
