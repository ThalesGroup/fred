"""add model_reasoning table

Platform-wide, per-model reasoning activation — the admin toggle that decides
whether a model's thinking-capable profiles run with reasoning on (REASON-01,
MODEL-REASONING-ENABLEMENT-RFC.md §5.5 option A).

An absent row means OFF (§5.6): enabling a model and enabling its reasoning are
two separate admin actions. No backfill is written on purpose — a deployment
that ran reasoning through models_catalog.yaml alone stops reasoning at this
upgrade until an administrator switches it on (§5.6.1, release-noted).

Revision ID: a7c3d91f2b40
Revises: c1d2e3f4a5b6
Create Date: 2026-07-29 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3d91f2b40"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "c1d2e3f4a5b6"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "model_reasoning",
        sa.Column("model_capability_id", sa.String(), nullable=False),
        sa.Column(
            "reasoning_enabled",
            sa.Boolean(),
            nullable=False,
            comment=(
                "Whether this model's thinking-capable profiles may run with "
                "reasoning on. Absent row = off (REASON-01 §5.6)."
            ),
        ),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("model_capability_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("model_reasoning")
