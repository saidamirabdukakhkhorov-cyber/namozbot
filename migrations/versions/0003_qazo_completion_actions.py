"""add qazo completion actions

Revision ID: 0003_qazo_completion_actions
Revises: 0002_qazo_plans
Create Date: 2026-04-29
"""
from alembic import op

revision = "0003_qazo_completion_actions"
down_revision = "0002_qazo_plans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('''
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
    ''')
    op.execute('CREATE INDEX IF NOT EXISTS ix_qazo_completion_user_created ON qazo_completion_actions (user_id, created_at DESC)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_qazo_completion_user_status ON qazo_completion_actions (user_id, status)')


def downgrade() -> None:
    pass
