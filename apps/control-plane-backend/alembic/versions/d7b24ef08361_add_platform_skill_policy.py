# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Add global packaged skill activation policy.

Revision ID: d7b24ef08361
Revises: f28c3e9ab641
"""

import sqlalchemy as sa
from alembic import op

revision: str = "d7b24ef08361"  # pragma: allowlist secret - public Alembic revision
down_revision: str = "f28c3e9ab641"  # pragma: allowlist secret - public Alembic parent
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    """Create the shared opt-out table; existing skills remain enabled."""
    op.create_table(
        "platform_skill_policy",
        sa.Column("skill_name", sa.String(length=64), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """Remove activation overrides after runtimes no longer require them."""
    op.drop_table("platform_skill_policy")
