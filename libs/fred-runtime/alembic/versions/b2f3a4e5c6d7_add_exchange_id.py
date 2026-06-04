"""add exchange_id to session_history

Per-turn UUID used to join KPI and history records for a single agent turn.

Revision ID: b2f3a4e5c6d7
Revises: a1e2f3c4d5b6
Create Date: 2026-06-02 00:01:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2f3a4e5c6d7"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "a1e2f3c4d5b6"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "session_history",
        sa.Column("exchange_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("session_history", "exchange_id")
