# SPDX-License-Identifier: Apache-2.0
"""Index the current chat stream segment of each captured turn.

Revision ID: a81d6c5072e4
Revises: 7f3c41ac2d09
"""

import sqlalchemy as sa
from alembic import op

revision = "a81d6c5072e4"  # pragma: allowlist secret
down_revision = "7f3c41ac2d09"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_trace_turn",
        sa.Column("chat_stream_segment_id", sa.String(36), nullable=True),
    )
    op.create_index(
        "uq_trace_turn_session_chat_stream_segment",
        "conversation_trace_turn",
        ["session_id", "chat_stream_segment_id"],
        unique=True,
        postgresql_where=sa.text("chat_stream_segment_id IS NOT NULL"),
        sqlite_where=sa.text("chat_stream_segment_id IS NOT NULL"),
    )
    op.add_column(
        "conversation_trace_turn",
        sa.Column("chat_stream_result_segment_id", sa.String(36), nullable=True),
    )
    op.create_index(
        "ix_trace_turn_session_chat_result_segment",
        "conversation_trace_turn",
        ["session_id", "chat_stream_result_segment_id"],
        postgresql_where=sa.text("chat_stream_result_segment_id IS NOT NULL"),
        sqlite_where=sa.text("chat_stream_result_segment_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_trace_turn_session_chat_result_segment",
        table_name="conversation_trace_turn",
    )
    op.drop_column("conversation_trace_turn", "chat_stream_result_segment_id")
    op.drop_index(
        "uq_trace_turn_session_chat_stream_segment",
        table_name="conversation_trace_turn",
    )
    op.drop_column("conversation_trace_turn", "chat_stream_segment_id")
