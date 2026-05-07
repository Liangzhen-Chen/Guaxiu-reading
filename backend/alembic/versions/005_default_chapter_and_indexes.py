"""P5-7: current_chapter default 0 -> 1
P5-9: composite index on conversations (book_id, chapter_index, round_index)
P5-10: pg_trgm index on wiki_entries.concept_name

Revision ID: 005
Revises: 004
Create Date: 2026-05-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # P5-7: Update existing rows where current_chapter = 0 -> 1
    op.execute("UPDATE reading_progress SET current_chapter = 1 WHERE current_chapter = 0")

    # P5-9: Composite index on conversations for efficient book+chapter+round queries
    op.create_index(
        "ix_conv_book_chapter_round",
        "conversations",
        ["book_id", "chapter_index", "round_index"],
        postgresql_using="btree",
    )

    # P5-10: pg_trgm index on wiki_entries.concept_name for fuzzy search
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wiki_concept_name_trgm "
        "ON wiki_entries USING gin (concept_name gin_trgm_ops)"
    )


def downgrade() -> None:
    # P5-7: Revert rows back (no-op for data safety, only revert default)
    # We don't revert data back to 0 since that would break existing reading state

    # P5-9: Drop composite index
    op.drop_index("ix_conv_book_chapter_round", table_name="conversations")

    # P5-10: Drop pg_trgm index
    op.execute("DROP INDEX IF EXISTS ix_wiki_concept_name_trgm")
