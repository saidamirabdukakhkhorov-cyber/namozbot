from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

router = Router(name="privacy")

TEXT = """Maxfiylik\n\nBiz faqat bot ishlashi uchun kerakli ma'lumotlarni saqlaymiz:\n\n• Telegram ID\n• Tanlangan til\n• Shahar\n• Namoz holatlari\n• Qazo namozlar\n• Eslatma sozlamalari\n\nMa'lumotlaringiz ommaga ko'rsatilmaydi.\nLoglarda shaxsiy ibodat tafsilotlari yozilmaydi."""

@router.callback_query(F.data == "privacy")
async def privacy_cb(callback: CallbackQuery):
    await callback.message.answer(TEXT)
    await callback.answer()

@router.message(F.text.in_({"ℹ️ Yordam", "ℹ️ Помощь", "ℹ️ Help", "/help"}))
async def help_handler(message: Message):
    await message.answer("Botdan command yozmasdan pastki menu orqali foydalanishingiz mumkin. Savollar uchun admin bilan bog'laning.")
