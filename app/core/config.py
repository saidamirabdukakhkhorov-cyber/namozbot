from __future__ import annotations
import os
from functools import lru_cache
from typing import Any
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
load_dotenv()

def _read_secret(name: str, default: Any = None) -> Any:
    try:
        from app.core import secrets  # type: ignore
    except Exception:
        return default
    return getattr(secrets, name, default)

def normalize_async_db_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"): return url
    if url.startswith("postgres://"): return "postgresql+asyncpg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"): return "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url

def normalize_alembic_db_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"): return url
    if url.startswith("postgresql+asyncpg://"): return "postgresql+psycopg://" + url[len("postgresql+asyncpg://"):]
    if url.startswith("postgres://"): return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"): return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    bot_token: str = Field(default_factory=lambda: os.getenv("BOT_TOKEN") or _read_secret("BOT_TOKEN", ""))
    admin_telegram_ids: str = Field(default_factory=lambda: os.getenv("ADMIN_TELEGRAM_IDS") or _read_secret("ADMIN_TELEGRAM_IDS", ""))
    database_url: str = Field(default_factory=lambda: os.getenv("DATABASE_URL") or _read_secret("DATABASE_URL", ""))
    alembic_database_url: str = Field(default_factory=lambda: os.getenv("ALEMBIC_DATABASE_URL") or _read_secret("ALEMBIC_DATABASE_URL", ""))
    default_timezone: str = Field(default_factory=lambda: os.getenv("DEFAULT_TIMEZONE") or _read_secret("DEFAULT_TIMEZONE", "Asia/Tashkent"))
    prayer_api_base_url: str = Field(default_factory=lambda: os.getenv("PRAYER_API_BASE_URL") or _read_secret("PRAYER_API_BASE_URL", ""))
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    environment: str = Field(default_factory=lambda: os.getenv("ENVIRONMENT", "local"))
    @property
    def async_database_url(self) -> str: return normalize_async_db_url(self.database_url)
    @property
    def sync_database_url(self) -> str: return normalize_alembic_db_url(self.alembic_database_url or self.database_url)
    @property
    def admin_ids(self) -> set[int]:
        return {int(x.strip()) for x in (self.admin_telegram_ids or "").split(",") if x.strip().isdigit()}
    def validate_required(self) -> None:
        if not self.bot_token or self.bot_token == "PASTE_TELEGRAM_BOT_TOKEN_HERE": raise RuntimeError("BOT_TOKEN is not configured")
        if not self.database_url: raise RuntimeError("DATABASE_URL is not configured")
@lru_cache
def get_settings() -> Settings:
    s = Settings(); s.database_url = normalize_async_db_url(s.database_url); s.alembic_database_url = normalize_alembic_db_url(s.alembic_database_url or s.database_url); return s
settings = get_settings()
