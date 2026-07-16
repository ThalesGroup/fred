"""merge heads: mcp prefix drop + team capability settings

Revision ID: 7fb19a619b0e
Revises: a1b2c3d4e5f7, b1c2d3e4f5a6
Create Date: 2026-07-16 10:42:07.342830

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "7fb19a619b0e"
down_revision: Union[str, Sequence[str], None] = ("a1b2c3d4e5f7", "b1c2d3e4f5a6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
