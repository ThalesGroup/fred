"""Keep terminal incident proof separate from the transcript write."""

import sqlalchemy as sa
from alembic import op

revision = "b34a0d59ef71"  # pragma: allowlist secret
down_revision = "a7b8c9d0e1f2"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_trace_incidents",
        sa.Column("session_id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), primary_key=True),
        sa.Column("support_error_ref", sa.String(32), primary_key=True),
        sa.Column("exchange_id", sa.String(), nullable=False),
        sa.Column("first_rank", sa.Integer(), nullable=False),
        sa.Column("last_rank", sa.Integer(), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failure_category", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_session_trace_incidents_rank",
        "session_trace_incidents",
        ["session_id", "last_rank"],
    )


def downgrade() -> None:
    op.drop_table("session_trace_incidents")
