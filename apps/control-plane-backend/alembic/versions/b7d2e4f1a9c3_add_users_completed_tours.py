"""Record which guided tours each user has finished.

Revision ID: b7d2e4f1a9c3
Revises: 8a49f3ac2e6b
"""

import sqlalchemy as sa
from alembic import op

revision = "b7d2e4f1a9c3"  # pragma: allowlist secret
down_revision = "8a49f3ac2e6b"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users_preferences",
        sa.Column(
            "completed_tours",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users_preferences", "completed_tours")
