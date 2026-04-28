"""
Telegram Mini App backend.
Serves the static HTML and handles API calls from the web app.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl

from aiohttp import web
from sqlalchemy import func, select, update

from app.core.config import settings
from app.db.models import DailyPrayer, MissedPrayer, ReminderSetting, User
from app.db.repositories.daily_prayers import DailyPrayersRepository
from app.db.repositories.missed_prayers import MissedPrayersRepository
from app.db.repositories.users import UsersRepository
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)
WEBAPP_DIR = Path(__file__).parent.parent / "webapp"
PRAYER_NAMES = ("fajr", "dhuhr", "asr", "maghrib", "isha")


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
            })

        today = date.today()

        # ── Today's prayer statuses ──
        daily_rows = await session.execute(
            select(DailyPrayer.prayer_name, DailyPrayer.status, DailyPrayer.prayer_time)
            .where(DailyPrayer.user_id == user.id, DailyPrayer.prayer_date == today)
        )
        prayers = {}
        prayer_times = {}
        tz = user.timezone or "Asia/Tashkent"
        from zoneinfo import ZoneInfo
        for prayer_name, status, prayer_time in daily_rows:
            prayers[prayer_name] = status
            if prayer_time:
                local_time = prayer_time.astimezone(ZoneInfo(tz))
                prayer_times[prayer_name] = local_time.strftime("%H:%M")

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
            "prayer_times": prayer_times,   # HH:MM strings from DB
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
            raw_date = body.get("date", str(date.today()))
            if prayer in PRAYER_NAMES:
                try:
                    prayer_date = date.fromisoformat(raw_date)
                except ValueError:
                    prayer_date = date.today()
                if prayer_date > date.today():
                    return web.json_response({"error": "future date"}, status=400)
                repo = MissedPrayersRepository(session)
                _, created = await repo.create(
                    user_id=user.id,
                    prayer_name=prayer,
                    prayer_date=prayer_date,
                    source="manual",
                )
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

            today = date.today()
            daily: DailyPrayer | None = await session.scalar(
                select(DailyPrayer).where(
                    DailyPrayer.user_id == user.id,
                    DailyPrayer.prayer_name == prayer,
                    DailyPrayer.prayer_date == today,
                )
            )
            if daily:
                repo = DailyPrayersRepository(session)
                await repo.set_status(daily.id, status)

                # If marked as missed → also add to qazo list
                if status == "missed":
                    missed_repo = MissedPrayersRepository(session)
                    await missed_repo.create(
                        user_id=user.id,
                        prayer_name=prayer,
                        prayer_date=today,
                        source="daily_confirmation",
                        daily_prayer_id=daily.id,
                    )
                await session.commit()
            else:
                # DailyPrayer doesn't exist yet for today — only create if marking missed
                if status == "missed":
                    missed_repo = MissedPrayersRepository(session)
                    await missed_repo.create(
                        user_id=user.id,
                        prayer_name=prayer,
                        prayer_date=today,
                        source="manual",
                    )
                    await session.commit()

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
