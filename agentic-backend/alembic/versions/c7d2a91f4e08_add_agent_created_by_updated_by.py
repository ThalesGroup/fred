"""add agent created_by / updated_by audit columns

Revision ID: c7d2a91f4e08
Revises: a1c4f7e92b30
Create Date: 2026-07-08 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7d2a91f4e08"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "a1c4f7e92b30"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable on purpose: pre-existing agents and system/seed writes have no actor.
    op.add_column("agent", sa.Column("created_by", sa.String(), nullable=True))
    op.add_column("agent", sa.Column("updated_by", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("agent", "updated_by")
    op.drop_column("agent", "created_by")
