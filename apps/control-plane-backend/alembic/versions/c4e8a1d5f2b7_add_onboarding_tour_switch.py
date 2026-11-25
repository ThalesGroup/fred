"""Let platform admins turn the guided tutorial off.

Revision ID: c4e8a1d5f2b7
Revises: b7d2e4f1a9c3
"""

import sqlalchemy as sa
from alembic import op

revision = "c4e8a1d5f2b7"  # pragma: allowlist secret
down_revision = "b7d2e4f1a9c3"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "platform_ui_settings",
        sa.Column(
            "onboarding_tour_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("platform_ui_settings", "onboarding_tour_enabled")
