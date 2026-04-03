"""add session_purge_queue

New table introduced during the purge-queue refactoring.

Revision ID: a1b2c3d4e5f6
Revises: d01a50e94bec
Create Date: 2026-04-01 16:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "d01a50e94bec"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "session_purge_queue",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("team_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index(
        op.f("ix_session_purge_queue_created_at"),
        "session_purge_queue",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_session_purge_queue_due_at"),
        "session_purge_queue",
        ["due_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_session_purge_queue_status"),
        "session_purge_queue",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_session_purge_queue_team_id"),
        "session_purge_queue",
        ["team_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_session_purge_queue_updated_at"),
        "session_purge_queue",
        ["updated_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_session_purge_queue_user_id"),
        "session_purge_queue",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_session_purge_queue_user_id"), table_name="session_purge_queue"
    )
    op.drop_index(
        op.f("ix_session_purge_queue_updated_at"), table_name="session_purge_queue"
    )
    op.drop_index(
        op.f("ix_session_purge_queue_team_id"), table_name="session_purge_queue"
    )
    op.drop_index(
        op.f("ix_session_purge_queue_status"), table_name="session_purge_queue"
    )
    op.drop_index(
        op.f("ix_session_purge_queue_due_at"), table_name="session_purge_queue"
    )
    op.drop_index(
        op.f("ix_session_purge_queue_created_at"), table_name="session_purge_queue"
    )
    op.drop_table("session_purge_queue")
