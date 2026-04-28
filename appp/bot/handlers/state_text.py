from datetime import date
from aiogram import Router
from aiogram.types import Message
from app.bot.keyboards.qazo import undo_keyboard
from app.bot.keyboards.qazo_calculator import calculator_prayers_keyboard
from app.bot.handlers.qazo import source_values
from app.core.constants import PRAYER_NAMES
from app.db.repositories.missed_prayers import MissedPrayersRepository
from app.db.repositories.states import StatesRepository
from app.db.repositories.users import UsersRepository
from app.services.i18n import prayer_label, t

router = Router(name="state_text")

@router.message()
async def state_text_handler(message: Message, current_user, session, is_admin: bool):
    state = await StatesRepository(session).get(current_user.id)
    if not state:
        return
    text = (message.text or "").strip()

    if state.state == "waiting_custom_city":
        city = text[:120]
        await UsersRepository(session).set_city(current_user.id, city)
        await UsersRepository(session).complete_onboarding(current_user.id)
        await StatesRepository(session).clear(current_user.id)
        await message.answer(t(current_user.language_code, "onboarding.done", city=city))
        return

    if state.state == "waiting_qazo_custom_date":
        prayer = state.payload["prayer"]
        try:
            day = date.fromisoformat(text)
        except ValueError:
            await message.answer("Iltimos, sanani YYYY-MM-DD formatida kiriting.")
            return
        _, created = await MissedPrayersRepository(session).create(user_id=current_user.id, prayer_name=prayer, prayer_date=day, source="manual")
        await StatesRepository(session).clear(current_user.id)
        await message.answer("Qazo qo'shildi." if created else "Bu qazo ro'yxatda allaqachon bor.")
        return

    if state.state == "waiting_qazo_complete_count":
        try:
            count = int(text)
            if count <= 0:
                raise ValueError
        except ValueError:
            await message.answer("Iltimos, son kiriting. Masalan: 2")
            return
        source_key = state.payload["source_key"]; prayer = state.payload["prayer"]
        max_count = await MissedPrayersRepository(session).count_by_prayer(current_user.id, prayer, source_values(source_key))
        if count > max_count:
            await message.answer(f"Sizda active {prayer_label(current_user.language_code, prayer)} qazolari: {max_count} ta.")
            return
        action = await MissedPrayersRepository(session).complete_oldest(current_user.id, prayer, count, source_values(source_key))
        await StatesRepository(session).clear(current_user.id)
        await message.answer(f"✅ Belgilandi\n\n{count} ta {prayer_label(current_user.language_code, prayer)} ado qilingan deb belgilandi.", reply_markup=undo_keyboard(action.id))
        return

    if state.state.startswith("calc_waiting"):
        payload = state.payload or {}
        try:
            if state.state == "calc_waiting_start_date":
                payload["start_date"] = date.fromisoformat(text).isoformat()
                await StatesRepository(session).set(current_user.id, "calc_waiting_end_date", payload)
                await message.answer("Boshlanish sanasi saqlandi. Endi tugash sanasini yozing.")
                return
            if state.state == "calc_waiting_end_date":
                payload["end_date"] = date.fromisoformat(text).isoformat()
            elif state.state == "calc_waiting_start_year":
                year = int(text)
                payload["start_date"] = date(year, 1, 1).isoformat()
                await StatesRepository(session).set(current_user.id, "calc_waiting_end_year", payload)
                await message.answer("Tugash yilini yozing.")
                return
            elif state.state == "calc_waiting_end_year":
                payload["end_date"] = date(int(text), 12, 31).isoformat()
            elif state.state == "calc_waiting_start_month":
                y, m = map(int, text.split("-"))
                payload["start_date"] = date(y, m, 1).isoformat()
                await StatesRepository(session).set(current_user.id, "calc_waiting_end_month", payload)
                await message.answer("Tugash oyini YYYY-MM formatida yozing.")
                return
            elif state.state == "calc_waiting_end_month":
                y, m = map(int, text.split("-"))
                next_y, next_m = (y + 1, 1) if m == 12 else (y, m + 1)
                payload["end_date"] = date.fromordinal(date(next_y, next_m, 1).toordinal() - 1).isoformat()
        except Exception:
            await message.answer("Format noto'g'ri. Iltimos qayta kiriting.")
            return
        payload["selected_prayers"] = []
        await StatesRepository(session).set(current_user.id, "calc_select_prayers", payload)
        await message.answer("Qaysi namozlarni hisoblaymiz?", reply_markup=calculator_prayers_keyboard(current_user.language_code, []))
        return
