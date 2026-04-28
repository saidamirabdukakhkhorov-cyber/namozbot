from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Tilni o'zgartirish", callback_data="settings:language")],
        [InlineKeyboardButton(text="Shaharni o'zgartirish", callback_data="settings:city")],
        [InlineKeyboardButton(text="Namoz eslatmalari", callback_data="settings:prayer_reminders")],
        [InlineKeyboardButton(text="Qazo eslatmalari", callback_data="settings:qazo_reminders")],
        [InlineKeyboardButton(text="Eslatma vaqtlari", callback_data="settings:qazo_times")],
        [InlineKeyboardButton(text="Sokin vaqt", callback_data="settings:quiet_hours")],
        [InlineKeyboardButton(text="Maxfiylik", callback_data="privacy")],
    ])
