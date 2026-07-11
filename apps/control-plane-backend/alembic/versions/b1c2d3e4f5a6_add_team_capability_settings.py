"""add team_capability_settings table

Per-team capability enablement settings (CAPAB-01 / #1980, RFC AGENT-CAPABILITY
§8.2). The configuration half of enablement; authorization lives in OpenFGA.

Revision ID: b1c2d3e4f5a6
Revises: a6b7c8d9e0f1
Create Date: 2026-07-11 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "a6b7c8d9e0f1"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "team_capability_settings",
        sa.Column("team_id", sa.String(), nullable=False),
        sa.Column("capability_id", sa.String(), nullable=False),
        sa.Column(
            "settings_json",
            sa.Text(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("team_id", "capability_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("team_capability_settings")
