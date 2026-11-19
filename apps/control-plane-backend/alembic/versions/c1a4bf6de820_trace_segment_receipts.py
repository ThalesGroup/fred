# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Track independently admitted and published segments on a captured exchange.

Revision ID: c1a4bf6de820
Revises: 6cb9e24a813d
"""

import sqlalchemy as sa
from alembic import op

revision = "c1a4bf6de820"
down_revision = "6cb9e24a813d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversation_trace_turn", sa.Column("segment_receipts", sa.JSON()))


def downgrade() -> None:
    op.drop_column("conversation_trace_turn", "segment_receipts")
