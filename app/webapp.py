"""
Telegram Mini App backend.
Serves the static HTML and handles API calls from the web app.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import date, datetime, time, timezone, timedelta
from pathlib import Path
from urllib.parse import parse_qsl

from aiohttp import web
from sqlalchemy import delete, func, select, update

from app.core.config import settings
from app.db.models import DailyPrayer, MissedPrayer, QazoCalculation, ReminderSetting, User
from app.db.repositories.daily_prayers import DailyPrayersRepository
from app.db.repositories.missed_prayers import MissedPrayersRepository
from app.db.repositories.users import UsersRepository
from app.db.repositories.prayer_times import PrayerTimesRepository
from app.db.repositories.qazo_calculations import QazoCalculationsRepository
from app.services.prayer_times import PrayerTimesService, _extract_times, _parse_hhmm
from app.db.session import AsyncSessionLocal
from app.services.timezone import TASHKENT_TIMEZONE, tashkent_now

logger = logging.getLogger(__name__)
WEBAPP_DIR = Path(__file__).parent.parent / "webapp"
PRAYER_NAMES = ("fajr", "dhuhr", "asr", "maghrib", "isha")
PRAYER_LABELS = {"fajr": "Bomdod", "dhuhr": "Peshin", "asr": "Asr", "maghrib": "Shom", "isha": "Xufton"}
TASHKENT_TZ_NAME = TASHKENT_TIMEZONE


def _parse_date(value: str | None, default: date) -> date:
    try:
        return date.fromisoformat(str(value)) if value else default
    except ValueError:
        return default


def _date_range_days(start: date, end: date) -> int:
    return max(0, (end - start).days + 1)


def _calculate_qazo_breakdown(start: date, end: date, prayers: list[str]) -> dict[str, int]:
    days_count = _date_range_days(start, end)
    return {prayer: days_count for prayer in prayers if prayer in PRAYER_NAMES}


def tashkent_today() -> date:
    """Return current date in GMT+5 / Asia/Tashkent, not server local date."""
    return tashkent_now().date()


def _extract_sunrise_time(raw_payload: dict) -> time | None:
    """Extract sunrise/quyosh from islomapi-compatible raw payload without DB schema changes."""
    try:
        data = _extract_times(raw_payload or {})
        for key in ("quyosh", "Quyosh", "kun", "sunrise", "Sunrise", "sunrise_time", "sunriseTime"):
            if key in data and data[key]:
                return _parse_hhmm(data[key])
        lower = {str(k).lower(): v for k, v in data.items()}
        for key in ("quyosh", "sunrise"):
            if lower.get(key):
                return _parse_hhmm(lower[key])
    except Exception as exc:
        logger.warning("Could not extract sunrise time: %s", exc)
    return None


def _time_to_local_iso(day: date, value: time, tz_name: str = TASHKENT_TZ_NAME) -> str:
    from zoneinfo import ZoneInfo
    return datetime.combine(day, value, tzinfo=ZoneInfo(tz_name)).isoformat()


def _build_next_prayer(prayer_times: dict[str, str], now: datetime) -> dict | None:
    order = ("fajr", "sunrise", "dhuhr", "asr", "maghrib", "isha")
    names = {"fajr": "Bomdod", "sunrise": "Quyosh", "dhuhr": "Peshin", "asr": "Asr", "maghrib": "Shom", "isha": "Xufton"}
    now_min = now.hour * 60 + now.minute
    best: tuple[int, str, str] | None = None
    for key in order:
        value = prayer_times.get(key)
        if not value:
            continue
        try:
            hour, minute = [int(x) for x in value.split(":")[:2]]
        except Exception:
            continue
        prayer_min = hour * 60 + minute
        diff = prayer_min - now_min
        if diff <= 0:
            diff += 24 * 60
        if best is None or diff < best[0]:
            best = (diff, key, value)
    if not best:
        return None
    diff, key, value = best
    return {"key": key, "name": names.get(key, key), "time": value, "minutes_left": diff}


def _is_prayer_due(prayer_time: datetime | None, now: datetime | None = None) -> bool:
    """Only allow status changes after the actual prayer time in Asia/Tashkent."""
    if prayer_time is None:
        return False
    now = now or tashkent_now()
    if prayer_time.tzinfo is None:
        prayer_time = prayer_time.replace(tzinfo=timezone.utc)
    return prayer_time.astimezone(now.tzinfo) <= now


def _minutes_until(prayer_time: datetime | None, now: datetime | None = None) -> int | None:
    if prayer_time is None:
        return None
    now = now or tashkent_now()
    if prayer_time.tzinfo is None:
        prayer_time = prayer_time.replace(tzinfo=timezone.utc)
    delta = prayer_time.astimezone(now.tzinfo) - now
    return max(0, int(delta.total_seconds() // 60))


async def ensure_daily_prayer_row(session, user: User, prayer: str, prayer_date: date) -> DailyPrayer:
    """Ensure Mini App writes are visible in bot screens that read daily_prayers."""
    repo = DailyPrayersRepository(session)
    daily = await repo.get(user.id, prayer, prayer_date)
    if daily:
        return daily

    tz = TASHKENT_TZ_NAME
    city = user.city or "Toshkent"
    prayer_dt = datetime.combine(prayer_date, time(0, 0), tzinfo=timezone.utc)
    try:
        service = PrayerTimesService(PrayerTimesRepository(session))
        dto = await service.get_or_fetch(city, prayer_date, tz)
        prayer_dt = service.combine(prayer_date, dto.as_dict()[prayer], tz)
    except Exception as exc:
        logger.warning("Could not resolve prayer time for mini app status update: %s", exc)

    return await repo.upsert_pending(
        user_id=user.id,
        prayer_name=prayer,
        prayer_date=prayer_date,
        prayer_time=prayer_dt,
    )


# ─── AUTH ───

def verify_init_data(init_data: str) -> dict | None:
    """Validate Telegram WebApp initData HMAC signature."""
    if not init_data:
        return None
    try:
        params = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = params.pop("hash", "")
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
        secret_key = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, received_hash):
            return json.loads(params.get("user", "{}"))
        return None
    except Exception:
        return None


def _dev_mode() -> bool:
    return settings.environment not in ("production", "prod")


def resolve_telegram_id(init_data: str, body: dict) -> int | None:
    """Get telegram_id from initData (prod) or body (dev)."""
    user_info = verify_init_data(init_data)
    if user_info:
        return user_info.get("id")
    if _dev_mode():
        return body.get("telegram_id") or None
    return None


# ─── ROUTES ───

async def serve_index(request: web.Request) -> web.Response:
    html_file = WEBAPP_DIR / "index.html"
    if not html_file.exists():
        return web.Response(status=404, text="Mini App not found. Check WEBAPP_DIR path.")
    return web.FileResponse(html_file)


async def api_get_data(request: web.Request) -> web.Response:
    """Return all user data needed by the Mini App."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json"}, status=400)

    telegram_id = resolve_telegram_id(body.get("init_data", ""), body)
    if not telegram_id:
        return web.json_response({"error": "unauthorized"}, status=401)

    async with AsyncSessionLocal() as session:
        user: User | None = await session.scalar(
            select(User).where(User.telegram_id == telegram_id)
        )
        if not user or not user.onboarding_completed:
            return web.json_response({
                "error": "registration_required",
                "message": "Mini Appdan foydalanish uchun avval botda /start bosib, tilni tanlang va rozilik bering.",
            }, status=403)

        today = tashkent_today()
        now_tz = tashkent_now()
        tz = TASHKENT_TZ_NAME
        city = user.city or "Toshkent"
        selected_day = today
        raw_selected_day = body.get("date")
        if raw_selected_day:
            try:
                selected_day = date.fromisoformat(str(raw_selected_day))
            except ValueError:
                selected_day = today
        if selected_day > today:
            selected_day = today
        is_today = selected_day == today

        # ── Authoritative prayer times for Mini App and bot sync ──
        prayer_times: dict[str, str] = {}
        prayer_iso_times: dict[str, str] = {}
        can_mark: dict[str, bool] = {}
        minutes_until: dict[str, int | None] = {}
        try:
            service = PrayerTimesService(PrayerTimesRepository(session))
            dto = await service.get_or_fetch(city, selected_day, tz)
            for name, value in dto.as_dict().items():
                prayer_times[name] = value.strftime("%H:%M")
                prayer_iso_times[name] = _time_to_local_iso(selected_day, value, tz)

            sunrise = _extract_sunrise_time(dto.raw_payload)
            if sunrise:
                prayer_times["sunrise"] = sunrise.strftime("%H:%M")
                prayer_iso_times["sunrise"] = _time_to_local_iso(selected_day, sunrise, tz)

            # Opening the Mini App ensures selected-day rows exist in the same table the bot reads.
            daily_repo = DailyPrayersRepository(session)
            for prayer_name, value in dto.as_dict().items():
                await daily_repo.upsert_pending(
                    user_id=user.id,
                    prayer_name=prayer_name,
                    prayer_date=selected_day,
                    prayer_time=service.combine(selected_day, value, tz),
                )
            await session.commit()
        except Exception as exc:
            logger.warning("Could not load exact prayer times for mini app: %s", exc)

        # ── Today's prayer statuses from the same table bot uses ──
        daily_rows = await session.execute(
            select(DailyPrayer.prayer_name, DailyPrayer.status, DailyPrayer.prayer_time)
            .where(DailyPrayer.user_id == user.id, DailyPrayer.prayer_date == selected_day)
        )
        prayers = {}
        from zoneinfo import ZoneInfo
        for prayer_name, status, prayer_time in daily_rows:
            prayers[prayer_name] = status
            if prayer_time and prayer_name not in prayer_times:
                local_time = prayer_time.astimezone(ZoneInfo(tz))
                prayer_times[prayer_name] = local_time.strftime("%H:%M")
                prayer_iso_times[prayer_name] = local_time.isoformat()
            can_mark[prayer_name] = (not is_today) or _is_prayer_due(prayer_time, now_tz)
            minutes_until[prayer_name] = _minutes_until(prayer_time, now_tz) if is_today else 0

        next_prayer = _build_next_prayer(prayer_times, now_tz) if is_today else None

        # ── Qazo counts per prayer ──
        qazo_rows = await session.execute(
            select(MissedPrayer.prayer_name, func.count())
            .where(MissedPrayer.user_id == user.id, MissedPrayer.status == "active")
            .group_by(MissedPrayer.prayer_name)
        )
        qazo = {p: 0 for p in PRAYER_NAMES}
        for prayer_name, count in qazo_rows:
            if prayer_name in qazo:
                qazo[prayer_name] = int(count)

        total_active = sum(qazo.values())

        detail_rows = (await session.execute(
            select(MissedPrayer.id, MissedPrayer.prayer_name, MissedPrayer.prayer_date, MissedPrayer.source, MissedPrayer.qazo_calculation_id)
            .where(MissedPrayer.user_id == user.id, MissedPrayer.status == "active")
            .order_by(MissedPrayer.prayer_date.asc(), MissedPrayer.created_at.asc())
            .limit(200)
        )).all()
        qazo_details = [
            {"id": int(row_id), "prayer": prayer_name, "label": PRAYER_LABELS.get(prayer_name, prayer_name), "date": prayer_date.isoformat(), "source": source or "manual", "calculation_id": qazo_calculation_id}
            for row_id, prayer_name, prayer_date, source, qazo_calculation_id in detail_rows
        ]

        calc_rows = list((await session.scalars(
            select(QazoCalculation).where(QazoCalculation.user_id == user.id).order_by(QazoCalculation.created_at.desc()).limit(5)
        )).all())
        qazo_calculations = [
            {"id": int(c.id), "start_date": c.start_date.isoformat(), "end_date": c.end_date.isoformat(), "selected_prayers": c.selected_prayers, "days_count": c.days_count, "total_count": c.total_count, "status": c.status, "created_missed_count": c.created_missed_count, "skipped_existing_count": c.skipped_existing_count}
            for c in calc_rows
        ]

        # ── Monthly stats ──
        month_start = date(today.year, today.month, 1)

        prayed_count = int(await session.scalar(
            select(func.count()).select_from(DailyPrayer)
            .where(DailyPrayer.user_id == user.id,
                   DailyPrayer.status == "prayed",
                   DailyPrayer.prayer_date >= month_start)
        ) or 0)

        missed_count = int(await session.scalar(
            select(func.count()).select_from(DailyPrayer)
            .where(DailyPrayer.user_id == user.id,
                   DailyPrayer.status == "missed",
                   DailyPrayer.prayer_date >= month_start)
        ) or 0)

        completed_count = int(await session.scalar(
            select(func.count()).select_from(MissedPrayer)
            .where(MissedPrayer.user_id == user.id,
                   MissedPrayer.status == "completed",
                   MissedPrayer.completed_at >= datetime(today.year, today.month, 1, tzinfo=timezone.utc))
        ) or 0)

        # ── Reminder settings ──
        reminder: ReminderSetting | None = await session.scalar(
            select(ReminderSetting).where(ReminderSetting.user_id == user.id)
        )

        return web.json_response({
            "name": user.full_name or user.username or "Foydalanuvchi",
            "city": user.city or "Toshkent",
            "lang": user.language_code or "uz",
            "prayers": prayers,
            "prayer_times": prayer_times,   # HH:MM strings in Asia/Tashkent
            "prayer_datetimes": prayer_iso_times,
            "can_mark": can_mark,
            "minutes_until": minutes_until,
            "next_prayer": next_prayer,
            "current_time": now_tz.strftime("%H:%M"),
            "current_datetime": now_tz.isoformat(),
            "qazo": qazo,
            "qazo_details": qazo_details,
            "qazo_calculations": qazo_calculations,
            "stats": {
                "prayed": prayed_count,
                "missed": missed_count,
                "completed": completed_count,
                "active": total_active,
            },
            "settings": {
                "prayer_reminders": reminder.prayer_reminders_enabled if reminder else True,
                "qazo_reminders": reminder.qazo_reminders_enabled if reminder else True,
            },
            "today": today.isoformat(),
            "selected_date": selected_day.isoformat(),
            "is_today": is_today,
            "timezone": TASHKENT_TZ_NAME,
        })


async def api_action(request: web.Request) -> web.Response:
    """Handle all write actions from the Mini App."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json"}, status=400)

    telegram_id = resolve_telegram_id(body.get("init_data", ""), body)
    if not telegram_id:
        return web.json_response({"error": "unauthorized"}, status=401)

    action = body.get("action", "")

    async with AsyncSessionLocal() as session:
        user: User | None = await session.scalar(
            select(User).where(User.telegram_id == telegram_id)
        )
        if not user or not user.onboarding_completed:
            return web.json_response({
                "ok": False,
                "error": "registration_required",
                "message": "Mini Appdan foydalanish uchun avval botda /start bosib, tilni tanlang va rozilik bering.",
            }, status=403)

        # ── SET LANGUAGE ──
        if action == "set_lang":
            lang = body.get("lang", "")
            if lang in ("uz", "ru", "en"):
                await UsersRepository(session).set_language(user.id, lang)
                await session.commit()

        # ── SET CITY ──
        elif action == "set_city":
            city = (body.get("city") or "").strip()[:100]
            if city:
                await UsersRepository(session).set_city(user.id, city)
                await session.commit()

        # ── TOGGLE REMINDERS ──
        elif action == "set_setting":
            reminder: ReminderSetting | None = await session.scalar(
                select(ReminderSetting).where(ReminderSetting.user_id == user.id)
            )
            if not reminder:
                reminder = ReminderSetting(user_id=user.id)
                session.add(reminder)
                await session.flush()
            setting_type = body.get("type", "")
            value = bool(body.get("value", True))
            if setting_type == "prayer":
                reminder.prayer_reminders_enabled = value
            elif setting_type == "qazo":
                reminder.qazo_reminders_enabled = value
            else:
                return web.json_response({"ok": False, "message": "unknown setting"}, status=400)
            await session.commit()

        # ── QAZO CALCULATOR PREVIEW ──
        elif action == "calculate_qazo":
            today = tashkent_today()
            start_date = _parse_date(body.get("start_date"), today)
            end_date = _parse_date(body.get("end_date"), today)
            if end_date > today:
                end_date = today
            if start_date > end_date:
                return web.json_response({"ok": False, "message": "Boshlanish sanasi tugash sanasidan katta bo‘lmasin"}, status=400)
            selected = [prayer for prayer in (body.get("prayers") or []) if prayer in PRAYER_NAMES]
            if not selected:
                return web.json_response({"ok": False, "message": "Kamida bitta namozni tanlang"}, status=400)
            days_count = _date_range_days(start_date, end_date)
            if days_count > 36500:
                return web.json_response({"ok": False, "message": "Oraliq juda katta"}, status=400)
            breakdown = _calculate_qazo_breakdown(start_date, end_date, selected)
            existing_rows = await session.execute(
                select(MissedPrayer.prayer_name, func.count())
                .where(MissedPrayer.user_id == user.id, MissedPrayer.status == "active", MissedPrayer.prayer_date >= start_date, MissedPrayer.prayer_date <= end_date, MissedPrayer.prayer_name.in_(selected))
                .group_by(MissedPrayer.prayer_name)
            )
            existing = {prayer: 0 for prayer in selected}
            for prayer_name, count in existing_rows:
                existing[prayer_name] = int(count)
            created = {prayer: max(0, breakdown[prayer] - existing.get(prayer, 0)) for prayer in selected}
            return web.json_response({"ok": True, "start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "days_count": days_count, "breakdown": breakdown, "existing_breakdown": existing, "created_breakdown": created, "total_count": sum(breakdown.values()), "will_create_count": sum(created.values()), "skipped_existing_count": sum(existing.values())})

        # ── QAZO CALCULATOR APPLY ──
        elif action == "apply_qazo_calculation":
            today = tashkent_today()
            start_date = _parse_date(body.get("start_date"), today)
            end_date = _parse_date(body.get("end_date"), today)
            if end_date > today:
                end_date = today
            if start_date > end_date:
                return web.json_response({"ok": False, "message": "Sana oralig‘i noto‘g‘ri"}, status=400)
            selected = [prayer for prayer in (body.get("prayers") or []) if prayer in PRAYER_NAMES]
            if not selected:
                return web.json_response({"ok": False, "message": "Kamida bitta namozni tanlang"}, status=400)
            days_count = _date_range_days(start_date, end_date)
            if days_count > 36500:
                return web.json_response({"ok": False, "message": "Oraliq juda katta"}, status=400)
            breakdown = _calculate_qazo_breakdown(start_date, end_date, selected)
            calc_repo = QazoCalculationsRepository(session)
            calc = await calc_repo.create_calculated(user_id=user.id, start_date=start_date, end_date=end_date, selected_prayers=selected, days_count=days_count, breakdown=breakdown)
            missed_repo = MissedPrayersRepository(session)
            created_breakdown = {prayer: 0 for prayer in selected}
            skipped_breakdown = {prayer: 0 for prayer in selected}
            current_day = start_date
            while current_day <= end_date:
                for prayer in selected:
                    _, created = await missed_repo.create(user_id=user.id, prayer_name=prayer, prayer_date=current_day, source="calculator", qazo_calculation_id=calc.id)
                    if created:
                        created_breakdown[prayer] += 1
                    else:
                        skipped_breakdown[prayer] += 1
                current_day = current_day + timedelta(days=1)
            await calc_repo.mark_applied(calc.id, created_breakdown, skipped_breakdown)
            await session.commit()
            return web.json_response({"ok": True, "calculation_id": int(calc.id), "created_breakdown": created_breakdown, "skipped_breakdown": skipped_breakdown, "created_count": sum(created_breakdown.values()), "skipped_count": sum(skipped_breakdown.values())})

        # ── ADD QAZO ──
        elif action == "add_qazo":
            prayer = body.get("prayer", "")
            raw_date = body.get("date", str(tashkent_today()))
            if prayer in PRAYER_NAMES:
                try:
                    prayer_date = date.fromisoformat(raw_date)
                except ValueError:
                    prayer_date = tashkent_today()
                if prayer_date > tashkent_today():
                    return web.json_response({"error": "future date"}, status=400)
                repo = MissedPrayersRepository(session)
                _, created = await repo.create(
                    user_id=user.id,
                    prayer_name=prayer,
                    prayer_date=prayer_date,
                    source="manual",
                )
                if prayer_date == tashkent_today():
                    daily = await ensure_daily_prayer_row(session, user, prayer, prayer_date)
                    await DailyPrayersRepository(session).set_status(daily.id, "missed")
                await session.commit()
                return web.json_response({"ok": True, "created": created})

        # ── COMPLETE QAZO (mark 1 as done) ──
        elif action == "complete_qazo":
            prayer = body.get("prayer", "")
            count = max(1, min(int(body.get("count", 1)), 10))
            if prayer in PRAYER_NAMES:
                repo = MissedPrayersRepository(session)
                available = await repo.count_by_prayer(user.id, prayer)
                if available <= 0:
                    return web.json_response({"error": "no active qazo"}, status=400)
                actual_count = min(count, available)
                try:
                    await repo.complete_oldest(user_id=user.id, prayer_name=prayer, count=actual_count)
                    await session.commit()
                    return web.json_response({"ok": True, "completed": actual_count})
                except ValueError as e:
                    return web.json_response({"error": str(e)}, status=400)

        # ── UPDATE TODAY'S PRAYER STATUS ──
        elif action == "set_prayer_status":
            prayer = body.get("prayer", "")
            status = body.get("status", "")
            if prayer not in PRAYER_NAMES or status not in ("prayed", "missed", "pending"):
                return web.json_response({"error": "invalid params"}, status=400)

            today = tashkent_today()
            raw_date = body.get("date", today.isoformat())
            try:
                prayer_date = date.fromisoformat(str(raw_date))
            except ValueError:
                prayer_date = today
            if prayer_date > today:
                return web.json_response({"error": "future_date", "message": "Kelajakdagi kunni belgilab bo‘lmaydi"}, status=400)
            daily = await ensure_daily_prayer_row(session, user, prayer, prayer_date)
            if prayer_date == today and status in ("prayed", "missed") and not _is_prayer_due(daily.prayer_time, tashkent_now()):
                return web.json_response({"error": "future_prayer", "message": "Bu namoz vaqti hali kirmagan"}, status=400)

            repo = DailyPrayersRepository(session)
            await repo.set_status(daily.id, status)

            if status == "missed":
                missed_repo = MissedPrayersRepository(session)
                await missed_repo.create(
                    user_id=user.id,
                    prayer_name=prayer,
                    prayer_date=prayer_date,
                    source="daily_confirmation",
                    daily_prayer_id=daily.id,
                )
            elif status == "prayed":
                # If the user changes an earlier "missed" status to "prayed",
                # remove the qazo row that was created by daily confirmation.
                await session.execute(
                    delete(MissedPrayer).where(
                        MissedPrayer.user_id == user.id,
                        MissedPrayer.prayer_name == prayer,
                        MissedPrayer.prayer_date == prayer_date,
                        MissedPrayer.status == "active",
                        MissedPrayer.source == "daily_confirmation",
                    )
                )

            await session.commit()
            return web.json_response({"ok": True})

    return web.json_response({"ok": True})


def create_webapp() -> web.Application:
    app = web.Application()
    # Telegram opens WEBAPP_URL directly (root "/"), so serve index.html at "/"
    app.router.add_get("/", serve_index)
    app.router.add_get("/webapp", serve_index)
    app.router.add_get("/webapp/", serve_index)
    # API endpoints at both root and /webapp prefix
    app.router.add_post("/api/data", api_get_data)
    app.router.add_post("/api/action", api_action)
    app.router.add_post("/webapp/api/data", api_get_data)
    app.router.add_post("/webapp/api/action", api_action)
    return app
