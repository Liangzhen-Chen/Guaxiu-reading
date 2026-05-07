"""add updated_at column to reading_progress for streak computation

Revision ID: 003
Revises: 002
Create Date: 2026-05-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "reading_progress",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill existing rows with started_at or current timestamp
    op.execute(
        "UPDATE reading_progress SET updated_at = COALESCE(started_at, NOW()) WHERE updated_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("reading_progress", "updated_at")
