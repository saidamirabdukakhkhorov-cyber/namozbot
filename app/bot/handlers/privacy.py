from aiogram import F, Router
from app.bot.filters.text import text_is_one_of
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.services.i18n import t

router = Router(name="privacy")


def back_home_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "common.home"), callback_data="dashboard")],
    ])


@router.callback_query(F.data == "privacy")
async def privacy_cb(callback: CallbackQuery, current_user):
    lang = current_user.language_code or "uz"
    try:
        await callback.message.edit_text(t(lang, "privacy.text"), reply_markup=back_home_keyboard(lang))
    except Exception:
        await callback.message.answer(t(lang, "privacy.text"), reply_markup=back_home_keyboard(lang))
    await callback.answer()


@router.message(text_is_one_of("ℹ️ Yordam", "ℹ️ Помощь", "ℹ️ Help", "ℹ Yordam", "ℹ Помощь", "ℹ Help", "Yordam", "Помощь", "Help", "/help"))
async def help_handler(message: Message, current_user):
    lang = current_user.language_code or "uz"
    await message.answer(t(lang, "help.text"), reply_markup=help_keyboard(lang))


def help_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "help.calc"), callback_data="help:calculator")],
        [InlineKeyboardButton(text=t(language, "help.complete"), callback_data="help:completion")],
        [InlineKeyboardButton(text=t(language, "common.home"), callback_data="dashboard")],
    ])


def help_back_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "common.back"), callback_data="help:open")],
        [InlineKeyboardButton(text=t(language, "common.home"), callback_data="dashboard")],
    ])


@router.callback_query(F.data == "help:open")
async def help_open(callback: CallbackQuery, current_user):
    lang = current_user.language_code or "uz"
    try:
        await callback.message.edit_text(t(lang, "help.text"), reply_markup=help_keyboard(lang))
    except Exception:
        await callback.message.answer(t(lang, "help.text"), reply_markup=help_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "help:calculator")
async def help_calculator(callback: CallbackQuery, current_user):
    lang = current_user.language_code or "uz"
    try:
        await callback.message.edit_text(t(lang, "help.calc.info"), reply_markup=help_back_keyboard(lang))
    except Exception:
        await callback.message.answer(t(lang, "help.calc.info"), reply_markup=help_back_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "help:completion")
async def help_completion(callback: CallbackQuery, current_user):
    lang = current_user.language_code or "uz"
    try:
        await callback.message.edit_text(t(lang, "help.complete.info"), reply_markup=help_back_keyboard(lang))
    except Exception:
        await callback.message.answer(t(lang, "help.complete.info"), reply_markup=help_back_keyboard(lang))
    await callback.answer()
