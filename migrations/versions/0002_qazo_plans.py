"""add qazo plans

Revision ID: 0002_qazo_plans
Revises: 0001_initial
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_qazo_plans"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('''
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
    ''')
    op.execute('CREATE INDEX IF NOT EXISTS ix_qazo_plans_user_enabled ON qazo_plans (user_id, enabled)')


def downgrade() -> None:
    # Production safety: keep data by default. Use a forward migration for changes.
    pass
