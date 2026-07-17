"""merge heads: platform bootstrap + capability system

Revision ID: 37f6de4ac781
Revises: 6e4149d46705, 7fb19a619b0e
Create Date: 2026-07-17 05:21:04.073388

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "37f6de4ac781"
down_revision: Union[str, Sequence[str], None] = ("6e4149d46705", "7fb19a619b0e")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
