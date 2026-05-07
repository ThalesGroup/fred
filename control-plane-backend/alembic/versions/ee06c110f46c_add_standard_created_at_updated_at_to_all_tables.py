"""add standard created_at updated_at to all tables

Normalises timestamp columns for control-plane tables.

- teammetadata: normalises created_at/updated_at type from DateTime to TimestampColumn
  (no-op in PostgreSQL, both map to TIMESTAMP WITH TIME ZONE).
- session_purge_queue: same type normalisation; indexes kept as-is.
- users: adds created_at/updated_at back-filled from gcuAcceptedAt.

Revision ID: ee06c110f46c
Revises: c789f5ab40fe
Create Date: 2026-05-07 18:08:41.631834

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "ee06c110f46c"
down_revision: Union[str, Sequence[str], None] = "c789f5ab40fe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SENTINEL = "2026-05-04 15:30:00+00"

ts_type = postgresql.TIMESTAMP(timezone=True).with_variant(
    sa.DateTime(timezone=True), "sqlite"
)


def upgrade() -> None:
    """Upgrade schema."""
    # -- teammetadata: normalise type from DateTime to TimestampColumn (no-op in PG) --
    with op.batch_alter_table("teammetadata", schema=None) as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            type_=ts_type,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            type_=ts_type,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )

    # -- session_purge_queue: same type normalisation; indexes kept as-is --
    with op.batch_alter_table("session_purge_queue", schema=None) as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            type_=ts_type,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            type_=ts_type,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )

    # -- users: add created_at/updated_at back-filled from gcuAcceptedAt --
    # server_default=CURRENT_TIMESTAMP ensures future inserts get the real time.
    # The UPDATE immediately overwrites existing rows with their actual gcuAcceptedAt.
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("created_at", ts_type, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"))
        )
        batch_op.add_column(
            sa.Column("updated_at", ts_type, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"))
        )
    op.execute('UPDATE users SET created_at = "gcuAcceptedAt", updated_at = "gcuAcceptedAt"')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("updated_at")
        batch_op.drop_column("created_at")

    with op.batch_alter_table("session_purge_queue", schema=None) as batch_op:
        batch_op.alter_column(
            "updated_at",
            existing_type=ts_type,
            type_=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        )
        batch_op.alter_column(
            "created_at",
            existing_type=ts_type,
            type_=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        )

    with op.batch_alter_table("teammetadata", schema=None) as batch_op:
        batch_op.alter_column(
            "updated_at",
            existing_type=ts_type,
            type_=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        )
        batch_op.alter_column(
            "created_at",
            existing_type=ts_type,
            type_=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        )
