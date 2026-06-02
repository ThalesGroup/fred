"""add emoji and tags to prompt table

Merges the two open heads (prompt library + session purge queue) and adds
emoji/tags columns for the prompt card redesign.

Revision ID: c5d6e7f8a9b0
Revises: b3c4d5e6f7a8, a1b2c3d4e5f6
Create Date: 2026-06-02 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5d6e7f8a9b0"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "b3c4d5e6f7a8",  # pragma: allowlist secret  prompt_library_extension
    "a1b2c3d4e5f6",  # pragma: allowlist secret  add_session_purge_queue
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add emoji and tags columns to the prompt table."""
    op.add_column("prompt", sa.Column("emoji", sa.String(length=8), nullable=True))
    op.add_column(
        "prompt",
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    """Remove emoji and tags columns from the prompt table."""
    op.drop_column("prompt", "tags")
    op.drop_column("prompt", "emoji")
