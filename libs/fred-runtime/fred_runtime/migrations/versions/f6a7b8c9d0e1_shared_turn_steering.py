"""Store active turn steering across runtime replicas."""

import sqlalchemy as sa
from alembic import op
from fred_core.models.base import JsonColumn

revision = "f6a7b8c9d0e1"  # pragma: allowlist secret
down_revision = "e5f6a7b8c9d0"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_turn_steering",
        sa.Column("session_id", sa.String(), primary_key=True),
        sa.Column("turn_id", sa.String(128), nullable=False),
        sa.Column("agent_instance_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("team_id", sa.String(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("pending", JsonColumn, nullable=False),
        sa.Column("seen", JsonColumn, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_runtime_turn_steering_expires_at",
        "runtime_turn_steering",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_table("runtime_turn_steering")
