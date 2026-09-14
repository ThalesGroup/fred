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

# revision identifiers, used by Alembic.
revision: str = "d3f8a2c6e174"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "b7d4c1a9e802"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema. Indexes are dropped with their table."""
    op.drop_table("task_event_log")
    op.drop_table("task_run")


def downgrade() -> None:
    """Downgrade schema: an empty skeleton, not the full pre-split shape.

    Only what `a3b4c5d6e7f8`'s downgrade drops unguarded; the other older
    downgrades skip the columns and indexes that are absent.
    """
    op.create_table(
        "task_run",
        sa.Column("kind", sa.String(length=64)),
        sa.Column("state", sa.String(length=32)),
        sa.Column("created_by", sa.String(length=36)),
        sa.Column("team_id", sa.String(length=255)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    for column in ("kind", "state", "created_by", "team_id"):
        op.create_index(f"ix_task_run_{column}", "task_run", [column])
    op.create_index("ix_task_run_state_updated", "task_run", ["state", "updated_at"])
    op.create_table("task_event_log", sa.Column("task_id", sa.String(length=36)))
    op.create_index("ix_task_event_log_task_id", "task_event_log", ["task_id"])
