"""Initial schema: create all 7 Xiugua model tables.

Revision ID: 001
Revises: None
Create Date: 2026-05-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all 7 tables in dependency order."""

    # ── 1. users ──
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), unique=True, nullable=True, index=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("wechat_openid", sa.String(128), unique=True, nullable=True, index=True),
        sa.Column("wechat_unionid", sa.String(128), nullable=True),
        sa.Column("display_name", sa.String(100), nullable=True),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── 2. books ──
    op.create_table(
        "books",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("author", sa.String(300), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("cover_url", sa.String(1000), nullable=True),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("file_format", sa.String(10), nullable=False),
        sa.Column("file_path", sa.String(1000), nullable=False),
        sa.Column("text_path", sa.String(1000), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("metadata_source", sa.String(50), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("chapter_count", sa.Integer(), nullable=True),
        sa.Column("parse_status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column("preprocess_status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("preprocess_progress", postgresql.JSONB(), nullable=True),
        sa.Column("one_liner", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── 3. conversations ──
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("book_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("chapter_index", sa.Integer(), nullable=False, index=True),
        sa.Column("round_index", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_jsonb", postgresql.JSONB(), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("compressed_from", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── 4. reading_progress ──
    op.create_table(
        "reading_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("book_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("books.id", ondelete="CASCADE"), nullable=False, unique=True, index=True),
        sa.Column("mode", sa.String(20), nullable=False, server_default=sa.text("'quick'")),
        sa.Column("language", sa.String(10), nullable=False, server_default=sa.text("'zh'")),
        sa.Column("current_chapter", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_rounds", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'not_started'")),
        sa.Column("assessment_result", sa.String(2000), nullable=True),
        sa.Column("current_wiki_id", sa.String(50), nullable=True),
        sa.Column("completed_wikis", postgresql.JSONB(), nullable=True, server_default=sa.text("'[]'::jsonb")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── 5. wiki_entries ──
    op.create_table(
        "wiki_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("book_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("books.id", ondelete="SET NULL"), nullable=True),
        sa.Column("concept_name", sa.String(300), nullable=False),
        sa.Column("chapter_index", sa.Integer(), nullable=True),
        sa.Column("entry_type", sa.String(20), nullable=False, server_default=sa.text("'concept'")),
        sa.Column("entry_subtype", sa.String(20), nullable=False, server_default=sa.text("'concept'")),
        sa.Column("ai_definition", sa.Text(), nullable=True),
        sa.Column("user_understanding", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(), nullable=True),
        sa.Column("tags", postgresql.JSONB(), nullable=True),
        sa.Column("source_quote", sa.Text(), nullable=True),
        sa.Column("source_quotes", postgresql.JSONB(), nullable=True),
        sa.Column("parent_concept_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wiki_entries.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── 6. feedback ──
    op.create_table(
        "feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("contact", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── 7. analytics_events ──
    op.create_table(
        "analytics_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.String(64), nullable=True, index=True),
        sa.Column("event", sa.String(100), nullable=False, index=True),
        sa.Column("page", sa.String(100), nullable=True),
        sa.Column("props", postgresql.JSONB(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop all 7 tables in reverse dependency order."""
    op.drop_table("analytics_events")
    op.drop_table("feedback")
    op.drop_table("wiki_entries")
    op.drop_table("reading_progress")
    op.drop_table("conversations")
    op.drop_table("books")
    op.drop_table("users")
