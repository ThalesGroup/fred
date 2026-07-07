"""add session_metadata table

Stores control-plane-owned session metadata records.
Runtime message history remains in fred-runtime (session_history table).

Revision ID: f1a2b3c4d5e6
Revises: e1f2a3b4c5d6
Create Date: 2026-04-23 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "e1f2a3b4c5d6"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "session_metadata",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("team_id", sa.String(), nullable=False),
        sa.Column("agent_instance_id", sa.String(), nullable=True),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
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
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index(
        op.f("ix_session_metadata_team_id"),
        "session_metadata",
        ["team_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_session_metadata_agent_instance_id"),
        "session_metadata",
        ["agent_instance_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_session_metadata_agent_instance_id"),
        table_name="session_metadata",
    )
    op.drop_index(
        op.f("ix_session_metadata_team_id"),
        table_name="session_metadata",
    )
    op.drop_table("session_metadata")
