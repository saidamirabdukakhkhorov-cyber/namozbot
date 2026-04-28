from datetime import date, timedelta
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from app.bot.keyboards.prayer import prayer_select_keyboard
from app.bot.keyboards.qazo import qazo_add_date_keyboard, qazo_complete_count_keyboard, qazo_complete_prayers_keyboard, qazo_complete_source_keyboard, qazo_overview_keyboard, undo_keyboard
from app.bot.keyboards.qazo_calculator import calculator_start_keyboard
from app.core.constants import ALL_QAZO_SOURCES, CURRENT_QAZO_SOURCES, PRAYER_NAMES
from app.db.models import User
from app.db.repositories.missed_prayers import MissedPrayersRepository
from app.db.repositories.states import StatesRepository
from app.services.date_periods import current_month_range
from app.services.i18n import prayer_label, t

router = Router(name="qazo")

def source_values(source_key: str):
    if source_key == "current":
        return list(CURRENT_QAZO_SOURCES)
    if source_key == "calculator":
        return ["calculator"]
    return list(ALL_QAZO_SOURCES)

async def render_qazo_overview(user: User, session) -> str:
    lang = user.language_code
    start, end = current_month_range()
    repo = MissedPrayersRepository(session)
    current = await repo.summary(user.id, start, end, CURRENT_QAZO_SOURCES)
    calculator = await repo.total_active(user.id, ["calculator"])
    all_active = await repo.total_active(user.id)
    lines = ["📌 Qazo namozlarim", "", f"Davr: Shu oy ({start} — {end})", f"Joriy davrdagi active qazolar: {sum(current.values())} ta", ""]
    for p in PRAYER_NAMES:
        lines.append(f"{prayer_label(lang, p)}: {current.get(p, 0)} ta")
    lines += ["", f"Kalkulyator orqali qo'shilgan active qazolar: {calculator} ta", f"Jami active qazo: {all_active} ta"]
    return "\n".join(lines)

@router.message(Command("qazo"))
@router.message(F.text.in_({"📌 Qazo namozlarim", "📌 Мои каза-намазы", "📌 My missed prayers"}))
async def qazo_menu(message: Message, current_user: User, session):
    await message.answer(await render_qazo_overview(current_user, session), reply_markup=qazo_overview_keyboard(current_user.language_code))

@router.callback_query(F.data == "qazo:overview")
async def qazo_menu_cb(callback: CallbackQuery, current_user: User, session):
    await callback.message.answer(await render_qazo_overview(current_user, session), reply_markup=qazo_overview_keyboard(current_user.language_code))
    await callback.answer()


@router.callback_query(F.data == "qazo:calculator_section")
async def qazo_calculator_section(callback: CallbackQuery, current_user: User):
    await callback.message.answer(
        "🧮 Qazo kalkulyator\n\nDavrni qanday tanlaysiz?",
        reply_markup=calculator_start_keyboard(current_user.language_code),
    )
    await callback.answer()


@router.callback_query(F.data == "qazo:all")
async def qazo_all(callback: CallbackQuery, current_user: User, session):
    counts = await MissedPrayersRepository(session).summary(current_user.id)
    lines = ["📋 Barcha active qazolar", ""]
    for p in PRAYER_NAMES:
        lines.append(f"{prayer_label(current_user.language_code, p)}: {counts.get(p, 0)} ta")
    lines.append("")
    lines.append(f"Jami: {sum(counts.values())} ta")
    await callback.message.answer("\n".join(lines), reply_markup=qazo_overview_keyboard(current_user.language_code))
    await callback.answer()


@router.callback_query(F.data == "qazo:period")
async def qazo_period_placeholder(callback: CallbackQuery):
    await callback.message.answer("Davrni o'zgartirish bo'limi keyingi versiyada kengaytiriladi. Hozircha umumiy ro'yxat va shu oy statistikasi ishlaydi.")
    await callback.answer()


@router.callback_query(F.data == "back")
async def qazo_back(callback: CallbackQuery, current_user: User, session):
    await callback.message.answer(await render_qazo_overview(current_user, session), reply_markup=qazo_overview_keyboard(current_user.language_code))
    await callback.answer()

@router.message(F.text.in_({"➕ Qazo qo'shish", "➕ Добавить каза", "➕ Add missed prayer"}))
@router.callback_query(F.data == "qazo_add:start")
async def qazo_add_start(event, current_user: User):
    target = event.message if isinstance(event, CallbackQuery) else event
    await target.answer("Qaysi namoz qazo bo'lgan?", reply_markup=prayer_select_keyboard(current_user.language_code, "qazo_add_prayer"))
    if isinstance(event, CallbackQuery):
        await event.answer()

@router.callback_query(F.data.startswith("qazo_add_prayer:"))
async def qazo_add_prayer(callback: CallbackQuery, current_user: User):
    prayer = callback.data.split(":", 1)[1]
    await callback.message.answer("Qaysi sana uchun?", reply_markup=qazo_add_date_keyboard(current_user.language_code, prayer))
    await callback.answer()

@router.callback_query(F.data.startswith("qazo_add_date:"))
async def qazo_add_date(callback: CallbackQuery, current_user: User, session):
    _, prayer, raw_day = callback.data.split(":")
    if raw_day == "custom":
        await StatesRepository(session).set(current_user.id, "waiting_qazo_custom_date", {"prayer": prayer})
        await callback.message.answer("Sanani YYYY-MM-DD formatida yozing. Masalan: 2026-04-25")
        await callback.answer()
        return
    day = date.today() if raw_day == "today" else date.today() - timedelta(days=1)
    _, created = await MissedPrayersRepository(session).create(user_id=current_user.id, prayer_name=prayer, prayer_date=day, source="manual")
    msg = f"{prayer_label(current_user.language_code, prayer)} qazo namozi qo'shildi.\nSana: {day}" if created else f"Bu sana uchun {prayer_label(current_user.language_code, prayer)} qazo namozi allaqachon ro'yxatda bor."
    await callback.message.answer(msg)
    await callback.answer()

@router.callback_query(F.data == "qazo_complete:start")
async def qazo_complete_start(callback: CallbackQuery, current_user: User, session):
    repo = MissedPrayersRepository(session)
    current = await repo.total_active(current_user.id, CURRENT_QAZO_SOURCES)
    calc = await repo.total_active(current_user.id, ["calculator"])
    total = await repo.total_active(current_user.id)
    await callback.message.answer(f"✅ Qazo ado qilish\n\nJoriy qazolar: {current} ta\nKalkulyator qazolari: {calc} ta\nBarcha active qazolar: {total} ta", reply_markup=qazo_complete_source_keyboard(current_user.language_code))
    await callback.answer()

@router.callback_query(F.data.startswith("qazo_complete_source:"))
async def qazo_complete_source(callback: CallbackQuery, current_user: User, session):
    source_key = callback.data.split(":", 1)[1]
    counts = await MissedPrayersRepository(session).summary(current_user.id, sources=source_values(source_key))
    if sum(counts.values()) == 0:
        await callback.message.answer("Sizda hozircha active qazo namoz yo'q 🌿")
    else:
        await callback.message.answer("Qaysi namozdan qazo ado qildingiz?", reply_markup=qazo_complete_prayers_keyboard(current_user.language_code, counts, source_key))
    await callback.answer()

@router.callback_query(F.data.startswith("qazo_complete_prayer:"))
async def qazo_complete_prayer(callback: CallbackQuery, current_user: User, session):
    _, source_key, prayer = callback.data.split(":")
    count = await MissedPrayersRepository(session).count_by_prayer(current_user.id, prayer, source_values(source_key))
    await callback.message.answer(f"Nechta {prayer_label(current_user.language_code, prayer)} qazo namozini ado qildingiz?\n\nActive: {count} ta", reply_markup=qazo_complete_count_keyboard(current_user.language_code, source_key, prayer, count))
    await callback.answer()

@router.callback_query(F.data.startswith("qazo_complete_count:"))
async def qazo_complete_count(callback: CallbackQuery, current_user: User, session):
    _, source_key, prayer, raw_count = callback.data.split(":")
    try:
        count = int(raw_count)
        action = await MissedPrayersRepository(session).complete_oldest(current_user.id, prayer, count, source_values(source_key))
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    remaining = await MissedPrayersRepository(session).count_by_prayer(current_user.id, prayer, source_values(source_key))
    await callback.message.answer(f"✅ Belgilandi\n\n{count} ta {prayer_label(current_user.language_code, prayer)} qazo namozi ado qilingan deb belgilandi.\n\nQolgan: {remaining} ta", reply_markup=undo_keyboard(action.id))
    await callback.answer()

@router.callback_query(F.data.startswith("qazo_complete_custom:"))
async def qazo_complete_custom(callback: CallbackQuery, current_user: User, session):
    _, source_key, prayer = callback.data.split(":")
    await StatesRepository(session).set(current_user.id, "waiting_qazo_complete_count", {"source_key": source_key, "prayer": prayer})
    await callback.message.answer(f"Nechta {prayer_label(current_user.language_code, prayer)} qazo namozini ado qilganingizni yozing.")
    await callback.answer()


@router.callback_query(F.data.startswith("undo_completion:"))
async def undo_completion(callback: CallbackQuery, current_user: User, session):
    action_id = int(callback.data.split(":", 1)[1])
    action = await MissedPrayersRepository(session).undo_completion_action(current_user.id, action_id)
    if not action:
        await callback.answer("Bekor qilib bo'lmadi", show_alert=True)
        return
    await callback.message.answer("Bekor qilindi. Qazolar yana active holatga qaytarildi.")
    await callback.answer()
