"""One expiring active turn per conversation."""

import sqlalchemy as sa
from alembic import op

revision = "e1f2a3b4c5d6"  # pragma: allowlist secret
down_revision = "d0e1f2a3b4c5"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    op.create_table(
        "session_active_turn",
        sa.Column("session_id", sa.Uuid if postgres else sa.String, primary_key=True),
        sa.Column("owner_token", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    if postgres:
        op.create_foreign_key(
            "session_active_turn_root_fk",
            "session_active_turn",
            "session_metadata",
            ["session_id"],
            ["session_id"],
            referent_schema="control_plane",
            ondelete="CASCADE",
        )


def downgrade() -> None:
    op.drop_table("session_active_turn")
