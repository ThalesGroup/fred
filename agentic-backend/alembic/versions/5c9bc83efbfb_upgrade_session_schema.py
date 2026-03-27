"""upgrade session schema

Brings the session table up to date with the current ORM:
- add team_id column
- change session_data from json to jsonb (PostgreSQL only)
- set NOT NULL on user_id, session_data, updated_at
- add ix_session_team_id and ix_session_history_timestamp indexes

Revision ID: 5c9bc83efbfb
Revises: bb94940fde0c
Create Date: 2026-03-26 17:42:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5c9bc83efbfb"
down_revision: Union[str, Sequence[str], None] = "bb94940fde0c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # -- session table --

    # Fill NULLs before setting NOT NULL constraints
    op.execute("UPDATE session SET user_id = 'unknown' WHERE user_id IS NULL")
    op.execute("UPDATE session SET session_data = '{}' WHERE session_data IS NULL")
    op.execute(
        "UPDATE session SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL"
    )

    # Use batch_alter_table so that SQLite recreates the table behind the scenes.
    # The with_variant pattern handles json→jsonb on PostgreSQL, stays JSON on SQLite.
    jsonb_type = postgresql.JSONB(astext_type=sa.Text()).with_variant(
        sa.JSON(), "sqlite"
    )
    with op.batch_alter_table("session", schema=None) as batch_op:
        batch_op.add_column(sa.Column("team_id", sa.String(), nullable=True))
        batch_op.alter_column("user_id", existing_type=sa.String(), nullable=False)
        batch_op.alter_column(
            "session_data", existing_type=sa.JSON(), type_=jsonb_type, nullable=False
        )
        batch_op.alter_column(
            "updated_at", existing_type=sa.DateTime(timezone=True), nullable=False
        )
        batch_op.create_index(op.f("ix_session_team_id"), ["team_id"], unique=False)

    # -- session_history table --
    op.create_index(
        "ix_session_history_timestamp", "session_history", ["timestamp"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    # -- session_history table --
    op.drop_index("ix_session_history_timestamp", table_name="session_history")

    # -- session table --
    jsonb_type = postgresql.JSONB(astext_type=sa.Text()).with_variant(
        sa.JSON(), "sqlite"
    )
    with op.batch_alter_table("session", schema=None) as batch_op:
        batch_op.drop_index(op.f("ix_session_team_id"))
        batch_op.alter_column(
            "updated_at", existing_type=sa.DateTime(timezone=True), nullable=True
        )
        batch_op.alter_column(
            "session_data",
            existing_type=jsonb_type,
            type_=sa.JSON().with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        )
        batch_op.alter_column("user_id", existing_type=sa.String(), nullable=True)
        batch_op.drop_column("team_id")
