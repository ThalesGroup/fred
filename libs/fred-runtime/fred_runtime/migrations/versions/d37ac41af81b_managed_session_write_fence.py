# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Keep a shared managed session write fence after erasure.

Revision ID: d37ac41af81b
Revises: b34a0d59ef71
"""

import sqlalchemy as sa
from alembic import op

revision = "d37ac41af81b"  # pragma: allowlist secret
down_revision = "b34a0d59ef71"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "managed_session_write_fence",
        sa.Column("session_key", sa.String(64), primary_key=True),
        sa.Column("erased", sa.Boolean(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("managed_session_write_fence")
