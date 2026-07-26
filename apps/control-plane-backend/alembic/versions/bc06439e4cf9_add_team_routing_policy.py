"""add team_routing_policy table

Team-owned (and personal-space) LLM model routing policy — team_editor
picks a default chat profile and per-operation overrides, bounded by
kind="model" capability enablement (TEAM-05, #2118,
TEAM-ROUTING-POLICY-RFC.md §3/§10).

Revision ID: bc06439e4cf9
Revises: 9e5074103b67
Create Date: 2026-07-26 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bc06439e4cf9"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "9e5074103b67"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "team_routing_policy",
        sa.Column("team_id", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("chat_default_profile_id", sa.String(), nullable=True),
        sa.Column(
            "operation_rules_json",
            sa.Text(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("team_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("team_routing_policy")
