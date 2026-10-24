"""Add durable per-user display preferences.

Revision ID: f28c3e9ab641
Revises: 7e0d93f21c6a
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f28c3e9ab641"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "7e0d93f21c6a"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users_preferences",
        sa.Column("user_id", sa.String(), primary_key=True),
        sa.Column("ui_theme_id", sa.String(length=32), nullable=True),
        sa.Column(
            "theme_mode", sa.String(length=6), nullable=False, server_default="system"
        ),
        sa.Column("language", sa.String(length=2), nullable=True),
        sa.Column(
            "sidebar_collapsed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "team_sort_mode",
            sa.String(length=6),
            nullable=False,
            server_default="recent",
        ),
        sa.Column(
            "agent_sort", sa.String(length=20), nullable=False, server_default="name"
        ),
        sa.Column("trace_expanded", sa.Boolean(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )


def downgrade() -> None:
    op.drop_table("users_preferences")
