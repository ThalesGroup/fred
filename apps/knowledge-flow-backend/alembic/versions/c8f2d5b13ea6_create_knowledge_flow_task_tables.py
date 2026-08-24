"""create knowledge-flow's own task tables (kf_task_run / kf_task_event_log)

Revision ID: c8f2d5b13ea6
Revises: bcd7cbdbedca
Create Date: 2026-08-14 00:00:00.000000

Knowledge-flow's first real `CREATE TABLE` for its task pair (#2170). Until now
this tree only carried defensive `ALTER`s (`1c9a54674ebf`, `d96d9ae21375`,
`e2f3a4b5c6d7`) against a `task_run` it never created: the table came either
from control-plane's `a3b4c5d6e7f8` — both backends migrate the same `fred`
database — or from the unfiltered `CoreBase.metadata.create_all` at startup
(#2313, tracked under #2314). Sharing one physical table meant each backend's
`GET /tasks` returned the other's rows, so the Activity page listed every task
twice.

`control-plane` keeps the `cp_`-prefixed pair (its `b7e1c4a09d52` drops the
shared one). Postgres scopes index names per schema, so both pairs carry their
table name in every index name.

No backfill: task rows are operational telemetry, not records of record, so the
history that lived in the shared table is deliberately not carried over (#2170).

The DDL below is intentionally a self-contained copy of the shape
`control_plane_backend/alembic/versions/b7e1c4a09d52` creates, not a shared
helper import: a migration is a frozen snapshot, and importing living code into
it would let a later refactor silently rewrite history.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8f2d5b13ea6"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "bcd7cbdbedca"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSONB = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")
_BIGINT_PK = sa.BigInteger().with_variant(sa.INTEGER(), "sqlite")

_RUN = "kf_task_run"
_LOG = "kf_task_event_log"

# Mirrors `fred_core.tasks.orm_models.task_run_table_args`.
_NON_TERMINAL_MIGRATION = "kind = 'migration' AND state NOT IN ('succeeded', 'failed', 'cancelled')"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        _RUN,
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("progress", sa.Float(), nullable=True),
        sa.Column("step", sa.Text(), nullable=True),
        sa.Column("detail", _JSONB, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("target", _JSONB, nullable=True),
        sa.Column("execution_id", sa.String(length=255), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("team_id", sa.String(length=255), nullable=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(length=36), nullable=True),
        sa.PrimaryKeyConstraint("task_id"),
    )
    op.create_index(op.f(f"ix_{_RUN}_kind"), _RUN, ["kind"], unique=False)
    op.create_index(op.f(f"ix_{_RUN}_state"), _RUN, ["state"], unique=False)
    op.create_index(op.f(f"ix_{_RUN}_created_by"), _RUN, ["created_by"], unique=False)
    op.create_index(op.f(f"ix_{_RUN}_team_id"), _RUN, ["team_id"], unique=False)
    op.create_index(op.f(f"ix_{_RUN}_scheduled_for"), _RUN, ["scheduled_for"], unique=False)
    # Reconciliation sweeper: scans non-terminal tasks ordered by age.
    op.create_index(f"ix_{_RUN}_state_updated", _RUN, ["state", "updated_at"], unique=False)
    # At most one non-terminal kind='migration' row. Knowledge-flow never creates
    # migration-kind tasks today, but the table shape is shared with control-plane
    # and `alembic check` compares it against the same ORM mixin.
    op.create_index(
        f"uq_{_RUN}_single_active_migration",
        _RUN,
        ["kind"],
        unique=True,
        sqlite_where=sa.text(_NON_TERMINAL_MIGRATION),
        postgresql_where=sa.text(_NON_TERMINAL_MIGRATION),
    )

    op.create_table(
        _LOG,
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
        sa.Column("emitted_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "seq", name=f"uq_{_LOG}_task_seq"),
    )
    op.create_index(op.f(f"ix_{_LOG}_task_id"), _LOG, ["task_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema. Indexes are dropped with their table on both backends."""
    op.drop_table(_LOG)
    op.drop_table(_RUN)
