"""add prompt.command with a per-team partial unique index

Revision ID: 21e235382895
Revises: b88202b8451e
Create Date: 2026-09-28 17:05:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
# codeql[py/unused-global-variable]
revision: str = "21e235382895"
# codeql[py/unused-global-variable]
down_revision: Union[str, Sequence[str], None] = "b88202b8451e"
# codeql[py/unused-global-variable]
branch_labels: Union[str, Sequence[str], None] = None
# codeql[py/unused-global-variable]
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "prompt",
        sa.Column(
            "command",
            sa.String(length=64),
            nullable=True,
        ),
    )
    # Partial: any number of prompts may carry no command, a present one is
    # unique within its team.
    op.create_index(
        "uq_prompt_team_command",
        "prompt",
        ["team_id", "command"],
        unique=True,
        postgresql_where=sa.text("command IS NOT NULL"),
        sqlite_where=sa.text("command IS NOT NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_prompt_team_command", table_name="prompt")
    op.drop_column("prompt", "command")
