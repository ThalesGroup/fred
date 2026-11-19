# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Record manual consent notes and standalone incidents on their grants.

Revision ID: 2f0ac7d34e61
Revises: 4d81a3f9b2c6
"""

import sqlalchemy as sa
from alembic import op

revision = "2f0ac7d34e61"
down_revision = "4d81a3f9b2c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversation_trace_consent", sa.Column("source_note", sa.Text()))
    op.add_column(
        "conversation_trace_consent", sa.Column("incident", sa.JSON(none_as_null=True))
    )


def downgrade() -> None:
    op.drop_column("conversation_trace_consent", "incident")
    op.drop_column("conversation_trace_consent", "source_note")
