"""Add the admin-chosen chat profile for generated conversation titles.

Revision ID: b5d2e8f7c031
Revises: f28c3e9ab641
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b5d2e8f7c031"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "f28c3e9ab641"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "creation_assistant_settings",
        sa.Column("title_model_profile_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("creation_assistant_settings") as batch_op:
        batch_op.drop_column("title_model_profile_id")
