"""add agent run lifecycle registry

Revision ID: c4e8f1a2b305
Revises: a3f7c9e2d514
Create Date: 2026-09-17 18:45:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4e8f1a2b305"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "a3f7c9e2d514"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("run_id", sa.String(length=256), nullable=False),
        sa.Column("person_id", sa.String(length=256), nullable=False),
        sa.Column("team_id", sa.String(length=256), nullable=True),
        sa.Column("agent_id", sa.String(length=256), nullable=False),
        sa.Column("agent_instance_id", sa.String(length=256), nullable=True),
        sa.Column("reporter_client_id", sa.String(length=256), nullable=False),
        sa.Column("reporter_subject", sa.String(length=256), nullable=False),
        sa.Column("origin_caller", sa.String(length=256), nullable=True),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_ceiling_seconds", sa.Float(), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("stop_reason", sa.String(length=64), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index("ix_agent_runs_person_id", "agent_runs", ["person_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_runs_person_id", table_name="agent_runs")
    op.drop_table("agent_runs")
