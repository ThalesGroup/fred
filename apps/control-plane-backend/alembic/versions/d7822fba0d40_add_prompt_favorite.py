"""add prompt_favorite: per-user favorite library prompts

Revision ID: d7822fba0d40
Revises: 21e235382895
Create Date: 2026-10-01 15:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
# codeql[py/unused-global-variable]
revision: str = "d7822fba0d40"
# codeql[py/unused-global-variable]
down_revision: Union[str, Sequence[str], None] = "21e235382895"
# codeql[py/unused-global-variable]
branch_labels: Union[str, Sequence[str], None] = None
# codeql[py/unused-global-variable]
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "prompt_favorite",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("prompt_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["prompt_id"], ["prompt.prompt_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "prompt_id"),
    )
    # Deleting a prompt cascades through prompt_id; it needs its own index.
    op.create_index("ix_prompt_favorite_prompt_id", "prompt_favorite", ["prompt_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_prompt_favorite_prompt_id", table_name="prompt_favorite")
    op.drop_table("prompt_favorite")
