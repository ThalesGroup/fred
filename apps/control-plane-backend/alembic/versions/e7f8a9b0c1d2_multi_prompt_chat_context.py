"""multi-prompt chat context — ordered session_context_prompts association

PROMPT-05 / PROMPTS.md §5: a conversation may have 0, 1, or many prompts attached
as chat context, cumulatively and ordered. Replaces the scalar
``session_metadata.context_prompt_id`` with the ordered association table
``session_context_prompts``.

Steps:
1. create ``session_context_prompts`` (session_id, prompt_id, position);
2. backfill one row ``(session_id, context_prompt_id, 0)`` per session that had a
   non-null scalar context prompt;
3. drop ``session_metadata.context_prompt_id``.

Revision ID: e7f8a9b0c1d2
Revises: a7c1e9d2b4f6
Create Date: 2026-06-19 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "a7c1e9d2b4f6"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "session_context_prompts",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("prompt_id", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["session_metadata.session_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("session_id", "prompt_id"),
    )

    # Backfill the scalar reference as the first (position 0) attached prompt.
    op.execute(
        """
        INSERT INTO session_context_prompts (session_id, prompt_id, position)
        SELECT session_id, context_prompt_id, 0
        FROM session_metadata
        WHERE context_prompt_id IS NOT NULL
        """
    )

    op.drop_column("session_metadata", "context_prompt_id")


def downgrade() -> None:
    """Downgrade schema."""

    op.add_column(
        "session_metadata",
        sa.Column("context_prompt_id", sa.String(), nullable=True),
    )

    # Restore the scalar from the first attached prompt (position 0).
    op.execute(
        """
        UPDATE session_metadata
        SET context_prompt_id = (
            SELECT prompt_id
            FROM session_context_prompts
            WHERE session_context_prompts.session_id = session_metadata.session_id
              AND session_context_prompts.position = 0
        )
        """
    )

    op.drop_table("session_context_prompts")
