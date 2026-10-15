# SPDX-License-Identifier: Apache-2.0
"""Distinguish team-admin join links from Free-team enrollment links.

Revision ID: c3a7e5d9f1b2
Revises: 24c2f88374fe
"""

import sqlalchemy as sa
from alembic import op

revision = "c3a7e5d9f1b2"  # pragma: allowlist secret
down_revision = "24c2f88374fe"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "platform_access_links",
        sa.Column("kind", sa.String(8), server_default="free", nullable=False),
    )


def downgrade() -> None:
    op.execute("DELETE FROM platform_access_links WHERE kind = 'team'")
    with op.batch_alter_table("platform_access_links") as batch:
        batch.drop_column("kind")
