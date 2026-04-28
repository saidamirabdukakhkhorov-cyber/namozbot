from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Dashboard", callback_data="admin:dashboard")],
        [InlineKeyboardButton(text="Users", callback_data="admin:users")],
        [InlineKeyboardButton(text="Broadcast", callback_data="admin:broadcast")],
        [InlineKeyboardButton(text="Reminder logs", callback_data="admin:reminders")],
        [InlineKeyboardButton(text="Prayer times cache", callback_data="admin:prayer_cache")],
        [InlineKeyboardButton(text="Admin actions", callback_data="admin:actions")],
        [InlineKeyboardButton(text="Back to user menu", callback_data="dashboard")],
    ])
