from aiogram import F, Router
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


@router.message(F.text.in_({"ℹ️ Yordam", "ℹ️ Помощь", "ℹ️ Help", "/help"}))
async def help_handler(message: Message, current_user):
    lang = current_user.language_code or "uz"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "help.calc"), callback_data="calc:start")],
        [InlineKeyboardButton(text=t(lang, "help.complete"), callback_data="qazo_complete:start")],
        [InlineKeyboardButton(text=t(lang, "common.home"), callback_data="dashboard")],
    ])
    await message.answer(t(lang, "help.text"), reply_markup=keyboard)
