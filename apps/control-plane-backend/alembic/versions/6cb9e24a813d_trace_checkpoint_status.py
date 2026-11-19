# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Store the observed root checkpoint status on conversation trace turns.

Revision ID: 6cb9e24a813d
Revises: 4eea63270bc1
"""

import sqlalchemy as sa
from alembic import op

revision = "6cb9e24a813d"  # pragma: allowlist secret
down_revision = "4eea63270bc1"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_trace_turn", sa.Column("checkpoint_status", sa.String(32))
    )


def downgrade() -> None:
    op.drop_column("conversation_trace_turn", "checkpoint_status")
