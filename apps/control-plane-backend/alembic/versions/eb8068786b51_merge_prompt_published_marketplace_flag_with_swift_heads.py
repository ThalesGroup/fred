"""merge prompt-published marketplace flag with swift heads

Revision ID: eb8068786b51
Revises: 0dd1e72106af, d5c9a1b73e60
Create Date: 2026-08-24 08:43:24.032090

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
# codeql[py/unused-global-variable]
revision: str = "eb8068786b51"
# codeql[py/unused-global-variable]
down_revision: Union[str, Sequence[str], None] = ("0dd1e72106af", "d5c9a1b73e60")
# codeql[py/unused-global-variable]
branch_labels: Union[str, Sequence[str], None] = None
# codeql[py/unused-global-variable]
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
