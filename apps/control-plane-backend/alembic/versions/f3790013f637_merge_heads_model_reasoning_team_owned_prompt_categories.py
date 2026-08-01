"""merge heads: model reasoning + team-owned prompt categories

Revision ID: f3790013f637
Revises: d8e4f7a2c1b9, 8ca7cafc292f
Create Date: 2026-08-01 09:05:10.182240

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "f3790013f637"
down_revision: Union[str, Sequence[str], None] = ("d8e4f7a2c1b9", "8ca7cafc292f")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
