"""Store in-flight chat text in session history."""

import sqlalchemy as sa
from alembic import op
from fred_core.models.base import JsonColumn

revision = "a7b8c9d0e1f2"  # pragma: allowlist secret
down_revision = "f6a7b8c9d0e1"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "session_history", sa.Column("message_id", sa.String(128), nullable=True)
    )
    op.add_column(
        "session_history", sa.Column("delivery_state", sa.String(16), nullable=True)
    )
    op.create_index(
        "ux_session_history_message_id",
        "session_history",
        ["session_id", "user_id", "message_id"],
        unique=True,
    )
    op.create_index(
        "ix_session_history_delivery",
        "session_history",
        ["session_id", "user_id", "delivery_state", "rank"],
    )
    op.create_index(
        "ix_session_history_exchange_rank",
        "session_history",
        ["session_id", "exchange_id", "rank"],
    )

    op.drop_index(
        "ix_runtime_turn_steering_expires_at", table_name="runtime_turn_steering"
    )
    op.drop_table("runtime_turn_steering")


def downgrade() -> None:
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
        "ix_runtime_turn_steering_expires_at", "runtime_turn_steering", ["expires_at"]
    )
    op.drop_index("ix_session_history_delivery", table_name="session_history")
    op.drop_index("ix_session_history_exchange_rank", table_name="session_history")
    op.drop_index("ux_session_history_message_id", table_name="session_history")
    op.drop_column("session_history", "delivery_state")
    op.drop_column("session_history", "message_id")
