from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from app.bot.keyboards.city import city_keyboard
from app.bot.keyboards.language import language_keyboard
from app.bot.keyboards.main import main_menu_keyboard
from app.db.models import User
from app.db.repositories.states import StatesRepository
from app.db.repositories.users import UsersRepository
from app.services.i18n import t

router = Router(name="start")

@router.message(CommandStart())
async def start(message: Message, current_user: User, is_admin: bool):
    if not current_user.language_code or not current_user.onboarding_completed:
        await message.answer(t("uz", "onboarding.choose_language"), reply_markup=language_keyboard())
        return
    await message.answer(t(current_user.language_code, "dashboard.welcome"), reply_markup=main_menu_keyboard(current_user.language_code, is_admin))

@router.callback_query(F.data.startswith("lang:"))
async def choose_language(callback: CallbackQuery, current_user: User, session):
    language = callback.data.split(":", 1)[1]
    await UsersRepository(session).set_language(current_user.id, language)
    await StatesRepository(session).set(current_user.id, "onboarding_city", {"language": language})
    await callback.message.edit_text(t(language, "onboarding.intro"))
    await callback.message.answer(t(language, "city.choose"), reply_markup=city_keyboard())
    await callback.answer()

@router.callback_query(F.data.startswith("city:"))
async def choose_city(callback: CallbackQuery, current_user: User, session, is_admin: bool):
    city = callback.data.split(":", 1)[1]
    language = current_user.language_code or "uz"
    if city == "other":
        await StatesRepository(session).set(current_user.id, "waiting_custom_city", {})
        await callback.message.answer(t(language, "city.custom_prompt"))
        await callback.answer()
        return
    await UsersRepository(session).set_city(current_user.id, city)
    await UsersRepository(session).complete_onboarding(current_user.id)
    await StatesRepository(session).clear(current_user.id)
    await callback.message.answer(t(language, "onboarding.done", city=city), reply_markup=main_menu_keyboard(language, is_admin))
    await callback.answer()

