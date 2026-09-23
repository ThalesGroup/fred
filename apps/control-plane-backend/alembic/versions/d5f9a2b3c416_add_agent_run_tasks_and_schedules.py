"""add durable agent run task admissions and schedules

Revision ID: d5f9a2b3c416
Revises: c4e8f1a2b305
Create Date: 2026-09-17 19:15:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5f9a2b3c416"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "c4e8f1a2b305"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_run_admissions",
        sa.Column("task_id", sa.String(length=256), nullable=False),
        sa.Column("workflow_id", sa.String(length=256), nullable=False),
        sa.Column("occurrence_key", sa.String(length=256), nullable=True),
        sa.Column("person_id", sa.String(length=256), nullable=False),
        sa.Column("runtime_client_id", sa.String(length=256), nullable=False),
        sa.Column("runtime_subject", sa.String(length=256), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"], ["cp_task_run.task_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("task_id"),
        sa.UniqueConstraint("workflow_id"),
        sa.UniqueConstraint("occurrence_key"),
    )
    op.create_index(
        "ix_agent_run_admissions_person_id", "agent_run_admissions", ["person_id"]
    )
    op.create_table(
        "agent_run_schedules",
        sa.Column("schedule_id", sa.String(length=256), nullable=False),
        sa.Column("team_id", sa.String(length=256), nullable=False),
        sa.Column("agent_instance_id", sa.String(length=256), nullable=False),
        sa.Column("runtime_id", sa.String(length=256), nullable=False),
        sa.Column("created_by", sa.String(length=256), nullable=False),
        sa.Column("template_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("schedule_id"),
    )
    op.create_index(
        "ix_agent_run_schedules_team_id", "agent_run_schedules", ["team_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_agent_run_schedules_team_id", table_name="agent_run_schedules")
    op.drop_table("agent_run_schedules")
    op.drop_index(
        "ix_agent_run_admissions_person_id", table_name="agent_run_admissions"
    )
    op.drop_table("agent_run_admissions")
