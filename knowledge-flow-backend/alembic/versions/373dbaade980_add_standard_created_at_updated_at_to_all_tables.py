"""add standard created_at updated_at to all tables

Adds TimestampMixin columns (created_at, updated_at) to all tables that were
missing them, normalises existing timestamp columns, and back-fills existing
rows using the best available timestamp source or the prod opening sentinel
(2026-05-04 15:30 UTC).

Revision ID: 373dbaade980
Revises: 0b9a54674eba
Create Date: 2026-05-07 18:08:54.868726

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "373dbaade980"
down_revision: Union[str, Sequence[str], None] = "0b9a54674eba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SENTINEL = "2026-05-04 15:30:00+00"

ts_type = postgresql.TIMESTAMP(timezone=True).with_variant(sa.DateTime(timezone=True), "sqlite")


def upgrade() -> None:
    """Upgrade schema."""
    # -- metadata: no prior standard timestamps; has date_added_to_kb --
    # Back-fill from date_added_to_kb.
    with op.batch_alter_table("metadata", schema=None) as batch_op:
        batch_op.add_column(sa.Column("created_at", ts_type, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
        batch_op.add_column(sa.Column("updated_at", ts_type, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
    op.execute(
        f"""
        UPDATE metadata
        SET
            created_at = COALESCE(date_added_to_kb, '{SENTINEL}'),
            updated_at = COALESCE(date_added_to_kb, '{SENTINEL}')
        """
    )

    # -- resource: no prior timestamps; timestamps live in doc JSONB --
    # Back-fill from doc->>'created_at' / doc->>'updated_at' on PostgreSQL.
    # On SQLite, COALESCE falls back to the sentinel server_default.
    with op.batch_alter_table("resource", schema=None) as batch_op:
        batch_op.add_column(sa.Column("created_at", ts_type, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
        batch_op.add_column(sa.Column("updated_at", ts_type, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
    # ::timestamptz cast is PostgreSQL-only; SQLite gets the sentinel instead.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                f"""
                UPDATE resource
                SET
                    created_at = COALESCE((doc->>'created_at')::timestamptz, '{SENTINEL}'),
                    updated_at = COALESCE((doc->>'updated_at')::timestamptz, '{SENTINEL}')
                WHERE doc IS NOT NULL
                """
            )
        )
    else:
        op.execute(f"UPDATE resource SET created_at = '{SENTINEL}', updated_at = '{SENTINEL}'")

    # -- tag: had nullable created_at/updated_at (no server_default) --
    # Backfill NULLs with sentinel, then make NOT NULL and add server_default.
    op.execute(f"UPDATE tag SET created_at = '{SENTINEL}' WHERE created_at IS NULL")
    op.execute(f"UPDATE tag SET updated_at = '{SENTINEL}' WHERE updated_at IS NULL")
    with op.batch_alter_table("tag", schema=None) as batch_op:
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
    # -- sched_workflow_tasks: had created_at/updated_at (TimestampColumn, no server_default) --
    # Normalise server_defaults only.
    with op.batch_alter_table("sched_workflow_tasks", schema=None) as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=ts_type,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=ts_type,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("sched_workflow_tasks", schema=None) as batch_op:
        batch_op.alter_column(
            "updated_at",
            existing_type=ts_type,
            nullable=False,
            server_default=None,
        )
        batch_op.alter_column(
            "created_at",
            existing_type=ts_type,
            nullable=False,
            server_default=None,
        )

    with op.batch_alter_table("tag", schema=None) as batch_op:
        batch_op.alter_column(
            "updated_at",
            existing_type=ts_type,
            type_=sa.DateTime(timezone=True),
            nullable=True,
            server_default=None,
        )
        batch_op.alter_column(
            "created_at",
            existing_type=ts_type,
            type_=sa.DateTime(timezone=True),
            nullable=True,
            server_default=None,
        )

    with op.batch_alter_table("resource", schema=None) as batch_op:
        batch_op.drop_column("updated_at")
        batch_op.drop_column("created_at")

    with op.batch_alter_table("metadata", schema=None) as batch_op:
        batch_op.drop_column("updated_at")
        batch_op.drop_column("created_at")
