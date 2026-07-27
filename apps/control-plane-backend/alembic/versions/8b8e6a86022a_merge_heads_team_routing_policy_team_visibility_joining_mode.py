"""merge heads: team routing policy + team visibility/joining-mode

Revision ID: 8b8e6a86022a
Revises: 8092a626d4d0, bc06439e4cf9
Create Date: 2026-07-27 06:05:56.424527

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8b8e6a86022a'
down_revision: Union[str, Sequence[str], None] = ('8092a626d4d0', 'bc06439e4cf9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
