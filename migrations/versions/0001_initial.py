"""initial safe schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-28
"""
from alembic import op
from app.db.models import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)

def downgrade() -> None:
    # Production safety: destructive downgrade intentionally disabled.
    # Create a new forward migration for schema changes instead of dropping data.
    pass
