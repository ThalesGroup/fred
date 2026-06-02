"""create session_history table

Initial schema for the session_history table as originally deployed via
PostgresHistoryStore._ensure_tables (CREATE TABLE IF NOT EXISTS).

Stamp an existing production database that already has this table with:
    alembic stamp a1e2f3c4d5b6

Revision ID: a1e2f3c4d5b6
Revises:
Create Date: 2026-06-02 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1e2f3c4d5b6"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "session_history",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column(
            "parts_json",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("session_id", "user_id", "rank"),
    )
    op.create_index(
        "ix_session_history_timestamp",
        "session_history",
        ["timestamp"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_session_history_timestamp", table_name="session_history")
    op.drop_table("session_history")
