"""add category column to prompt table

Stores the functional category (doc-assist, summary, extraction…) for each
prompt-library record. Nullable so existing rows keep working until they are
re-saved with a category.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-06-02 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d6e7f8a9b0c1"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "c5d6e7f8a9b0"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add category column to the prompt table."""
    op.add_column(
        "prompt",
        sa.Column("category", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    """Remove category column from the prompt table."""
    op.drop_column("prompt", "category")
