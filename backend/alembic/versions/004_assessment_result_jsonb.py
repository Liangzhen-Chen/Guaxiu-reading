"""P5-4: assessment_result String(2000) -> JSONB

Previous format: JSON string stored in String(2000)
New format: Native JSONB column

Revision ID: 004
Revises: 003
Create Date: 2026-05-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Convert String(2000) to JSONB with automatic string->json cast
    op.execute("""
        ALTER TABLE reading_progress
        ALTER COLUMN assessment_result TYPE JSONB
        USING CASE
            WHEN assessment_result IS NULL THEN NULL
            WHEN assessment_result = '' THEN '{}'::jsonb
            ELSE assessment_result::jsonb
        END
    """)


def downgrade() -> None:
    # Convert JSONB back to String(2000) - cast jsonb to text
    op.execute("""
        ALTER TABLE reading_progress
        ALTER COLUMN assessment_result TYPE VARCHAR(2000)
        USING CASE
            WHEN assessment_result IS NULL THEN NULL
            ELSE assessment_result::text
        END
    """)
