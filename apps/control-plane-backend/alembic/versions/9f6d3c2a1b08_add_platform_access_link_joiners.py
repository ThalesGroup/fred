# SPDX-License-Identifier: Apache-2.0
"""Record successful Free-link team joins.

Revision ID: 9f6d3c2a1b08
Revises: 93427a5fe874
"""

import sqlalchemy as sa
from alembic import op

revision = "9f6d3c2a1b08"  # pragma: allowlist secret
down_revision = "93427a5fe874"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_access_link_joiners",
        sa.Column(
            "link_id",
            sa.Uuid(),
            sa.ForeignKey("platform_access_links.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("user_id", sa.Uuid(), primary_key=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("username_snapshot", sa.String(), nullable=True),
        sa.Column("first_name_snapshot", sa.String(), nullable=True),
        sa.Column("last_name_snapshot", sa.String(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_platform_access_link_joiners_page",
        "platform_access_link_joiners",
        ["link_id", "joined_at", "user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_platform_access_link_joiners_page",
        table_name="platform_access_link_joiners",
    )
    op.drop_table("platform_access_link_joiners")
