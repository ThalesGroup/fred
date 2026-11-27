# SPDX-License-Identifier: Apache-2.0
"""Save each user's Resources file browser visibility.

Revision ID: b6e47a91c3d0
Revises: e5b1c9d3a742
"""

import sqlalchemy as sa
from alembic import op

revision = "b6e47a91c3d0"  # pragma: allowlist secret
down_revision = "e5b1c9d3a742"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users_preferences",
        sa.Column(
            "resources_tree_open",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users_preferences", "resources_tree_open")
