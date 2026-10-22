"""add sandbox settings

Revision ID: d0a1b2c3d4e5
Revises: c9acb7dd3ad0
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d0a1b2c3d4e5"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "c9acb7dd3ad0"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sandbox_settings",
        sa.Column("id", sa.String(), primary_key=True, server_default="default"),
        sa.Column("idle_minutes", sa.Integer(), nullable=False, server_default="20"),
        sa.Column(
            "max_active_sessions", sa.Integer(), nullable=False, server_default="8"
        ),
        sa.Column("warm_capacity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("id = 'default'", name="ck_sandbox_settings_singleton"),
        sa.CheckConstraint("idle_minutes BETWEEN 1 AND 120", name="ck_sandbox_idle"),
        sa.CheckConstraint(
            "max_active_sessions BETWEEN 1 AND 1000", name="ck_sandbox_active"
        ),
        sa.CheckConstraint("warm_capacity BETWEEN 0 AND 1000", name="ck_sandbox_warm"),
    )


def downgrade() -> None:
    op.drop_table("sandbox_settings")
