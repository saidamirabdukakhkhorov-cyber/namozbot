from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

CITIES = ["Toshkent", "Samarqand", "Buxoro", "Andijon", "Farg'ona", "Namangan", "Qarshi", "Nukus"]

def city_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(CITIES), 2):
        rows.append([InlineKeyboardButton(text=c, callback_data=f"city:{c}") for c in CITIES[i:i+2]])
    rows.append([InlineKeyboardButton(text="Boshqa shahar", callback_data="city:other")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
