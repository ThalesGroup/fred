"""add prompt table

Stores team-scoped prompt-library records owned by control-plane, including the
reserved ``personal`` team scope.

Revision ID: 9c4e1a2b3d4f
Revises: f1a2b3c4d5e6
Create Date: 2026-05-08 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c4e1a2b3d4f"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "f1a2b3c4d5e6"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "prompt",
        sa.Column("prompt_id", sa.String(), nullable=False),
        sa.Column("team_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("prompt_id"),
        sa.UniqueConstraint("team_id", "name", name="uq_prompt_team_name"),
    )
    op.create_index(op.f("ix_prompt_team_id"), "prompt", ["team_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(op.f("ix_prompt_team_id"), table_name="prompt")
    op.drop_table("prompt")
