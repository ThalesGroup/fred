# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Index terminal failure references and record title authorization provenance."""

import sqlalchemy as sa
from alembic import op

revision = "83adb40b71f5"  # pragma: allowlist secret
down_revision = "76b1a93d8c57"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("session_metadata", sa.Column("title_revision", sa.String(36)))
    # Existing consent records have no title authorization proof.
    op.execute(
        "UPDATE session_metadata SET title_revision = 'legacy' WHERE title IS NOT NULL"
    )
    op.add_column(
        "conversation_trace_consent", sa.Column("title_revision", sa.String(36))
    )
    op.add_column(
        "conversation_trace_turn", sa.Column("failure_category", sa.String(32))
    )
    op.add_column(
        "conversation_trace_turn", sa.Column("support_error_ref", sa.String(32))
    )
    op.create_index(
        "ix_conversation_trace_turn_support_error_ref",
        "conversation_trace_turn",
        ["support_error_ref"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conversation_trace_turn_support_error_ref",
        table_name="conversation_trace_turn",
    )
    op.drop_column("conversation_trace_turn", "support_error_ref")
    op.drop_column("conversation_trace_turn", "failure_category")
    op.drop_column("conversation_trace_consent", "title_revision")
    op.drop_column("session_metadata", "title_revision")
