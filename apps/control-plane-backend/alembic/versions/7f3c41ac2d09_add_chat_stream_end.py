# SPDX-License-Identifier: Apache-2.0
"""Store the observed end of a managed chat stream.

Revision ID: 7f3c41ac2d09
Revises: b6e47a91c3d0
"""

import sqlalchemy as sa
from alembic import op

revision = "7f3c41ac2d09"  # pragma: allowlist secret
down_revision = "b6e47a91c3d0"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_trace_turn",
        sa.Column("chat_stream_end", sa.String(24), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversation_trace_turn", "chat_stream_end")
