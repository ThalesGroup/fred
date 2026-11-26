"""Bind trace block reservations to their admitted execution segment.

Revision ID: 8a49f3ac2e6b
Revises: 2da6fa199e5e
"""

import sqlalchemy as sa
from alembic import op

revision = "8a49f3ac2e6b"  # pragma: allowlist secret
down_revision = "2da6fa199e5e"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Record the segment origin and liveness without changing legacy rows."""
    op.add_column(
        "conversation_trace_storage",
        sa.Column("incremental_segment_id", sa.String(36)),
    )
    op.add_column(
        "conversation_trace_turn",
        sa.Column("capture_activity_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    """Remove the incremental reservation fields on rollback."""
    op.drop_column("conversation_trace_turn", "capture_activity_at")
    op.drop_column("conversation_trace_storage", "incremental_segment_id")
