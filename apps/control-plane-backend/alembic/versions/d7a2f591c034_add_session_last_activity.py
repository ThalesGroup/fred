"""Add explicit conversation activity for home launchers.

Revision ID: d7a2f591c034
Revises: b8e1f4a2c6d9
"""

import sqlalchemy as sa
from alembic import op

revision = "d7a2f591c034"  # pragma: allowlist secret
down_revision = "b8e1f4a2c6d9"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "session_metadata",
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_session_metadata_user_agent_activity",
        "session_metadata",
        ["user_id", "agent_instance_id", "last_activity_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_session_metadata_user_agent_activity", table_name="session_metadata"
    )
    op.drop_column("session_metadata", "last_activity_at")
