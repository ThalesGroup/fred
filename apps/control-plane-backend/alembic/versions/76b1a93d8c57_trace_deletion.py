# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Distinguish conversations removed from chat and retained for support."""

import sqlalchemy as sa
from alembic import op

revision = "76b1a93d8c57"
down_revision = "78961f25bd30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "session_metadata",
        sa.Column(
            "trace_retained_after_delete",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("session_metadata", "trace_retained_after_delete")
