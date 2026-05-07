"""add language column to books table

Revision ID: 002
Revises: 001
Create Date: 2026-05-07
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "books",
        sa.Column("language", sa.String(10), nullable=False, server_default="zh"),
    )


def downgrade() -> None:
    op.drop_column("books", "language")
