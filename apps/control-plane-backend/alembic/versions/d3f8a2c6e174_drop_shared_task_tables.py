"""drop the shared task_run/task_event_log orphaned by the per-backend split

Revision ID: d3f8a2c6e174
Revises: b7d4c1a9e802
Create Date: 2026-09-14 00:00:00.000000

`b7e1c4a09d52` moved each backend onto its own prefixed pair and left the shared
pair in place for one release, because the Temporal workers get no scale-down
hook and still ran code writing `task_run` during that rollout. Every deployment
now runs a release containing the split, so nothing writes these tables.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d3f8a2c6e174"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "b7d4c1a9e802"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSONB = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")
_BIGINT_PK = sa.BigInteger().with_variant(sa.INTEGER(), "sqlite")

_NON_TERMINAL_MIGRATION = (
    "kind = 'migration' AND state NOT IN ('succeeded', 'failed', 'cancelled')"
)


def upgrade() -> None:
    """Upgrade schema. Indexes are dropped with their table."""
    op.drop_table("task_event_log")
    op.drop_table("task_run")


def downgrade() -> None:
    """Downgrade schema: recreate the pair at its pre-split shape, empty.

    Index names must match what the older downgrades (`a3b4c5d6e7f8`,
    `c1d2e3f4a5b6`, `f4a5b6c7d8e9`) drop by name.
    """
    op.create_table(
        "task_run",
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("progress", sa.Float(), nullable=True),
        sa.Column("step", sa.Text(), nullable=True),
        sa.Column("detail", _JSONB, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("target", _JSONB, nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("team_id", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(length=36), nullable=True),
        sa.Column("execution_id", sa.String(length=255), nullable=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("task_id"),
    )
    op.create_index(op.f("ix_task_run_kind"), "task_run", ["kind"], unique=False)
    op.create_index(op.f("ix_task_run_state"), "task_run", ["state"], unique=False)
    op.create_index(
        op.f("ix_task_run_created_by"), "task_run", ["created_by"], unique=False
    )
    op.create_index(op.f("ix_task_run_team_id"), "task_run", ["team_id"], unique=False)
    op.create_index(
        "ix_task_run_state_updated", "task_run", ["state", "updated_at"], unique=False
    )
    op.create_index(
        op.f("ix_task_run_scheduled_for"), "task_run", ["scheduled_for"], unique=False
    )
    op.create_index(
        "uq_task_run_single_active_migration",
        "task_run",
        ["kind"],
        unique=True,
        sqlite_where=sa.text(_NON_TERMINAL_MIGRATION),
        postgresql_where=sa.text(_NON_TERMINAL_MIGRATION),
    )

    op.create_table(
        "task_event_log",
        sa.Column("id", _BIGINT_PK, nullable=False, autoincrement=True),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Float(), nullable=True),
        sa.Column("step", sa.Text(), nullable=True),
        sa.Column("detail", _JSONB, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("target", _JSONB, nullable=True),
        sa.Column("owner", sa.String(length=255), nullable=True),
        sa.Column(
            "emitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "seq", name="uq_task_event_log_task_seq"),
    )
    op.create_index(
        op.f("ix_task_event_log_task_id"), "task_event_log", ["task_id"], unique=False
    )
