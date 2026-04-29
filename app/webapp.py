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
from sqlalchemy import delete, func, select, text, update

from app.core.config import settings
from app.db.models import DailyPrayer, MissedPrayer, QazoCalculation, QazoCompletionAction, QazoPlan, ReminderSetting, User
from app.db.repositories.daily_prayers import DailyPrayersRepository
from app.db.repositories.missed_prayers import MissedPrayersRepository
from app.db.repositories.users import UsersRepository
from app.db.repositories.prayer_times import PrayerTimesRepository
from app.db.repositories.qazo_calculations import QazoCalculationsRepository
from app.services.prayer_times import ISLOMAPI_REGIONS, PrayerTimesService, _extract_times, _parse_hhmm, _region_for_islomapi
from app.db.session import AsyncSessionLocal
from app.services.timezone import TASHKENT_TIMEZONE, tashkent_now

logger = logging.getLogger(__name__)
WEBAPP_DIR = Path(__file__).parent.parent / "webapp"
DAILY_PRAYER_NAMES = ("fajr", "dhuhr", "asr", "maghrib", "isha")
QAZO_PRAYER_NAMES = ("fajr", "dhuhr", "asr", "maghrib", "isha", "witr")
PRAYER_NAMES = QAZO_PRAYER_NAMES
PRAYER_LABELS = {"fajr": "Bomdod", "dhuhr": "Peshin", "asr": "Asr", "maghrib": "Shom", "isha": "Xufton", "witr": "Vitr"}
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
    return {prayer: days_count for prayer in prayers if prayer in QAZO_PRAYER_NAMES}


def _default_qazo_targets() -> dict[str, int]:
    return {"fajr": 1, "dhuhr": 1, "asr": 1, "maghrib": 1, "isha": 1, "witr": 0}


def _normalize_qazo_targets(raw: dict | None) -> dict[str, int]:
    raw = raw or {}
    result: dict[str, int] = {}
    for prayer in QAZO_PRAYER_NAMES:
        try:
            result[prayer] = max(0, min(int(raw.get(prayer, 0)), 99))
        except Exception:
            result[prayer] = 0
    return result


async def get_or_create_qazo_plan(session, user_id: int) -> QazoPlan:
    plan = await session.scalar(select(QazoPlan).where(QazoPlan.user_id == user_id))
    if plan:
        # make old rows forward-compatible when Vitr was added later
        plan.daily_targets = {**_default_qazo_targets(), **_normalize_qazo_targets(plan.daily_targets)}
        return plan
    plan = QazoPlan(user_id=user_id, enabled=True, mode="balanced", daily_targets=_default_qazo_targets(), preferred_times=[])
    session.add(plan)
    await session.flush()
    return plan


def _qazo_plan_payload(plan: QazoPlan, active_qazo: dict[str, int], completed_today: dict[str, int]) -> dict:
    targets = _normalize_qazo_targets(plan.daily_targets)
    tasks = {}
    total_target = 0
    total_done = 0
    for prayer in QAZO_PRAYER_NAMES:
        active = int(active_qazo.get(prayer, 0) or 0)
        target = int(targets.get(prayer, 0) or 0) if plan.enabled else 0
        target = min(target, active + int(completed_today.get(prayer, 0) or 0))
        done = int(completed_today.get(prayer, 0) or 0)
        tasks[prayer] = {
            "target": target,
            "done": done,
            "left": max(0, target - done),
            "active": active,
        }
        total_target += target
        total_done += done
    return {
        "enabled": bool(plan.enabled),
        "mode": plan.mode or "custom",
        "daily_targets": targets,
        "tasks": tasks,
        "today_target": total_target,
        "today_done": total_done,
        "today_left": max(0, total_target - total_done),
    }

async def _execute_schema_statement(session, stmt) -> None:
    """Run one schema self-heal DDL statement without poisoning the request transaction.

    SQLAlchemy ``text()`` treats JSON colons like ``{"fajr":1}`` as bind
    parameters (``:1``), which broke the production qazo_plans self-heal and
    left the table uncreated. DDL here is static app-owned SQL, so execute the
    raw driver SQL directly to avoid bind parsing.
    """
    try:
        raw_sql = getattr(stmt, "text", None) or str(stmt)
        conn = await session.connection()
        await conn.exec_driver_sql(raw_sql)
        await session.commit()
    except Exception as exc:
        logger.warning("schema self-heal statement skipped: %s", exc)
        await session.rollback()


async def _get_user_snapshot(session, telegram_id: int) -> dict | None:
    """Read only primitive user fields the Mini App needs."""
    row = (await session.execute(text("""
        SELECT id, telegram_id, username, full_name, language_code, city, timezone, onboarding_completed
        FROM users
        WHERE telegram_id = :telegram_id
        LIMIT 1
    """), {"telegram_id": telegram_id})).mappings().first()
    return dict(row) if row else None


def _zero_qazo() -> dict[str, int]:
    return {p: 0 for p in QAZO_PRAYER_NAMES}


def _safe_iso_date(value) -> str | None:
    try:
        return value.isoformat() if value else None
    except Exception:
        return None


def _safe_json_value(value, fallback):
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return fallback
    return value


async def ensure_qazo_schema(session) -> None:
    """Ensure Mini App qazo tables exist even if Alembic was not run yet."""
    try:
        dialect = session.get_bind().dialect.name
    except Exception:
        dialect = "postgresql"
    if dialect != "postgresql":
        return

    # Core Mini App tables/columns. Production can be on an older DB if
    # migrations were skipped, so the web app self-heals instead of returning
    # HTTP 500 to users.
    await _execute_schema_statement(session, text("""
    CREATE TABLE IF NOT EXISTS users (
        id BIGSERIAL PRIMARY KEY,
        telegram_id BIGINT NOT NULL UNIQUE,
        username VARCHAR(255) NULL,
        full_name VARCHAR(255) NULL,
        language_code VARCHAR(5) NOT NULL DEFAULT 'uz',
        city VARCHAR(120) NULL,
        timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Tashkent',
        is_active BOOLEAN NOT NULL DEFAULT true,
        onboarding_completed BOOLEAN NOT NULL DEFAULT false,
        last_activity_at TIMESTAMPTZ NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS username VARCHAR(255) NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255) NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS language_code VARCHAR(5) NOT NULL DEFAULT 'uz'"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS city VARCHAR(120) NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Tashkent'"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS onboarding_completed BOOLEAN NOT NULL DEFAULT false"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMPTZ NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"))
    await _execute_schema_statement(session, text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_telegram_id_unique ON users (telegram_id)"))
    await _execute_schema_statement(session, text("CREATE INDEX IF NOT EXISTS ix_users_city ON users (city)"))

    await _execute_schema_statement(session, text("""
    CREATE TABLE IF NOT EXISTS user_preferences (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
        language VARCHAR(5) NOT NULL DEFAULT 'uz',
        date_format VARCHAR(20) NOT NULL DEFAULT 'YYYY-MM-DD',
        main_menu_style VARCHAR(30) NOT NULL DEFAULT 'reply_keyboard',
        show_daily_summary BOOLEAN NOT NULL DEFAULT true,
        show_weekly_summary BOOLEAN NOT NULL DEFAULT true,
        quiet_hours_enabled BOOLEAN NOT NULL DEFAULT true,
        quiet_hours_start TIME NOT NULL DEFAULT '23:00',
        quiet_hours_end TIME NOT NULL DEFAULT '06:00',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS user_preferences ADD COLUMN IF NOT EXISTS user_id BIGINT NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS user_preferences ADD COLUMN IF NOT EXISTS language VARCHAR(5) NOT NULL DEFAULT 'uz'"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS user_preferences ADD COLUMN IF NOT EXISTS date_format VARCHAR(20) NOT NULL DEFAULT 'YYYY-MM-DD'"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS user_preferences ADD COLUMN IF NOT EXISTS main_menu_style VARCHAR(30) NOT NULL DEFAULT 'reply_keyboard'"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS user_preferences ADD COLUMN IF NOT EXISTS show_daily_summary BOOLEAN NOT NULL DEFAULT true"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS user_preferences ADD COLUMN IF NOT EXISTS show_weekly_summary BOOLEAN NOT NULL DEFAULT true"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS user_preferences ADD COLUMN IF NOT EXISTS quiet_hours_enabled BOOLEAN NOT NULL DEFAULT true"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS user_preferences ADD COLUMN IF NOT EXISTS quiet_hours_start TIME NOT NULL DEFAULT '23:00'"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS user_preferences ADD COLUMN IF NOT EXISTS quiet_hours_end TIME NOT NULL DEFAULT '06:00'"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS user_preferences ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS user_preferences ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"))
    await _execute_schema_statement(session, text("CREATE UNIQUE INDEX IF NOT EXISTS ix_user_preferences_user_id_unique ON user_preferences (user_id) WHERE user_id IS NOT NULL"))

    await _execute_schema_statement(session, text("""
    CREATE TABLE IF NOT EXISTS reminder_settings (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
        prayer_reminders_enabled BOOLEAN NOT NULL DEFAULT true,
        qazo_reminders_enabled BOOLEAN NOT NULL DEFAULT true,
        qazo_reminder_times JSONB NOT NULL DEFAULT '["08:00", "21:00"]'::jsonb,
        daily_qazo_limit INTEGER NOT NULL DEFAULT 1,
        quiet_hours_enabled BOOLEAN NOT NULL DEFAULT true,
        quiet_hours_start TIME NOT NULL DEFAULT '23:00',
        quiet_hours_end TIME NOT NULL DEFAULT '06:00',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS reminder_settings ADD COLUMN IF NOT EXISTS user_id BIGINT NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS reminder_settings ADD COLUMN IF NOT EXISTS prayer_reminders_enabled BOOLEAN NOT NULL DEFAULT true"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS reminder_settings ADD COLUMN IF NOT EXISTS qazo_reminders_enabled BOOLEAN NOT NULL DEFAULT true"))
    await _execute_schema_statement(session, text("""ALTER TABLE IF EXISTS reminder_settings ADD COLUMN IF NOT EXISTS qazo_reminder_times JSONB NOT NULL DEFAULT '["08:00", "21:00"]'::jsonb"""))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS reminder_settings ADD COLUMN IF NOT EXISTS daily_qazo_limit INTEGER NOT NULL DEFAULT 1"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS reminder_settings ADD COLUMN IF NOT EXISTS quiet_hours_enabled BOOLEAN NOT NULL DEFAULT true"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS reminder_settings ADD COLUMN IF NOT EXISTS quiet_hours_start TIME NOT NULL DEFAULT '23:00'"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS reminder_settings ADD COLUMN IF NOT EXISTS quiet_hours_end TIME NOT NULL DEFAULT '06:00'"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS reminder_settings ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS reminder_settings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"))

    await _execute_schema_statement(session, text("""
    CREATE TABLE IF NOT EXISTS prayer_times (
        id BIGSERIAL PRIMARY KEY,
        city VARCHAR(120) NOT NULL,
        prayer_date DATE NOT NULL,
        timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Tashkent',
        fajr_time TIME NOT NULL,
        dhuhr_time TIME NOT NULL,
        asr_time TIME NOT NULL,
        maghrib_time TIME NOT NULL,
        isha_time TIME NOT NULL,
        source VARCHAR(40) NOT NULL DEFAULT 'external',
        raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS prayer_times ADD COLUMN IF NOT EXISTS city VARCHAR(120) NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS prayer_times ADD COLUMN IF NOT EXISTS prayer_date DATE NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS prayer_times ADD COLUMN IF NOT EXISTS fajr_time TIME NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS prayer_times ADD COLUMN IF NOT EXISTS dhuhr_time TIME NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS prayer_times ADD COLUMN IF NOT EXISTS asr_time TIME NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS prayer_times ADD COLUMN IF NOT EXISTS maghrib_time TIME NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS prayer_times ADD COLUMN IF NOT EXISTS isha_time TIME NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS prayer_times ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Tashkent'"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS prayer_times ADD COLUMN IF NOT EXISTS source VARCHAR(40) NOT NULL DEFAULT 'external'"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS prayer_times ADD COLUMN IF NOT EXISTS raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS prayer_times ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS prayer_times ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"))
    await _execute_schema_statement(session, text('CREATE INDEX IF NOT EXISTS ix_prayer_times_city_date ON prayer_times (city, prayer_date)'))

    await _execute_schema_statement(session, text("""
    CREATE TABLE IF NOT EXISTS daily_prayers (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        prayer_name VARCHAR(20) NOT NULL,
        prayer_date DATE NOT NULL,
        prayer_time TIMESTAMPTZ NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        snooze_until TIMESTAMPTZ NULL,
        answered_at TIMESTAMPTZ NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS daily_prayers ADD COLUMN IF NOT EXISTS user_id BIGINT NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS daily_prayers ADD COLUMN IF NOT EXISTS prayer_name VARCHAR(20) NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS daily_prayers ADD COLUMN IF NOT EXISTS prayer_date DATE NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS daily_prayers ADD COLUMN IF NOT EXISTS prayer_time TIMESTAMPTZ NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS daily_prayers ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'pending'"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS daily_prayers ADD COLUMN IF NOT EXISTS snooze_until TIMESTAMPTZ NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS daily_prayers ADD COLUMN IF NOT EXISTS answered_at TIMESTAMPTZ NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS daily_prayers ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS daily_prayers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"))
    await _execute_schema_statement(session, text('CREATE INDEX IF NOT EXISTS ix_daily_prayers_user_date ON daily_prayers (user_id, prayer_date)'))
    await _execute_schema_statement(session, text('CREATE INDEX IF NOT EXISTS ix_daily_prayers_user_status ON daily_prayers (user_id, status)'))

    await _execute_schema_statement(session, text("""
    CREATE TABLE IF NOT EXISTS qazo_calculations (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        start_date DATE NOT NULL,
        end_date DATE NOT NULL,
        selected_prayers JSONB NOT NULL,
        days_count INTEGER NOT NULL,
        prayers_count INTEGER NOT NULL,
        total_count INTEGER NOT NULL,
        breakdown JSONB NOT NULL,
        created_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
        skipped_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
        status VARCHAR(20) NOT NULL DEFAULT 'calculated',
        created_missed_count INTEGER NOT NULL DEFAULT 0,
        skipped_existing_count INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        applied_at TIMESTAMPTZ NULL
    )
    """))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_calculations ADD COLUMN IF NOT EXISTS user_id BIGINT NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_calculations ADD COLUMN IF NOT EXISTS start_date DATE NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_calculations ADD COLUMN IF NOT EXISTS end_date DATE NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_calculations ADD COLUMN IF NOT EXISTS selected_prayers JSONB NOT NULL DEFAULT '[]'::jsonb"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_calculations ADD COLUMN IF NOT EXISTS days_count INTEGER NOT NULL DEFAULT 0"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_calculations ADD COLUMN IF NOT EXISTS prayers_count INTEGER NOT NULL DEFAULT 0"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_calculations ADD COLUMN IF NOT EXISTS total_count INTEGER NOT NULL DEFAULT 0"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_calculations ADD COLUMN IF NOT EXISTS breakdown JSONB NOT NULL DEFAULT '{}'::jsonb"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_calculations ADD COLUMN IF NOT EXISTS created_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_calculations ADD COLUMN IF NOT EXISTS skipped_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_calculations ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'calculated'"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_calculations ADD COLUMN IF NOT EXISTS created_missed_count INTEGER NOT NULL DEFAULT 0"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_calculations ADD COLUMN IF NOT EXISTS skipped_existing_count INTEGER NOT NULL DEFAULT 0"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_calculations ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_calculations ADD COLUMN IF NOT EXISTS applied_at TIMESTAMPTZ NULL"))
    await _execute_schema_statement(session, text('CREATE INDEX IF NOT EXISTS ix_qazo_calc_user_created ON qazo_calculations (user_id, created_at)'))

    await _execute_schema_statement(session, text("""
    CREATE TABLE IF NOT EXISTS qazo_plans (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
        enabled BOOLEAN NOT NULL DEFAULT true,
        mode VARCHAR(30) NOT NULL DEFAULT 'custom',
        daily_targets JSONB NOT NULL DEFAULT '{"fajr":1,"dhuhr":1,"asr":1,"maghrib":1,"isha":1,"witr":0}'::jsonb,
        preferred_times JSONB NOT NULL DEFAULT '[]'::jsonb,
        notes TEXT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """))
    await _execute_schema_statement(session, text('CREATE INDEX IF NOT EXISTS ix_qazo_plans_user_enabled ON qazo_plans (user_id, enabled)'))

    # Self-heal older production DBs. CREATE TABLE IF NOT EXISTS does not add
    # columns to existing tables; missing columns caused HTTP 500 in Qazo.
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_plans ADD COLUMN IF NOT EXISTS user_id BIGINT NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_plans ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT true"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_plans ADD COLUMN IF NOT EXISTS mode VARCHAR(30) NOT NULL DEFAULT 'custom'"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_plans ADD COLUMN IF NOT EXISTS daily_targets JSONB NOT NULL DEFAULT '{\"fajr\":1,\"dhuhr\":1,\"asr\":1,\"maghrib\":1,\"isha\":1,\"witr\":0}'::jsonb"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_plans ADD COLUMN IF NOT EXISTS preferred_times JSONB NOT NULL DEFAULT '[]'::jsonb"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_plans ADD COLUMN IF NOT EXISTS notes TEXT NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_plans ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_plans ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"))

    await _execute_schema_statement(session, text("""
    CREATE TABLE IF NOT EXISTS missed_prayers (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        prayer_name VARCHAR(20) NOT NULL,
        prayer_date DATE NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'active',
        source VARCHAR(30) NOT NULL DEFAULT 'manual',
        daily_prayer_id BIGINT NULL REFERENCES daily_prayers(id) ON DELETE SET NULL,
        qazo_calculation_id BIGINT NULL REFERENCES qazo_calculations(id) ON DELETE SET NULL,
        completed_at TIMESTAMPTZ NULL,
        cancelled_at TIMESTAMPTZ NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS missed_prayers ADD COLUMN IF NOT EXISTS user_id BIGINT NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS missed_prayers ADD COLUMN IF NOT EXISTS prayer_name VARCHAR(20) NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS missed_prayers ADD COLUMN IF NOT EXISTS prayer_date DATE NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS missed_prayers ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'active'"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS missed_prayers ADD COLUMN IF NOT EXISTS source VARCHAR(30) NOT NULL DEFAULT 'manual'"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS missed_prayers ADD COLUMN IF NOT EXISTS daily_prayer_id BIGINT NULL REFERENCES daily_prayers(id) ON DELETE SET NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS missed_prayers ADD COLUMN IF NOT EXISTS qazo_calculation_id BIGINT NULL REFERENCES qazo_calculations(id) ON DELETE SET NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS missed_prayers ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS missed_prayers ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS missed_prayers ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS missed_prayers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"))
    await _execute_schema_statement(session, text('CREATE INDEX IF NOT EXISTS ix_missed_user_status ON missed_prayers (user_id, status)'))
    await _execute_schema_statement(session, text('CREATE INDEX IF NOT EXISTS ix_missed_user_prayer_status ON missed_prayers (user_id, prayer_name, status)'))
    await _execute_schema_statement(session, text('CREATE INDEX IF NOT EXISTS ix_missed_user_source_status ON missed_prayers (user_id, source, status)'))
    await _execute_schema_statement(session, text('CREATE INDEX IF NOT EXISTS ix_missed_qazo_calculation_id ON missed_prayers (qazo_calculation_id)'))

    await _execute_schema_statement(session, text("""
    CREATE TABLE IF NOT EXISTS qazo_completion_actions (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        prayer_name VARCHAR(20) NOT NULL,
        completed_count INTEGER NOT NULL,
        missed_prayer_ids JSONB NOT NULL,
        source_filter JSONB NULL,
        start_date DATE NULL,
        end_date DATE NULL,
        qazo_calculation_id BIGINT NULL REFERENCES qazo_calculations(id) ON DELETE SET NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'completed',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        undone_at TIMESTAMPTZ NULL
    )
    """))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_completion_actions ADD COLUMN IF NOT EXISTS user_id BIGINT NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_completion_actions ADD COLUMN IF NOT EXISTS prayer_name VARCHAR(20) NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_completion_actions ADD COLUMN IF NOT EXISTS completed_count INTEGER NOT NULL DEFAULT 0"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_completion_actions ADD COLUMN IF NOT EXISTS missed_prayer_ids JSONB NOT NULL DEFAULT '[]'::jsonb"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_completion_actions ADD COLUMN IF NOT EXISTS source_filter JSONB NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_completion_actions ADD COLUMN IF NOT EXISTS start_date DATE NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_completion_actions ADD COLUMN IF NOT EXISTS end_date DATE NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_completion_actions ADD COLUMN IF NOT EXISTS qazo_calculation_id BIGINT NULL REFERENCES qazo_calculations(id) ON DELETE SET NULL"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_completion_actions ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'completed'"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_completion_actions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()"))
    await _execute_schema_statement(session, text("ALTER TABLE IF EXISTS qazo_completion_actions ADD COLUMN IF NOT EXISTS undone_at TIMESTAMPTZ NULL"))
    await _execute_schema_statement(session, text('CREATE INDEX IF NOT EXISTS ix_qazo_completion_user_created ON qazo_completion_actions (user_id, created_at DESC)'))
    await _execute_schema_statement(session, text('CREATE INDEX IF NOT EXISTS ix_qazo_completion_user_status ON qazo_completion_actions (user_id, status)'))
    await session.commit()


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


def _miniapp_error_payload(message: str | None = None) -> dict:
    """Safe response used when data loading hits an unexpected backend error.

    Telegram Mini App should not show raw HTTP 500. The UI can render this
    payload and show a friendly retry message while logs still keep details.
    """
    today = tashkent_today()
    now_tz = tashkent_now()
    empty_qazo = {p: 0 for p in QAZO_PRAYER_NAMES}
    return {
        "ok": False,
        "error": "server_error",
        "message": "Ma'lumotlarni yuklashda xato bo'ldi. Iltimos, qayta urinib ko'ring.",
        "debug_message": message if _dev_mode() else None,
        "name": "Foydalanuvchi",
        "city": "Toshkent",
        "lang": "uz",
        "prayers": {},
        "prayer_times": {},
        "prayer_datetimes": {},
        "can_mark": {},
        "minutes_until": {},
        "next_prayer": None,
        "current_time": now_tz.strftime("%H:%M"),
        "current_datetime": now_tz.isoformat(),
        "qazo": empty_qazo,
        "qazo_completed_today": empty_qazo.copy(),
        "qazo_plan": {
            "enabled": True,
            "mode": "balanced",
            "daily_targets": _default_qazo_targets(),
            "tasks": {p: {"target": 0, "done": 0, "left": 0, "active": 0} for p in QAZO_PRAYER_NAMES},
            "today_target": 0,
            "today_done": 0,
            "today_left": 0,
        },
        "qazo_history": [],
        "qazo_details": [],
        "qazo_calculations": [],
        "stats": {"prayed": 0, "missed": 0, "completed": 0, "active": 0},
        "settings": {"prayer_reminders": True, "qazo_reminders": True},
        "today": today.isoformat(),
        "selected_date": today.isoformat(),
        "is_today": True,
        "timezone": TASHKENT_TZ_NAME,
        "cities": list(ISLOMAPI_REGIONS),
    }


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


async def create_missed_prayer_if_absent(
    session,
    *,
    user_id: int,
    prayer_name: str,
    prayer_date: date,
    source: str = "manual",
    daily_prayer_id: int | None = None,
    qazo_calculation_id: int | None = None,
) -> tuple[MissedPrayer, bool]:
    """DB-agnostic active-qazo upsert used by Mini App."""
    existing = await session.scalar(
        select(MissedPrayer).where(
            MissedPrayer.user_id == user_id,
            MissedPrayer.prayer_name == prayer_name,
            MissedPrayer.prayer_date == prayer_date,
            MissedPrayer.status == "active",
        )
    )
    if existing:
        return existing, False
    row = MissedPrayer(
        user_id=user_id,
        prayer_name=prayer_name,
        prayer_date=prayer_date,
        status="active",
        source=source,
        daily_prayer_id=daily_prayer_id,
        qazo_calculation_id=qazo_calculation_id,
    )
    session.add(row)
    await session.flush()
    return row, True


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

    try:
        async with AsyncSessionLocal() as session:
            # Run schema self-heal BEFORE selecting ORM models. Older Railway DBs
            # can miss newly added mapped columns; selecting User first would fail
            # with UndefinedColumn and the Mini App would render an empty fallback.
            await ensure_qazo_schema(session)

            user_data = await _get_user_snapshot(session, int(telegram_id))
            if not user_data or not bool(user_data.get("onboarding_completed")):
                return web.json_response({
                    "error": "registration_required",
                    "message": "Mini Appdan foydalanish uchun avval botda /start bosib, tilni tanlang va rozilik bering.",
                }, status=403)

            # Snapshot primitive values before any rollback. SQLAlchemy expires ORM
            # objects on rollback; keeping primitive values prevents the Mini App
            # from losing the bot user data after a prayer/API/DB fallback.
            user_id = int(user_data["id"])
            user_name = user_data.get("full_name") or user_data.get("username") or "Foydalanuvchi"
            user_lang = user_data.get("language_code") or "uz"
            city = _region_for_islomapi(user_data.get("city") or "Toshkent")
            tz = user_data.get("timezone") or TASHKENT_TZ_NAME

            today = tashkent_today()
            now_tz = tashkent_now()
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
            prayer_error: str | None = None
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
                        user_id=user_id,
                        prayer_name=prayer_name,
                        prayer_date=selected_day,
                        prayer_time=service.combine(selected_day, value, tz),
                    )
                await session.commit()
            except Exception as exc:
                prayer_error = str(exc)
                logger.warning("Could not load exact prayer times for mini app: %s", exc)
                await session.rollback()

            # ── Today's prayer statuses from the same table bot uses ──
            daily_rows = await session.execute(
                select(DailyPrayer.prayer_name, DailyPrayer.status, DailyPrayer.prayer_time)
                .where(DailyPrayer.user_id == user_id, DailyPrayer.prayer_date == selected_day)
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
                .where(MissedPrayer.user_id == user_id, MissedPrayer.status == "active")
                .group_by(MissedPrayer.prayer_name)
            )
            qazo = {p: 0 for p in QAZO_PRAYER_NAMES}
            for prayer_name, count in qazo_rows:
                if prayer_name in qazo:
                    qazo[prayer_name] = int(count)

            total_active = sum(qazo.values())

            # ── Qazo plan and today's qazo completion progress ──
            from zoneinfo import ZoneInfo
            tzinfo = ZoneInfo(tz)
            day_start = datetime.combine(today, time.min, tzinfo=tzinfo).astimezone(timezone.utc)
            day_end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=tzinfo).astimezone(timezone.utc)
            completed_today_rows = await session.execute(
                select(QazoCompletionAction.prayer_name, func.coalesce(func.sum(QazoCompletionAction.completed_count), 0))
                .where(
                    QazoCompletionAction.user_id == user_id,
                    QazoCompletionAction.status == "completed",
                    QazoCompletionAction.created_at >= day_start,
                    QazoCompletionAction.created_at < day_end,
                )
                .group_by(QazoCompletionAction.prayer_name)
            )
            qazo_completed_today = {p: 0 for p in QAZO_PRAYER_NAMES}
            for prayer_name, count in completed_today_rows:
                if prayer_name in qazo_completed_today:
                    qazo_completed_today[prayer_name] = int(count or 0)

            plan = await get_or_create_qazo_plan(session, user_id)
            await session.commit()
            qazo_plan = _qazo_plan_payload(plan, qazo, qazo_completed_today)

            recent_actions = list((await session.scalars(
                select(QazoCompletionAction)
                .where(QazoCompletionAction.user_id == user_id, QazoCompletionAction.status == "completed")
                .order_by(QazoCompletionAction.created_at.desc())
                .limit(30)
            )).all())
            qazo_history = [
                {
                    "id": int(a.id),
                    "prayer": a.prayer_name,
                    "label": PRAYER_LABELS.get(a.prayer_name, a.prayer_name),
                    "count": int(a.completed_count),
                    "created_at": a.created_at.astimezone(tzinfo).isoformat() if a.created_at else None,
                    "date": a.created_at.astimezone(tzinfo).date().isoformat() if a.created_at else None,
                }
                for a in recent_actions
            ]

            detail_rows = (await session.execute(
                select(MissedPrayer.id, MissedPrayer.prayer_name, MissedPrayer.prayer_date, MissedPrayer.source, MissedPrayer.qazo_calculation_id)
                .where(MissedPrayer.user_id == user_id, MissedPrayer.status == "active")
                .order_by(MissedPrayer.prayer_date.asc(), MissedPrayer.created_at.asc())
                .limit(200)
            )).all()
            qazo_details = [
                {"id": int(row_id), "prayer": prayer_name, "label": PRAYER_LABELS.get(prayer_name, prayer_name), "date": prayer_date.isoformat(), "source": source or "manual", "calculation_id": qazo_calculation_id}
                for row_id, prayer_name, prayer_date, source, qazo_calculation_id in detail_rows
            ]

            calc_rows = list((await session.scalars(
                select(QazoCalculation).where(QazoCalculation.user_id == user_id).order_by(QazoCalculation.created_at.desc()).limit(5)
            )).all())
            qazo_calculations = [
                {"id": int(c.id), "start_date": c.start_date.isoformat(), "end_date": c.end_date.isoformat(), "selected_prayers": c.selected_prayers, "days_count": c.days_count, "total_count": c.total_count, "status": c.status, "created_missed_count": c.created_missed_count, "skipped_existing_count": c.skipped_existing_count}
                for c in calc_rows
            ]

            # ── Monthly stats ──
            month_start = date(today.year, today.month, 1)

            prayed_count = int(await session.scalar(
                select(func.count()).select_from(DailyPrayer)
                .where(DailyPrayer.user_id == user_id,
                       DailyPrayer.status == "prayed",
                       DailyPrayer.prayer_date >= month_start)
            ) or 0)

            missed_count = int(await session.scalar(
                select(func.count()).select_from(DailyPrayer)
                .where(DailyPrayer.user_id == user_id,
                       DailyPrayer.status == "missed",
                       DailyPrayer.prayer_date >= month_start)
            ) or 0)

            completed_count = int(await session.scalar(
                select(func.count()).select_from(MissedPrayer)
                .where(MissedPrayer.user_id == user_id,
                       MissedPrayer.status == "completed",
                       MissedPrayer.completed_at >= datetime(today.year, today.month, 1, tzinfo=timezone.utc))
            ) or 0)

            # ── Reminder settings ──
            # If an older DB is still missing this table/columns for any reason,
            # do not fail the whole Mini App data response; use safe defaults.
            reminder: ReminderSetting | None = None
            try:
                reminder = await session.scalar(
                    select(ReminderSetting).where(ReminderSetting.user_id == user_id)
                )
            except Exception as exc:
                logger.warning("Could not load reminder settings for mini app: %s", exc)
                await session.rollback()

            return web.json_response({
                "ok": True,
                "name": user_name,
                "city": city,
                "lang": user_lang,
                "prayers": prayers,
                "prayer_times": prayer_times,   # HH:MM strings in Asia/Tashkent
                "prayer_datetimes": prayer_iso_times,
                "can_mark": can_mark,
                "minutes_until": minutes_until,
                "next_prayer": next_prayer,
                "current_time": now_tz.strftime("%H:%M"),
                "current_datetime": now_tz.isoformat(),
                "qazo": qazo,
                "qazo_completed_today": qazo_completed_today,
                "qazo_plan": qazo_plan,
                "qazo_history": qazo_history,
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
                "cities": list(ISLOMAPI_REGIONS),
                "prayer_error": prayer_error,
            })
    except Exception as exc:
        logger.exception("miniapp_data_failed: %s", exc)
        return web.json_response(_miniapp_error_payload(str(exc)), status=200)


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

    try:
        async with AsyncSessionLocal() as session:
            # Same preflight as /api/data: do not read ORM models before the
            # production database has been self-healed.
            await ensure_qazo_schema(session)

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
                    return web.json_response({"ok": True, "lang": lang})
                return web.json_response({"ok": False, "message": "unknown language"}, status=400)

            # ── SET CITY ──
            elif action == "set_city":
                city = _region_for_islomapi((body.get("city") or "Toshkent").strip()[:100])
                await UsersRepository(session).set_city(user.id, city)
                await session.commit()
                return web.json_response({"ok": True, "city": city})

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
                return web.json_response({"ok": True, "type": setting_type, "value": value})

            # ── SAVE QAZO PLAN ──
            elif action == "save_qazo_plan":
                try:
                    plan = await get_or_create_qazo_plan(session, user.id)
                    targets = _normalize_qazo_targets(body.get("daily_targets") or {})
                    mode = str(body.get("mode") or "custom")[:30]
                    enabled = bool(body.get("enabled", True))
                    plan.mode = mode if mode in ("balanced", "focus", "custom", "flexible") else "custom"
                    plan.enabled = enabled
                    plan.daily_targets = targets
                    await session.commit()
                    return web.json_response({"ok": True, "plan": {"enabled": plan.enabled, "mode": plan.mode, "daily_targets": targets}})
                except Exception as exc:
                    logger.exception("save_qazo_plan failed for user %s: %s", user.id, exc)
                    await session.rollback()
                    return web.json_response({"ok": False, "message": str(exc)}, status=200)

            # ── UNDO QAZO COMPLETION ──
            elif action == "undo_qazo_completion":
                try:
                    action_id = int(body.get("action_id"))
                except Exception:
                    return web.json_response({"ok": False, "message": "Noto‘g‘ri amal"}, status=400)
                restored = await MissedPrayersRepository(session).undo_completion_action(user.id, action_id)
                if not restored:
                    return web.json_response({"ok": False, "message": "Bekor qilib bo‘lmadi"}, status=400)
                await session.commit()
                return web.json_response({"ok": True})

            # ── QAZO CALCULATOR PREVIEW ──
            elif action == "calculate_qazo":
                today = tashkent_today()
                start_date = _parse_date(body.get("start_date"), today)
                end_date = _parse_date(body.get("end_date"), today)
                if end_date > today:
                    end_date = today
                if start_date > end_date:
                    return web.json_response({"ok": False, "message": "Boshlanish sanasi tugash sanasidan katta bo‘lmasin"}, status=400)
                selected = [prayer for prayer in (body.get("prayers") or []) if prayer in QAZO_PRAYER_NAMES]
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
                selected = [prayer for prayer in (body.get("prayers") or []) if prayer in QAZO_PRAYER_NAMES]
                if not selected:
                    return web.json_response({"ok": False, "message": "Kamida bitta namozni tanlang"}, status=400)
                days_count = _date_range_days(start_date, end_date)
                if days_count > 36500:
                    return web.json_response({"ok": False, "message": "Oraliq juda katta"}, status=400)
                breakdown = _calculate_qazo_breakdown(start_date, end_date, selected)
                calc_repo = QazoCalculationsRepository(session)
                calc = await calc_repo.create_calculated(user_id=user.id, start_date=start_date, end_date=end_date, selected_prayers=selected, days_count=days_count, breakdown=breakdown)
                created_breakdown = {prayer: 0 for prayer in selected}
                skipped_breakdown = {prayer: 0 for prayer in selected}
                current_day = start_date
                while current_day <= end_date:
                    for prayer in selected:
                        _, created = await create_missed_prayer_if_absent(session, user_id=user.id, prayer_name=prayer, prayer_date=current_day, source="calculator", qazo_calculation_id=calc.id)
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
                if prayer in QAZO_PRAYER_NAMES:
                    try:
                        prayer_date = date.fromisoformat(raw_date)
                    except ValueError:
                        prayer_date = tashkent_today()
                    if prayer_date > tashkent_today():
                        return web.json_response({"error": "future date"}, status=400)
                    _, created = await create_missed_prayer_if_absent(
                        session,
                        user_id=user.id,
                        prayer_name=prayer,
                        prayer_date=prayer_date,
                        source="manual",
                    )
                    if prayer_date == tashkent_today() and prayer in DAILY_PRAYER_NAMES:
                        daily = await ensure_daily_prayer_row(session, user, prayer, prayer_date)
                        await DailyPrayersRepository(session).set_status(daily.id, "missed")
                    await session.commit()
                    return web.json_response({"ok": True, "created": created})

            # ── COMPLETE QAZO (mark 1 as done) ──
            elif action == "complete_qazo":
                prayer = body.get("prayer", "")
                try:
                    count = max(1, min(int(body.get("count", 1) or 1), 99))
                except Exception:
                    count = 1
                if prayer in QAZO_PRAYER_NAMES:
                    repo = MissedPrayersRepository(session)
                    try:
                        available = await repo.count_by_prayer(user.id, prayer)
                        if available <= 0:
                            return web.json_response({"ok": False, "message": "Ado qilinmagan qazo qolmagan"}, status=400)
                        actual_count = min(count, available)
                        completion_action = await repo.complete_oldest(user_id=user.id, prayer_name=prayer, count=actual_count)
                        remaining = await repo.count_by_prayer(user.id, prayer)
                        await session.commit()
                        return web.json_response({"ok": True, "completed": actual_count, "prayer": prayer, "action_id": int(completion_action.id), "active_remaining": remaining})
                    except ValueError as e:
                        await session.rollback()
                        return web.json_response({"ok": False, "message": str(e)}, status=400)
                    except Exception as exc:
                        logger.exception("complete_qazo failed for user %s prayer %s: %s", user.id, prayer, exc)
                        await session.rollback()
                        return web.json_response({"ok": False, "message": "Qazo ado qilishda xato yuz berdi. Iltimos, qayta urinib ko'ring."}, status=200)

            # ── UPDATE TODAY'S PRAYER STATUS ──
            elif action == "set_prayer_status":
                prayer = body.get("prayer", "")
                status = body.get("status", "")
                if prayer not in DAILY_PRAYER_NAMES or status not in ("prayed", "missed", "pending"):
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
                    await create_missed_prayer_if_absent(
                        session,
                        user_id=user.id,
                        prayer_name=prayer,
                        prayer_date=prayer_date,
                        source="daily_confirmation",
                        daily_prayer_id=daily.id,
                    )
                elif status in ("prayed", "pending"):
                    # If the user changes an earlier "missed" status to "prayed"
                    # or clears it back to pending, remove the qazo row created by
                    # daily confirmation. Manually-added/calculated qazo rows stay.
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

        return web.json_response({"ok": False, "message": "unknown action"}, status=400)
    except Exception as exc:
        logger.exception("miniapp_action_failed action=%s: %s", action, exc)
        return web.json_response({"ok": False, "message": "Amalni bajarishda xato bo'ldi. Iltimos, qayta urinib ko'ring."}, status=200)


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
