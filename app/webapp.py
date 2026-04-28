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
from app.db.models import DailyPrayer, MissedPrayer, ReminderSetting, User
from app.db.repositories.daily_prayers import DailyPrayersRepository
from app.db.repositories.missed_prayers import MissedPrayersRepository
from app.db.repositories.users import UsersRepository
from app.db.repositories.prayer_times import PrayerTimesRepository
from app.services.prayer_times import PrayerTimesService, _extract_times, _parse_hhmm
from app.db.session import AsyncSessionLocal
from app.services.timezone import TASHKENT_TIMEZONE, tashkent_now

logger = logging.getLogger(__name__)
WEBAPP_DIR = Path(__file__).parent.parent / "webapp"
PRAYER_NAMES = ("fajr", "dhuhr", "asr", "maghrib", "isha")
TASHKENT_TZ_NAME = TASHKENT_TIMEZONE


def tashkent_today() -> date:
    """Return current date in GMT+5 / Asia/Tashkent, not server local date."""
    return tashkent_now().date()


def _extract_sunrise_time(raw_payload: dict) -> time | None:
    """Extract sunrise/quyosh from islomapi-compatible raw payload without DB schema changes."""
    try:
        data = _extract_times(raw_payload or {})
        for key in ("quyosh", "sunrise", "Sunrise", "sunrise_time"):
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
        if not user:
            # New user — return empty defaults
            return web.json_response({
                "name": "Foydalanuvchi",
                "city": "Toshkent",
                "lang": "uz",
                "prayers": {},
                "prayer_times": {},
                "qazo": {p: 0 for p in PRAYER_NAMES},
                "stats": {"prayed": 0, "missed": 0, "completed": 0, "active": 0},
                "settings": {"prayer_reminders": True, "qazo_reminders": True},
                "today": tashkent_today().isoformat(),
                "current_time": tashkent_now().strftime("%H:%M"),
                "current_datetime": tashkent_now().isoformat(),
                "next_prayer": None,
                "timezone": TASHKENT_TZ_NAME,
            })

        today = tashkent_today()
        now_tz = tashkent_now()
        tz = TASHKENT_TZ_NAME
        city = user.city or "Toshkent"

        # ── Authoritative prayer times for Mini App and bot sync ──
        prayer_times: dict[str, str] = {}
        prayer_iso_times: dict[str, str] = {}
        try:
            service = PrayerTimesService(PrayerTimesRepository(session))
            dto = await service.get_or_fetch(city, today, tz)
            for name, value in dto.as_dict().items():
                prayer_times[name] = value.strftime("%H:%M")
                prayer_iso_times[name] = _time_to_local_iso(today, value, tz)

            sunrise = _extract_sunrise_time(dto.raw_payload)
            if sunrise:
                prayer_times["sunrise"] = sunrise.strftime("%H:%M")
                prayer_iso_times["sunrise"] = _time_to_local_iso(today, sunrise, tz)

            # Opening the Mini App ensures today's rows exist in the same table the bot reads.
            daily_repo = DailyPrayersRepository(session)
            for prayer_name, value in dto.as_dict().items():
                await daily_repo.upsert_pending(
                    user_id=user.id,
                    prayer_name=prayer_name,
                    prayer_date=today,
                    prayer_time=service.combine(today, value, tz),
                )
            await session.commit()
        except Exception as exc:
            logger.warning("Could not load exact prayer times for mini app: %s", exc)

        # ── Today's prayer statuses from the same table bot uses ──
        daily_rows = await session.execute(
            select(DailyPrayer.prayer_name, DailyPrayer.status, DailyPrayer.prayer_time)
            .where(DailyPrayer.user_id == user.id, DailyPrayer.prayer_date == today)
        )
        prayers = {}
        from zoneinfo import ZoneInfo
        for prayer_name, status, prayer_time in daily_rows:
            prayers[prayer_name] = status
            if prayer_time and prayer_name not in prayer_times:
                local_time = prayer_time.astimezone(ZoneInfo(tz))
                prayer_times[prayer_name] = local_time.strftime("%H:%M")
                prayer_iso_times[prayer_name] = local_time.isoformat()

        next_prayer = _build_next_prayer(prayer_times, now_tz)

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
            "next_prayer": next_prayer,
            "current_time": now_tz.strftime("%H:%M"),
            "current_datetime": now_tz.isoformat(),
            "qazo": qazo,
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
        if not user:
            return web.json_response({"error": "user not found"}, status=404)

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
            if reminder:
                setting_type = body.get("type", "")
                value = bool(body.get("value", True))
                if setting_type == "prayer":
                    reminder.prayer_reminders_enabled = value
                elif setting_type == "qazo":
                    reminder.qazo_reminders_enabled = value
                await session.commit()

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
            daily = await ensure_daily_prayer_row(session, user, prayer, today)

            repo = DailyPrayersRepository(session)
            await repo.set_status(daily.id, status)

            if status == "missed":
                missed_repo = MissedPrayersRepository(session)
                await missed_repo.create(
                    user_id=user.id,
                    prayer_name=prayer,
                    prayer_date=today,
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
                        MissedPrayer.prayer_date == today,
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
