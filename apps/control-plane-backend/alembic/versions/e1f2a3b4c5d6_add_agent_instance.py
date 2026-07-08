"""add agent_instance table

DB-backed managed agent instance enrollment records.
Replaces the in-process ApplicationContext._agent_instance_registry placeholder.

Revision ID: e1f2a3b4c5d6
Revises: a1b2c3d4e5f6
Create Date: 2026-04-19 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "a1b2c3d4e5f6"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "agent_instance",
        sa.Column("agent_instance_id", sa.String(), nullable=False),
        sa.Column("team_id", sa.String(), nullable=False),
        sa.Column("template_id", sa.String(), nullable=False),
        sa.Column("source_runtime_id", sa.String(), nullable=False),
        sa.Column("source_agent_id", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("tuning_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("agent_instance_id"),
    )
    op.create_index(
        op.f("ix_agent_instance_team_id"),
        "agent_instance",
        ["team_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_agent_instance_team_id"), table_name="agent_instance")
    op.drop_table("agent_instance")
