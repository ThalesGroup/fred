"""split task tables per backend: task_run/task_event_log -> cp_task_run/cp_task_event_log

Revision ID: b7e1c4a09d52
Revises: f3790013f637
Create Date: 2026-08-14 00:00:00.000000

control-plane and knowledge-flow both migrate the same `fred` database, and both
mapped the *same* shared `task_run`/`task_event_log` (registered on fred-core's
`CoreBase`). Neither backend scoped `GET /tasks` to the rows it created, so each
returned the other's tasks and the Activity page listed every task twice (#2170).

Each backend now owns a prefixed pair declared on its own `Base`
(`control_plane_backend.models.task_models`). Postgres scopes index names per
schema, so the indexes are renamed with the tables.

Create-only: the shared `task_run`/`task_event_log` are deliberately LEFT IN
PLACE, orphaned, to be dropped by a later release. #2170 is fixed the moment each
backend maps its own pair — the old table's continued existence changes nothing
about which rows a backend returns. There is no backfill either; task rows are
progress bookkeeping and #2170 chose not to carry them over.

Why not drop it here, which was the original plan: the two Temporal workers have
no `migration:` block in `deploy/charts/fred/values.yaml`, so unlike the API
Deployments they get no `hook-scale-down` Job and keep running OLD code through
the entire hook phase and the rolling update that follows. Old knowledge-flow
worker code writes to the shared `task_run` via `emit_ingestion_task_event`
(`features/scheduler/activities.py`), which is an unguarded `@activity.defn`
invoked as the FIRST step of `ProcessPushFile` with `maximum_attempts=1`
(`features/scheduler/workflow.py`). Dropping the table mid-deploy therefore does
not merely lose task bookkeeping — it fails the workflow before any extraction
runs, and the document is never ingested, with no retry. Leaving one dead table
pair behind for a release is the cheaper side of that trade.

This also keeps the revision symmetric with knowledge-flow's `c8f2d5b13ea6`:
create on upgrade, drop on downgrade, nothing conditional.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b7e1c4a09d52"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "f3790013f637"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSONB = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")
_BIGINT_PK = sa.BigInteger().with_variant(sa.INTEGER(), "sqlite")

_RUN = "cp_task_run"
_LOG = "cp_task_event_log"

# Mirrors `fred_core.tasks.orm_models.task_run_table_args`.
_NON_TERMINAL_MIGRATION = (
    "kind = 'migration' AND state NOT IN ('succeeded', 'failed', 'cancelled')"
)


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
        sa.PrimaryKeyConstraint("task_id"),
    )
    op.create_index(op.f(f"ix_{_RUN}_kind"), _RUN, ["kind"], unique=False)
    op.create_index(op.f(f"ix_{_RUN}_state"), _RUN, ["state"], unique=False)
    op.create_index(op.f(f"ix_{_RUN}_created_by"), _RUN, ["created_by"], unique=False)
    op.create_index(op.f(f"ix_{_RUN}_team_id"), _RUN, ["team_id"], unique=False)
    op.create_index(
        op.f(f"ix_{_RUN}_scheduled_for"), _RUN, ["scheduled_for"], unique=False
    )
    # Reconciliation sweeper: scans non-terminal tasks ordered by age.
    op.create_index(f"ix_{_RUN}_state_updated", _RUN, ["state", "updated_at"])
    # At most one non-terminal kind='migration' row (import/reset exclusion).
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
        sa.Column("id", _BIGINT_PK, autoincrement=True, nullable=False),
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
        sa.UniqueConstraint("task_id", "seq", name=f"uq_{_LOG}_task_seq"),
    )
    op.create_index(op.f(f"ix_{_LOG}_task_id"), _LOG, ["task_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema. Indexes are dropped with their table on both backends.

    Unguarded, like `c8f2d5b13ea6`'s: the pair can only exist if this revision
    created it. The shared `task_run` is untouched in both directions.
    """
    op.drop_table(_LOG)
    op.drop_table(_RUN)
