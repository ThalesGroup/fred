"""prompt library extension — versioning, analytics, context integration

Extends the prompt library schema (P1-D1b):
- prompt: version counter, usage counters, score, token-cost placeholders
- agent_instance: prompt_refs_json for library import metadata
- session_metadata: context_prompt_id for live chat-context reference

Revision ID: b3c4d5e6f7a8
Revises: 9c4e1a2b3d4f, be753abe25d7
Create Date: 2026-05-10 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "9c4e1a2b3d4f",  # pragma: allowlist secret
    "be753abe25d7",  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # prompt: versioning + analytics columns
    op.add_column(
        "prompt", sa.Column("version", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column(
        "prompt",
        sa.Column("import_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "prompt",
        sa.Column("session_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("prompt", sa.Column("score", sa.Float(), nullable=True))
    op.add_column("prompt", sa.Column("avg_input_tokens", sa.Integer(), nullable=True))
    op.add_column("prompt", sa.Column("avg_output_tokens", sa.Integer(), nullable=True))

    # agent_instance: library import back-reference (JSON stored as text, no FK)
    op.add_column(
        "agent_instance", sa.Column("prompt_refs_json", sa.Text(), nullable=True)
    )

    # session_metadata: live chat-context prompt reference
    op.add_column(
        "session_metadata", sa.Column("context_prompt_id", sa.String(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_column("session_metadata", "context_prompt_id")
    op.drop_column("agent_instance", "prompt_refs_json")
    op.drop_column("prompt", "avg_output_tokens")
    op.drop_column("prompt", "avg_input_tokens")
    op.drop_column("prompt", "score")
    op.drop_column("prompt", "session_count")
    op.drop_column("prompt", "import_count")
    op.drop_column("prompt", "version")
