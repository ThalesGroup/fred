# SPDX-License-Identifier: Apache-2.0
"""Whitelist emails of people who have not signed in yet.

Revision ID: e5b1c9d3a742
Revises: d7a2f591c034
"""

import sqlalchemy as sa
from alembic import op

revision = "e5b1c9d3a742"  # pragma: allowlist secret
down_revision = "d7a2f591c034"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_access_pending_emails",
        sa.Column("email", sa.String(320), primary_key=True),
        sa.Column("granted_by", sa.String(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("platform_access_pending_emails")
