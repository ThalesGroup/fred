"""add team_id and agent_instance_id to session_history

Team-scoped and managed-execution identity columns added for admin and
retention queries.  These are nullable for backward compatibility with rows
written before this revision.

Revision ID: c3d4b5a6f7e8
Revises: b2f3a4e5c6d7
Create Date: 2026-06-02 00:02:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4b5a6f7e8"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "b2f3a4e5c6d7"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "session_history",
        sa.Column("team_id", sa.String(), nullable=True),
    )
    op.add_column(
        "session_history",
        sa.Column("agent_instance_id", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_session_history_team_id",
        "session_history",
        ["team_id"],
        unique=False,
    )
    op.create_index(
        "ix_session_history_agent_instance_id",
        "session_history",
        ["agent_instance_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_session_history_agent_instance_id", table_name="session_history")
    op.drop_index("ix_session_history_team_id", table_name="session_history")
    op.drop_column("session_history", "agent_instance_id")
    op.drop_column("session_history", "team_id")
