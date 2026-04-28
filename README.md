# Namoz va Qazo Telegram Bot

Production-oriented Telegram bot for daily prayer reminders, missed-prayer tracking, qazo calculator, multilingual UX, PostgreSQL persistence, admin panel, scheduler and Railway/Docker deployment.

## Features

- aiogram 3.x Telegram bot
- PostgreSQL as the single source of truth
- Async SQLAlchemy repositories
- Alembic migrations
- User onboarding: language, privacy, city
- Uzbek, Russian and English locale files
- Reply-keyboard main menu
- Daily prayer times cache and fallback-ready provider interface
- Prayer confirmation: prayed, missed, snoozed
- Missed prayer storage with source separation: manual, daily_confirmation, calculator, admin
- Qazo calculator with per-prayer breakdown
- Calculator application into one missed_prayers row per date/prayer
- Duplicate protection through partial unique index
- Count-based qazo completion with undo action
- Settings, privacy and statistics screens
- Telegram admin panel scaffold: dashboard, users, broadcast sections
- DB-first scheduler with PostgreSQL advisory locks
- Docker Compose with persistent PostgreSQL volume
- Railway-compatible config normalization

## Project structure

```text
app/
  bot/
    handlers/       Telegram handlers
    keyboards/      Reply/inline keyboards
    middlewares/    DB/current-user middlewares
  core/             config, constants, logging
  db/               models, session, repositories
  services/         business services and i18n
  scheduler/        APScheduler jobs and advisory locks
  locales/          uz/ru/en translations
migrations/         Alembic migration environment

docs/               deployment, database, privacy, admin, UX notes
tests/              unit tests
```

## Configuration

Copy `.env.example` to `.env` for local development.

```bash
cp .env.example .env
```

Required values:

```env
BOT_TOKEN=PASTE_TELEGRAM_BOT_TOKEN_HERE
ADMIN_TELEGRAM_IDS=123456789,987654321
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/namoz_bot
ALEMBIC_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/namoz_bot
DEFAULT_TIMEZONE=Asia/Tashkent
PRAYER_API_BASE_URL=https://islomapi.uz
```

`app/core/secrets.py` may be created locally from `app/core/secrets.example.py`, but it must never be committed or included in Docker images/zip releases.

Railway may provide `postgresql://...`; the config loader normalizes it to `postgresql+asyncpg://...` for async SQLAlchemy and `postgresql+psycopg://...` for Alembic.

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.main
```

## Docker Compose

```bash
docker compose up --build
```

PostgreSQL data is stored in the named volume `postgres_data`, so container restarts do not delete user data.

## Railway deployment

Recommended MVP setup:

- App service: this repository
- PostgreSQL service: Railway Postgres
- Start command: `python -m app.main`
- Pre-deploy command: `alembic upgrade head`
- Replica count: `1` for MVP

The scheduler also uses PostgreSQL advisory locks so accidental duplicate instances skip locked jobs.

## Database persistence

The bot never stores important user data in long-lived Python dict/list objects. Persistent entities include:

- users, preferences, language, city, timezone
- DB-backed user_states for flows
- daily prayer statuses
- missed/qazo prayers and calculator histories
- qazo completion actions and undo metadata
- reminder settings and reminder logs
- admin actions and broadcast records
- user data delete requests

## Migration strategy

Safe migrations:

- Add a new table
- Add a nullable column
- Add a column with server default
- Add an index concurrently/with care
- Add a constraint after validating existing data

Dangerous migrations:

- Drop table or drop column
- Truncate users or missed_prayers
- Destructive type changes
- Add NOT NULL column without default/backfill
- Rename/remove enum values without compatibility plan
- Dropping production database during deploy

Always run `alembic upgrade head`; never use drop-and-recreate in production.

## Backup strategy

- Use regular `pg_dump` backups for production DB
- Enable/check Railway Postgres backup options
- Take a backup before each risky migration
- Store backups securely
- Test restore periodically
- Define backup retention policy
- Treat backups as sensitive data

## Prayer API integration

`PrayerTimesProvider` is an interface. `ExternalPrayerTimesProvider` fetches from `PRAYER_API_BASE_URL` and `PrayerTimesService` writes cache rows into `prayer_times`. If API fails, cached rows can still be used by extending `get_or_fetch` fallback behavior.

## Qazo calculator

The calculator uses inclusive day count:

```text
days_count = end_date - start_date + 1
prayer_count = days_count per selected prayer
total_count = days_count * selected_prayers_count
```

When applied, every qazo is stored as a separate `missed_prayers` row with `source='calculator'` and `qazo_calculation_id`.

## Privacy

The bot stores only data needed for the product to work. Personal worship details should not be written into logs. Tokens must never be logged.

## Smoke test checklist

User:

1. `/start` creates user
2. Language is saved
3. City is saved
4. Main menu appears
5. Today screen fetches/caches prayer times
6. Prayer status can become prayed
7. Prayer status can become missed
8. Missed row is created
9. Snooze writes `snooze_until`
10. Manual qazo add works
11. Duplicate qazo is skipped
12. Calculator range works
13. Calculator per-prayer breakdown is correct
14. Calculator apply creates rows
15. Calculator duplicates are skipped
16. Calculator qazolar are separated by `source='calculator'`
17. Count-based completion completes oldest rows
18. Undo returns rows to active
19. Stats screen opens
20. Settings screen opens
21. Privacy text opens

Admin:

1. Admin `/admin` opens panel
2. Non-admin cannot open panel
3. Dashboard counts load
4. Users list loads
5. Admin actions are logged

Scheduler/deployment:

1. `alembic upgrade head` creates schema
2. Docker Compose preserves data after restart
3. Token is not logged
4. Advisory lock skips duplicate job execution
5. Reminder idempotency unique key prevents duplicate sends
