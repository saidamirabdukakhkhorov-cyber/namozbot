from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional in minimal tooling
    def load_dotenv() -> None:
        return None

load_dotenv()

PRODUCTION_ENV_NAMES = {"prod", "production", "railway"}
PLACEHOLDER_MARKERS = (
    "${{",
    "PASTE_",
    "YOUR_",
    "REAL_PASSWORD",
    "<password>",
    "...",
)


def _clean(value: Any) -> str:
    """Normalize a config value copied from UI fields.

    Railway and local .env values should be single-line values without quotes.
    This helper strips accidental whitespace/quotes and joins copied line breaks.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1].strip()
    return "".join(text.split())


def _environment() -> str:
    return _clean(os.getenv("ENVIRONMENT") or "local").lower()


def _read_secret(name: str, default: Any = None) -> Any:
    """Read app/core/secrets.py only for local development.

    In Railway/production we intentionally do not fall back to secrets.py because
    placeholder localhost values can break deployment and hide missing variables.
    """
    if _environment() in PRODUCTION_ENV_NAMES:
        return default
    try:
        from app.core import secrets  # type: ignore
    except Exception:
        return default
    return getattr(secrets, name, default)


def _get(name: str, default: Any = "") -> str:
    value = os.getenv(name)
    if value is None or _clean(value) == "":
        value = _read_secret(name, default)
    return _clean(value)


def _looks_like_placeholder(url: str) -> bool:
    return any(marker in url for marker in PLACEHOLDER_MARKERS)


def _ensure_db_url(url: str, *, variable_name: str) -> str:
    url = _clean(url)
    if not url:
        raise RuntimeError(f"{variable_name} is not configured")
    if _looks_like_placeholder(url):
        raise RuntimeError(
            f"{variable_name} contains a placeholder/reference instead of a real PostgreSQL URL. "
            "Paste Railway Postgres DATABASE_PUBLIC_URL or configure a resolved Railway reference."
        )
    valid_prefixes = (
        "postgres://",
        "postgresql://",
        "postgresql+asyncpg://",
        "postgresql+psycopg://",
    )
    if not url.startswith(valid_prefixes):
        raise RuntimeError(f"{variable_name} must start with postgresql:// or postgres://")
    if ":PORT/" in url or url.endswith(":PORT"):
        raise RuntimeError(f"{variable_name} still contains PORT placeholder")
    return url


def normalize_async_db_url(url: str) -> str:
    url = _ensure_db_url(url, variable_name="DATABASE_URL")
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql+psycopg://"):
        return "postgresql+asyncpg://" + url[len("postgresql+psycopg://") :]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    return url


def normalize_alembic_db_url(url: str, *, source_name: str = "ALEMBIC_DATABASE_URL") -> str:
    url = _ensure_db_url(url, variable_name=source_name)
    if url.startswith("postgresql+psycopg://"):
        return url
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg://" + url[len("postgresql+asyncpg://") :]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


@dataclass(slots=True)
class Settings:
    bot_token: str
    admin_telegram_ids: str
    database_url: str
    alembic_database_url: str
    default_timezone: str
    prayer_api_base_url: str
    log_level: str
    environment: str

    @property
    def async_database_url(self) -> str:
        return normalize_async_db_url(self.database_url)

    @property
    def sync_database_url(self) -> str:
        raw = self.alembic_database_url or self.database_url
        source_name = "ALEMBIC_DATABASE_URL" if self.alembic_database_url else "DATABASE_URL"
        return normalize_alembic_db_url(raw, source_name=source_name)

    @property
    def admin_ids(self) -> set[int]:
        return {
            int(part.strip())
            for part in (self.admin_telegram_ids or "").split(",")
            if part.strip().isdigit()
        }

    def validate_required(self) -> None:
        if not self.bot_token or self.bot_token == "PASTE_TELEGRAM_BOT_TOKEN_HERE":
            raise RuntimeError("BOT_TOKEN is not configured")
        _ = self.async_database_url
        if not self.admin_ids:
            # Not fatal for local development, but useful for Railway logs.
            pass


@lru_cache
def get_settings() -> Settings:
    env = _environment()
    database_url = _get("DATABASE_URL")
    alembic_database_url = _get("ALEMBIC_DATABASE_URL")
    return Settings(
        bot_token=_get("BOT_TOKEN"),
        admin_telegram_ids=_get("ADMIN_TELEGRAM_IDS"),
        database_url=database_url,
        alembic_database_url=alembic_database_url,
        default_timezone=_get("DEFAULT_TIMEZONE", "Asia/Tashkent") or "Asia/Tashkent",
        prayer_api_base_url=_get("PRAYER_API_BASE_URL"),
        log_level=_get("LOG_LEVEL", "INFO") or "INFO",
        environment=env,
    )


settings = get_settings()
