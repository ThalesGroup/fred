"""merge heads: agent_instance comments + task/session tables

Revision ID: b4c5d6e7f8a9
Revises: a2b3c4d5e6f7, a3b4c5d6e7f8
Create Date: 2026-06-09 00:00:00.000000

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "b4c5d6e7f8a9"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "a2b3c4d5e6f7",  # pragma: allowlist secret
    "a3b4c5d6e7f8",  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
