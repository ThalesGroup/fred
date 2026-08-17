"""merge heads: model reasoning display name + routing policy simplification

Revision ID: 7fde1b42d5d0
Revises: a7d2e9c41f38, b4d5e6f7a8c9
Create Date: 2026-08-14 04:21:06.011152

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "7fde1b42d5d0"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = ("a7d2e9c41f38", "b4d5e6f7a8c9")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

__all__ = [
    "branch_labels",
    "depends_on",
    "down_revision",
    "downgrade",
    "revision",
    "upgrade",
]


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
