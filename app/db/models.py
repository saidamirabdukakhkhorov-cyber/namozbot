from __future__ import annotations
from datetime import date, datetime, time
from typing import Any
from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, Time, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
class Base(DeclarativeBase): pass
class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language_code: Mapped[str] = mapped_column(String(5), server_default="uz", nullable=False)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    timezone: Mapped[str] = mapped_column(String(64), server_default="Asia/Tashkent", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), nullable=False)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    preferences: Mapped["UserPreference"] = relationship(back_populates="user", cascade="all, delete-orphan")
    reminder_settings: Mapped["ReminderSetting"] = relationship(back_populates="user", cascade="all, delete-orphan")
class UserPreference(Base, TimestampMixin):
    __tablename__ = "user_preferences"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    language: Mapped[str] = mapped_column(String(5), server_default="uz", nullable=False)
    date_format: Mapped[str] = mapped_column(String(20), server_default="YYYY-MM-DD", nullable=False)
    main_menu_style: Mapped[str] = mapped_column(String(30), server_default="reply_keyboard", nullable=False)
    show_daily_summary: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)
    show_weekly_summary: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)
    quiet_hours_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)
    quiet_hours_start: Mapped[time] = mapped_column(Time, server_default="23:00", nullable=False)
    quiet_hours_end: Mapped[time] = mapped_column(Time, server_default="06:00", nullable=False)
    user: Mapped[User] = relationship(back_populates="preferences")
class UserState(Base, TimestampMixin):
    __tablename__ = "user_states"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
class PrayerTime(Base, TimestampMixin):
    __tablename__ = "prayer_times"
    __table_args__ = (UniqueConstraint("city", "prayer_date", name="uq_prayer_times_city_date"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    prayer_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    timezone: Mapped[str] = mapped_column(String(64), server_default="Asia/Tashkent", nullable=False)
    fajr_time: Mapped[time] = mapped_column(Time, nullable=False)
    dhuhr_time: Mapped[time] = mapped_column(Time, nullable=False)
    asr_time: Mapped[time] = mapped_column(Time, nullable=False)
    maghrib_time: Mapped[time] = mapped_column(Time, nullable=False)
    isha_time: Mapped[time] = mapped_column(Time, nullable=False)
    source: Mapped[str] = mapped_column(String(40), server_default="external", nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)
class DailyPrayer(Base, TimestampMixin):
    __tablename__ = "daily_prayers"
    __table_args__ = (UniqueConstraint("user_id", "prayer_name", "prayer_date", name="uq_daily_prayer_user_name_date"), Index("ix_daily_prayers_user_date", "user_id", "prayer_date"), Index("ix_daily_prayers_user_status", "user_id", "status"))
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    prayer_name: Mapped[str] = mapped_column(String(20), nullable=False)
    prayer_date: Mapped[date] = mapped_column(Date, nullable=False)
    prayer_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default="pending", nullable=False)
    snooze_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
class QazoCalculation(Base):
    __tablename__ = "qazo_calculations"
    __table_args__ = (Index("ix_qazo_calc_user_created", "user_id", "created_at"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    selected_prayers: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    days_count: Mapped[int] = mapped_column(Integer, nullable=False)
    prayers_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False)
    breakdown: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    created_breakdown: Mapped[dict[str, int]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)
    skipped_breakdown: Mapped[dict[str, int]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default="calculated", nullable=False)
    created_missed_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    skipped_existing_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
class MissedPrayer(Base, TimestampMixin):
    __tablename__ = "missed_prayers"
    __table_args__ = (Index("ix_missed_user_status", "user_id", "status"), Index("ix_missed_user_prayer_status", "user_id", "prayer_name", "status"), Index("ix_missed_user_source_status", "user_id", "source", "status"), Index("ix_missed_qazo_calculation_id", "qazo_calculation_id"), Index("uq_missed_active_user_prayer_date", "user_id", "prayer_name", "prayer_date", unique=True, postgresql_where=text("status = 'active'")))
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    prayer_name: Mapped[str] = mapped_column(String(20), nullable=False)
    prayer_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default="active", nullable=False)
    source: Mapped[str] = mapped_column(String(30), server_default="manual", nullable=False)
    daily_prayer_id: Mapped[int | None] = mapped_column(ForeignKey("daily_prayers.id", ondelete="SET NULL"), nullable=True)
    qazo_calculation_id: Mapped[int | None] = mapped_column(ForeignKey("qazo_calculations.id", ondelete="SET NULL"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
class QazoPlan(Base, TimestampMixin):
    __tablename__ = "qazo_plans"
    __table_args__ = (Index("ix_qazo_plans_user_enabled", "user_id", "enabled"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)
    mode: Mapped[str] = mapped_column(String(30), server_default="custom", nullable=False)
    daily_targets: Mapped[dict[str, int]] = mapped_column(JSONB, server_default=text("""'{"fajr":1,"dhuhr":1,"asr":1,"maghrib":1,"isha":1,"witr":0}'::jsonb"""), nullable=False)
    preferred_times: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

class QazoCompletionAction(Base):
    __tablename__ = "qazo_completion_actions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    prayer_name: Mapped[str] = mapped_column(String(20), nullable=False)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    missed_prayer_ids: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    source_filter: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    qazo_calculation_id: Mapped[int | None] = mapped_column(ForeignKey("qazo_calculations.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), server_default="completed", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
class ReminderSetting(Base, TimestampMixin):
    __tablename__ = "reminder_settings"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    prayer_reminders_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)
    qazo_reminders_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)
    qazo_reminder_times: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[\"08:00\", \"21:00\"]'::jsonb"), nullable=False)
    daily_qazo_limit: Mapped[int] = mapped_column(Integer, server_default="1", nullable=False)
    quiet_hours_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)
    quiet_hours_start: Mapped[time] = mapped_column(Time, server_default="23:00", nullable=False)
    quiet_hours_end: Mapped[time] = mapped_column(Time, server_default="06:00", nullable=False)
    user: Mapped[User] = relationship(back_populates="reminder_settings")
class ReminderLog(Base):
    __tablename__ = "reminders_log"
    __table_args__ = (UniqueConstraint("user_id", "reminder_type", "related_entity_type", "related_entity_id", "scheduled_for", name="uq_reminders_idempotency"), Index("ix_reminders_status_scheduled", "status", "scheduled_for"))
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reminder_type: Mapped[str] = mapped_column(String(40), nullable=False)
    related_entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    related_entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), server_default="pending", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
class AdminAction(Base):
    __tablename__ = "admin_actions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    admin_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    target_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
class AdminBroadcast(Base):
    __tablename__ = "admin_broadcasts"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    admin_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(String(40), server_default="active_users", nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default="draft", nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    sent_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
class BroadcastRecipient(Base, TimestampMixin):
    __tablename__ = "broadcast_recipients"
    __table_args__ = (UniqueConstraint("broadcast_id", "user_id", name="uq_broadcast_recipient"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    broadcast_id: Mapped[int] = mapped_column(ForeignKey("admin_broadcasts.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default="pending", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
class UserDataDeleteRequest(Base):
    __tablename__ = "user_data_delete_requests"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), server_default="requested", nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class PrayerTimeOverride(Base, TimestampMixin):
    __tablename__ = "prayer_time_overrides"
    __table_args__ = (UniqueConstraint("city", "prayer_date", name="uq_prayer_time_overrides_city_date"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    prayer_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), server_default="Asia/Tashkent", nullable=False)
    fajr_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    dhuhr_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    asr_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    maghrib_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    isha_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
