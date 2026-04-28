from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from app.services.i18n import t


def main_menu_keyboard(language: str, is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=t(language, "menu.today")), KeyboardButton(text=t(language, "menu.qazo"))],
        [KeyboardButton(text=t(language, "menu.add_qazo")), KeyboardButton(text=t(language, "menu.calculator"))],
        [KeyboardButton(text=t(language, "menu.stats")), KeyboardButton(text=t(language, "menu.settings"))],
        [KeyboardButton(text=t(language, "menu.help"))],
    ]
    if is_admin:
        rows.append([KeyboardButton(text=t(language, "menu.admin"))])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        input_field_placeholder=t(language, "menu.placeholder"),
    )
