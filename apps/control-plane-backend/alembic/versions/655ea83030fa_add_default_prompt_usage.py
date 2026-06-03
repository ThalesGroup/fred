"""add_default_prompt_usage

Tracks session_count for immutable platform-default prompts.
Default prompts are never stored in the ``prompt`` table (they are generated
at query time), so this table provides the counter that PromptRow.session_count
covers for user-created prompts.

Primary key: (team_id, category) — one row per default prompt per team,
created on first activation and incremented on each subsequent use.

Revision ID: 655ea83030fa
Revises: f0f1e2d3c4b5
Create Date: 2026-06-02 11:55:40.095371

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "655ea83030fa"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "f0f1e2d3c4b5"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "default_prompt_usage",
        sa.Column("team_id", sa.String(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("session_count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("team_id", "category"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("default_prompt_usage")
