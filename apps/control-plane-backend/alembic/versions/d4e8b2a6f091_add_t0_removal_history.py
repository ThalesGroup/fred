# SPDX-License-Identifier: Apache-2.0
"""Track individual removals for explicit T0 refreshes.

Revision ID: d4e8b2a6f091
Revises: c3a7e5d9f1b2
"""

import sqlalchemy as sa
from alembic import op

revision = "d4e8b2a6f091"  # pragma: allowlist secret
down_revision = "c3a7e5d9f1b2"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "platform_access_settings",
        sa.Column(
            "t0_removal_history_complete",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.execute(
        "UPDATE platform_access_settings SET t0_removal_history_complete = false "
        "WHERE t0_completed_at IS NOT NULL"
    )
    op.create_table(
        "platform_access_removals",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("removed_by", sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("platform_access_removals")
    op.drop_column("platform_access_settings", "t0_removal_history_complete")
